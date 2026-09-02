"""情感分析服务：大模型优先，预训练模型次之，词典分析兜底"""
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

import jieba
import jieba.analyse
import requests

logger = logging.getLogger(__name__)

# hf-xet 协议在部分网络环境下不稳定，默认禁用；如需 HF 镜像可设置 HF_ENDPOINT
os.environ.setdefault('HF_HUB_DISABLE_XET', '1')


class _DictionaryAnalyzer:
    """基于情感词典的简易分析器（含否定词与程度副词处理）"""

    POSITIVE_WORDS = {
        '好', '棒', '优秀', '喜欢', '支持', '赞', '不错', '满意', '开心', '感谢',
        '点赞', '靠谱', '暖心', '感动', '厉害', '精彩', '良心', '致敬', '痛快',
        '进步', '希望', '正能量', '温暖', '公平', '正义', '太好了', '期待',
        '舒服', '治愈', '加油', '祝福', '理解', '宽容', '理性', '客观', '欣慰',
        '高兴', '骄傲', '佩服', '认可', '拥护', '称赞', '美好', '善良', '圈粉',
        '教科书', '妥善', '响应', '迅速', '到位', '安心', '放心', '值得',
    }
    NEGATIVE_WORDS = {
        '差', '烂', '垃圾', '讨厌', '反对', '失望', '糟糕', '愤怒', '难过', '骗',
        '恶心', '离谱', '可怕', '担心', '焦虑', '质疑', '谴责', '抗议', '悲哀',
        '寒心', '黑心', '造假', '谣言', '骗子', '委屈', '冤枉', '欺负', '害人',
        '气愤', '不满', '担忧', '痛心', '可恶', '无耻', '冷漠', '怒了', '警惕',
        '傲慢', '敷衍', '推卸', '扯皮', '糊弄', '坑', '套路', '割韭菜', '翻车',
        '严惩', '严查', '追责', '交代', '血压飙升', '气死', '心疼', '避雷',
        '漏洞', '底线', '取关', '欺骗', '曝光', '忍不了', '过分', '乱象',
    }
    NEGATIONS = {'不', '没', '没有', '无', '别', '未', '不是', '并非', '绝不'}
    INTENSIFIERS = {'太', '非常', '特别', '十分', '极其', '超', '贼', '老', '好', '真'}

    NEGATION_PREFIXES = ('不太', '不是', '不', '没有', '没', '并未', '未', '无', '别')

    @classmethod
    def _match_sentiment_word(cls, word: str):
        """
        匹配情感词，返回 (polarity, negated)。
        支持"不太好"这类否定前缀复合词：否定前缀 + 情感词根。
        """
        if word in cls.POSITIVE_WORDS:
            return 'positive', False
        if word in cls.NEGATIVE_WORDS:
            return 'negative', False
        for prefix in cls.NEGATION_PREFIXES:
            if word.startswith(prefix) and len(word) > len(prefix):
                stem = word[len(prefix):]
                if stem in cls.POSITIVE_WORDS:
                    return 'positive', True
                if stem in cls.NEGATIVE_WORDS:
                    return 'negative', True
        return None, False

    @classmethod
    def analyze(cls, text: str) -> dict:
        words = jieba.lcut(text)
        pos_score = 0.0
        neg_score = 0.0

        for i, word in enumerate(words):
            polarity, negated = cls._match_sentiment_word(word)
            if polarity is None:
                continue

            weight = 1.0
            # 程度副词加权
            if i > 0 and words[i - 1] in cls.INTENSIFIERS:
                weight = 1.5
            # 前置否定词翻转极性
            if i > 0 and words[i - 1] in cls.NEGATIONS:
                negated = not negated

            if (polarity == 'positive') != negated:
                pos_score += weight
            else:
                neg_score += weight

        total = pos_score + neg_score
        if total == 0:
            return {'sentiment': 'neutral', 'score': 0.0}

        score = (pos_score - neg_score) / total
        if score > 0.15:
            sentiment = 'positive'
        elif score < -0.15:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        return {'sentiment': sentiment, 'score': round(score, 4)}


