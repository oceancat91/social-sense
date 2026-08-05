"""情感分析服务：预训练模型优先，词典分析兜底"""
import logging
import os

import jieba
import jieba.analyse

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


class SentimentService:
    """情感分析核心服务：优先使用预训练模型，不可用时降级为词典分析"""

    _transformer = None
    _use_transformer = None

    @classmethod
    def _analyzer(cls):
        """确定使用的分析器：transformer 模型可用则用，否则词典兜底"""
        if cls._use_transformer is None:
            model_name = os.getenv(
                'SENTIMENT_MODEL_NAME',
                'lxyuan/distilbert-base-multilingual-cased-sentiments-student'
            )
            try:
                analyzer = _TransformerAnalyzer(model_name)
                if analyzer.available:
                    analyzer.load()
                    cls._transformer = analyzer
                    cls._use_transformer = True
                    logger.info('情感分析：已启用预训练模型 %s', model_name)
                else:
                    raise RuntimeError('transformers 不可用')
            except Exception as exc:
                cls._use_transformer = False
                logger.warning('预训练模型加载失败，降级为词典分析: %s', exc)
        return cls._transformer if cls._use_transformer else None

    @classmethod
    def backend_name(cls) -> str:
        cls._analyzer()
        return 'transformer' if cls._use_transformer else 'dictionary'

    @classmethod
    def analyze(cls, text: str) -> dict:
        """单条文本情感分析"""
        return cls.analyze_batch([text])[0]

    @classmethod
    def analyze_batch(cls, texts: list) -> list:
        """批量情感分析"""
        if not texts:
            return []
        transformer = cls._analyzer()
        if transformer is not None:
            try:
                return transformer.analyze_batch(texts)
            except Exception as exc:
                logger.warning('模型推理失败，本批次降级为词典分析: %s', exc)
        return [_DictionaryAnalyzer.analyze(t) for t in texts]

    @classmethod
    def extract_keywords(cls, text: str, top_k: int = 5) -> list:
        """TF-IDF 关键词提取，返回 [(word, weight), ...]"""
        return jieba.analyse.extract_tags(text, topK=top_k, withWeight=True)