class _TransformerAnalyzer:
    """基于 HuggingFace 预训练模型的情感分析器（懒加载，失败自动降级）"""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._pipeline = None
        self._available = None

    @property
    def available(self) -> bool:
        if self._available is None:
            try:
                from transformers import pipeline  # noqa: F401
                self._available = True
            except Exception:
                self._available = False
        return self._available

    def load(self):
        if self._pipeline is None:
            from transformers import pipeline
            logger.info('加载情感分析模型: %s', self.model_name)
            self._pipeline = pipeline(
                'text-classification',
                model=self.model_name,
                truncation=True,
                max_length=512,
            )
        return self._pipeline

    # 置信度低于该阈值时判为中性，避免模型对边界文本过度极化
    NEUTRAL_THRESHOLD = float(os.getenv('SENTIMENT_NEUTRAL_THRESHOLD', '0.6'))

    def analyze_batch(self, texts: list) -> list:
        """批量分析，返回 [{'sentiment':..., 'score':...}]"""
        clf = self.load()
        results = clf(texts, batch_size=32)
        output = []
        for res in results:
            label = res['label'].lower()
            confidence = float(res['score'])
            if confidence < self.NEUTRAL_THRESHOLD:
                sentiment, score = 'neutral', 0.0
            elif 'pos' in label:
                sentiment, score = 'positive', confidence
            elif 'neg' in label:
                sentiment, score = 'negative', -confidence
            else:
                sentiment, score = 'neutral', 0.0
            output.append({'sentiment': sentiment, 'score': round(score, 4)})
        return output


class _LLMAnalyzer:
    """基于大语言模型的舆情情感分析器（OpenAI 兼容 Chat Completions API，效果最佳）

    兼容 DeepSeek / 通义千问 / OpenAI 等接口；配置 LLM_API_KEY 后自动启用。
    支持反讽、反语、网络用语与隐含情绪识别，单条失败时降级为词典分析。
    """

    SYSTEM_PROMPT = (
        '你是一名专业的舆情情感分析专家，擅长识别中文网络文本中的情感，'
        '包括反讽、反语、网络用语和隐含情绪。'
        '请判断文本的情感极性，只输出一个 JSON 对象，不要输出任何其他内容，格式如下：\n'
        '{"sentiment": "positive" 或 "negative" 或 "neutral", '
        '"confidence": 0到1之间的数字, "reason": "一句话说明判断依据"}'
    )
    DEFAULT_BASE_URL = 'https://api.deepseek.com'
    DEFAULT_MODEL = 'deepseek-chat'

    def __init__(self, api_key: str, base_url: str = None, model: str = None,
                 timeout: int = 30, max_workers: int = 8):
        self.api_key = api_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip('/')
        self.model = model or self.DEFAULT_MODEL
        self.timeout = timeout
        self.max_workers = max_workers
        self._auth_broken = False  # 鉴权失效后整批降级，避免逐条无效重试
        self._conn_fail_count = 0  # 连续连接失败计数（偶发网络抖动不降级）

    @classmethod
    def from_env(cls) -> '_LLMAnalyzer':
        return cls(
            api_key=os.getenv('LLM_API_KEY', ''),
            base_url=os.getenv('LLM_BASE_URL'),
            model=os.getenv('LLM_MODEL'),
            timeout=int(os.getenv('LLM_TIMEOUT', '30')),
            max_workers=int(os.getenv('LLM_MAX_WORKERS', '8')),
        )

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def analyze_batch(self, texts: list) -> list:
        """并发逐条调用大模型，返回 [{'sentiment':..., 'score':...}]"""
        if not texts:
            return []
        if self._auth_broken:
            return [_DictionaryAnalyzer.analyze(t) for t in texts]
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            return list(pool.map(self._analyze_one, texts))

    def _analyze_one(self, text: str) -> dict:
        if self._auth_broken:
            return _DictionaryAnalyzer.analyze(text)
        try:
            content = self._call_api(text)
            self._conn_fail_count = 0  # 成功即重置
            return self._parse_result(content)
        except (requests.Timeout, requests.ConnectionError) as exc:
            # 网络/SSL 抖动多为偶发，连续多次失败才永久降级，避免误伤
            self._conn_fail_count += 1
            if self._conn_fail_count >= 3:
                self._auth_broken = True
                logger.warning('大模型连续连接失败 %d 次，后续整批降级为词典分析', self._conn_fail_count)
            else:
                logger.warning('大模型连接失败（%d/%d），该条降级为词典分析: %s',
                               self._conn_fail_count, 3, exc)
            return _DictionaryAnalyzer.analyze(text)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (401, 403):
                self._auth_broken = True
                logger.warning('大模型鉴权失败（HTTP %s），后续整批降级为词典分析', status)
            else:
                logger.warning('大模型请求失败（HTTP %s），该条降级为词典分析', status)
            return _DictionaryAnalyzer.analyze(text)
        except Exception as exc:
            logger.warning('大模型分析失败（%s），该条降级为词典分析: %s', self.model, exc)
            return _DictionaryAnalyzer.analyze(text)

    def _call_api(self, text: str) -> str:
        """调用 Chat Completions 接口，返回模型输出文本"""
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': self.SYSTEM_PROMPT},
                {'role': 'user', 'content': text},
            ],
            'temperature': 0,
            'max_tokens': 120,
            'response_format': {'type': 'json_object'},
        }
        resp = requests.post(
            f'{self.base_url}/chat/completions',
            headers={
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']

    @staticmethod
    def _parse_result(content: str) -> dict:
        """解析模型输出的 JSON，兼容 markdown 代码块围栏与中文极性标签"""
        text = content.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            raise ValueError(f'无法从输出中解析 JSON: {content[:100]!r}')
        data = json.loads(match.group(0))

        sentiment = str(data.get('sentiment', '')).strip().lower()
        if sentiment in ('pos', 'positive', '正面', '积极'):
            sentiment = 'positive'
        elif sentiment in ('neg', 'negative', '负面', '消极'):
            sentiment = 'negative'
        elif sentiment in ('neutral', '中性', '中立'):
            sentiment = 'neutral'
        else:
            raise ValueError(f'未知情感极性: {sentiment!r}')

        confidence = float(data.get('confidence', data.get('score', 0.9)))
        confidence = min(max(confidence, 0.0), 1.0)
        if sentiment == 'neutral':
            return {'sentiment': 'neutral', 'score': 0.0}
        return {
            'sentiment': sentiment,
            'score': round(confidence if sentiment == 'positive' else -confidence, 4),
        }


class SentimentService:
    """情感分析核心服务：大模型 → 预训练模型 → 词典，逐级降级"""

    _llm = None
    _use_llm = None
    _transformer = None
    _use_transformer = None

    @classmethod
    def _load_transformer(cls):
        """尝试加载预训练模型（仅在大模型不可用时执行）"""
        if cls._use_transformer is not None:
            return
        model_name = os.getenv(
            'SENTIMENT_MODEL_NAME',
            'lxyuan/distilbert-base-multilingual-cased-sentiments-student'
        )
        try:
            analyzer = _TransformerAnalyzer(model_name)
            if not analyzer.available:
                raise RuntimeError('transformers 不可用')
            analyzer.load()
            cls._transformer = analyzer
            cls._use_transformer = True
            logger.info('情感分析：已启用预训练模型 %s', model_name)
        except Exception as exc:
            cls._use_transformer = False
            logger.warning('预训练模型加载失败，降级为词典分析: %s', exc)

    @classmethod
    def _analyzer(cls):
        """确定使用的分析器：大模型（配置了 Key）→ 预训练模型 → 词典兜底"""
        if cls._use_llm is None:
            analyzer = _LLMAnalyzer.from_env()
            if analyzer.available:
                cls._llm = analyzer
                cls._use_llm = True
                logger.info('情感分析：已启用大模型 %s', analyzer.model)
            else:
                cls._use_llm = False
                cls._load_transformer()
        if cls._use_llm:
            return cls._llm
        return cls._transformer if cls._use_transformer else None

    @classmethod
    def backend_name(cls) -> str:
        cls._analyzer()
        if cls._use_llm:
            return 'llm'
        if cls._use_transformer:
            return 'transformer'
        return 'dictionary'

    @classmethod
    def analyze(cls, text: str) -> dict:
        """单条文本情感分析"""
        return cls.analyze_batch([text])[0]

    @classmethod
    def analyze_batch(cls, texts: list) -> list:
        """批量情感分析"""
        if not texts:
            return []
        analyzer = cls._analyzer()
        if analyzer is not None:
            try:
                return analyzer.analyze_batch(texts)
            except Exception as exc:
                logger.warning('分析器推理失败，本批次降级为词典分析: %s', exc)
        return [_DictionaryAnalyzer.analyze(t) for t in texts]

    @classmethod
    def extract_keywords(cls, text: str, top_k: int = 5) -> list:
        """TF-IDF 关键词提取，返回 [(word, weight), ...]"""
        return jieba.analyse.extract_tags(text, topK=top_k, withWeight=True)
