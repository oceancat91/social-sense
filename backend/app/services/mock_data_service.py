"""
多平台舆情模拟数据生成器。

模拟一个社会热点事件在 6 大平台上的完整生命周期：
- 跨平台传播时序：抖音首发 → 快手跟进 → 微博热搜 → B站/小红书 → 知乎深度讨论
- 事件生命周期：曝光期 → 发酵期（峰值）→ 回应/平息期
- 平台情绪极化：不同平台具有不同的情绪倾向分布
生成结果确定性可复现（以关键词为随机种子），便于演示与测试。
"""
import hashlib
import math
import random
from datetime import datetime, timedelta

# 各平台特征画像：进入时间、峰值时间、相对体量、情绪分布、内容模板
PLATFORM_PROFILES = {
    'douyin': {
        'source': '抖音短视频',
        'entry_day': 0.0,
        'peak_day': 2.5,
        'volume': 1.5,
        'sentiment_bias': {'positive': 0.30, 'neutral': 0.20, 'negative': 0.50},
        'main_type': 'video',
        'authors': ['阿强说事', '现场直击', '小城故事多', '街头观察员', '每日热闻', '大壮在路上'],
        'templates': {
            'negative': [
                '刚刚！{kw}{aspect}，看完真的怒了😡',
                '{kw}{aspect}，这也太离谱了吧，必须曝光',
                '气到发抖！{kw}{aspect}，大家一起顶上去',
            ],
            'positive': [
                '{kw}{aspect}，结局暖心！为正能量点赞👍',
                '{kw}{aspect}，看到这一幕真的感动了',
                '太棒了！{kw}{aspect}，社会还是好人多',
            ],
            'neutral': [
                '{kw}{aspect}，你们觉得呢？评论区聊聊',
                '{kw}{aspect}完整经过，先码后看',
                '{kw}{aspect}，蹲一个后续进展',
            ],
        },
    },
    'kuaishou': {
        'source': '快手',
        'entry_day': 0.5,
        'peak_day': 3.0,
        'volume': 0.8,
        'sentiment_bias': {'positive': 0.50, 'neutral': 0.20, 'negative': 0.30},
        'main_type': 'video',
        'authors': ['铁岭老四', '村头大树', '正能量主播阿珍', '隔壁老王', '乡里乡亲'],
        'templates': {
            'negative': [
                '老铁们评评理！{kw}{aspect}，这也太欺负人了',
                '{kw}{aspect}，看着真心疼，不能就这么算了',
            ],
            'positive': [
                '家人们，{kw}{aspect}，好人一生平安🙏',
                '{kw}{aspect}，为这样的处理结果点赞，痛快！',
            ],
            'neutral': [
                '{kw}{aspect}，有知道内情的老铁吗？',
                '{kw}{aspect}，大伙都来看看咋回事',
            ],
        },
    },
    'weibo': {
        'source': '微博',
        'entry_day': 1.0,
        'peak_day': 3.5,
        'volume': 1.3,
        'sentiment_bias': {'positive': 0.20, 'neutral': 0.25, 'negative': 0.55},
        'main_type': 'post',
        'authors': ['吃瓜群众小王', '圈内扒姐', '都市观察者', '热心市民刘先生', '娱乐八公', '财经李记者'],
        'templates': {
            'negative': [
                '真的气死，{kw}{aspect}看得我血压飙升，必须严惩！#{kw}#',
                '#{kw}# {aspect}，这种事情一而再再而三地发生，监管在哪里？',
                '出离愤怒！{kw}{aspect}，请给公众一个交代 #{kw}#',
                '#{kw}# {aspect}，太让人失望了，说好的底线呢？',
            ],
            'positive': [
                '#{kw}# {aspect}，看到这么多人关心这件事还是挺暖心的，希望能妥善处理',
                '值得肯定！{kw}{aspect}，这次响应速度很快 #{kw}#',
            ],
            'neutral': [
                '#{kw}# {aspect}，蹲一个后续，先不站队',
                '{kw}{aspect}，目前信息比较杂，等官方通报 #{kw}#',
                '#{kw}# {aspect}上热搜了，理性吃瓜',
            ],
        },
    },
    'bilibili': {
        'source': '哔哩哔哩',
        'entry_day': 2.0,
        'peak_day': 4.5,
        'volume': 0.9,
        'sentiment_bias': {'positive': 0.25, 'neutral': 0.35, 'negative': 0.40},
        'main_type': 'video',
        'authors': ['硬核观察室', '芝士君', '法外狂徒张三', '一键三连侠', '真相挖掘机'],
        'templates': {
            'negative': [
                '【锐评】{kw}{aspect}，这次真的忍不了',
                '深度扒一扒{kw}：{aspect}背后的离谱操作',
                '{kw}{aspect}？这届网友不答应',
            ],
            'positive': [
                '【暖心】{kw}{aspect}，这才是我们想看到的结局',
                '{kw}{aspect}，被这波操作圈粉了',
            ],
            'neutral': [
                '【深度解析】{kw}{aspect}始末，一期视频讲清楚',
                '{kw}时间线梳理：{aspect}，客观还原全过程',
                '关于{kw}，{aspect}，我们需要冷静思考这几个问题',
            ],
        },
    },
    'xiaohongshu': {
        'source': '小红书',
        'entry_day': 2.0,
        'peak_day': 5.0,
        'volume': 1.0,
        'sentiment_bias': {'positive': 0.50, 'neutral': 0.30, 'negative': 0.20},
        'main_type': 'post',
        'authors': ['一颗小甜豆', '橘子味的风', '生活研究员', '桃子气泡水', '自律的小姜'],
        'templates': {
            'negative': [
                '姐妹们避雷！{kw}{aspect}真的太离谱了😤',
                '{kw}{aspect}，看完真的会很生气，给大家提个醒',
            ],
            'positive': [
                '{kw}{aspect}，被狠狠治愈到了😭 人间值得',
                '{kw}{aspect}，这个处理方式真的很赞，分享给大家',
                '破防了家人们，{kw}{aspect}也太暖心了吧',
            ],
            'neutral': [
                '{kw}{aspect}，理性讨论一下这件事🤔',
                '{kw}{aspect}，大家怎么看？评论区聊聊',
            ],
        },
    },
    'zhihu': {
        'source': '知乎',
        'entry_day': 3.0,
        'peak_day': 5.5,
        'volume': 0.6,
        'sentiment_bias': {'positive': 0.20, 'neutral': 0.55, 'negative': 0.25},
        'main_type': 'post',
        'authors': ['王二哈', '匿名用户', 'Alex', '数据分析师小赵', '法律从业者老周', '社会学在读博士'],
        'templates': {
            'negative': [
                '如何看待{kw}？{aspect}反映出的深层问题值得警惕',
                '{kw}{aspect}。恕我直言，这件事暴露的监管漏洞不容忽视',
            ],
            'positive': [
                '如何看待{kw}？{aspect}中的积极信号不容忽视',
                '{kw}{aspect}，从行业角度看，这次的应对堪称教科书级别',
            ],
            'neutral': [
                '如何看待{kw}？梳理{aspect}的时间线，谈谈我的分析',
                '{kw}{aspect}。利益相关，从专业角度客观分析几点',
                '关于{kw}，{aspect}，建议大家先了解事实再下结论',
            ],
        },
    },
}

# 事件不同阶段的进展描述（注入模板 {aspect}）
PHASE_ASPECTS = {
    'exposure': ['现场视频流出', '当事人发声', '知情人爆料', '现场照片曝光'],
    'ferment': ['引发全网热议', '多方相继回应', '话题冲上热搜', '各方说法不一'],
    'aftermath': ['官方通报来了', '事件出现反转', '处理结果公布', '后续进展更新'],
}

# 评论类内容模板（content_type=comment）
COMMENT_TEMPLATES = {
    'negative': [
        '太离谱了，必须严查到底', '看得血压上来了，不能忍', '气愤！必须给个说法',
        '失望透顶，取关了', '这就是赤裸裸的欺骗', '底线呢？必须追责',
        '真的怒了，还有王法吗', '心疼当事人，太过分了', '这种事必须曝光，不能姑息',
        '看得我一阵恶寒，太可怕了', '一直在敷衍，根本没有诚意', '质疑官方的回应，避重就轻',
    ],
    'positive': [
        '支持！希望能妥善解决', '为处理速度点赞', '好人一生平安', '暖心，愿一切安好',
        '这个结果令人满意', '响应很迅速，值得肯定', '看到后续了，处理得很到位',
        '正能量满满，加油', '被这份善意治愈了', '必须赞一个，教科书式的应对',
        '向一线工作人员致敬', '希望以后越来越好',
    ],
    'neutral': [
        '蹲个后续', '理性吃瓜，等通报', '让子弹飞一会儿', '先观望一下',
        '有没有课代表总结一下', '信息量有点大，求梳理', '蹲一个时间线',
        '不清楚全貌，暂不评价', '等官方消息吧', '前排围观', '先码后看', '已转发给朋友求证',
    ],
}

# 评论随机后缀，提升内容多样性
COMMENT_SUFFIXES = ['', '。', '！', '…', '，无语', '，真的', '啊', '吧', '呢', '[吃瓜]', '[doge]', '🙏']


class MockDataGenerator:
    """多平台舆情模拟数据生成器"""

    SIGMA = 2.2  # 生命周期曲线宽度

    def __init__(self, keyword: str, days: int = 14, seed: int = None):
        self.keyword = keyword
        self.days = days
        if seed is None:
            seed = int(hashlib.md5(keyword.encode('utf-8')).hexdigest()[:8], 16)
        self.rng = random.Random(seed)
        self.end_date = datetime.now().replace(hour=23, minute=59, second=0, microsecond=0)

    def _daily_weight(self, profile: dict, day: int) -> float:
        """平台在第 day 天的相对声量：进入时间前静默，之后按高斯曲线衰减"""
        if day < profile['entry_day']:
            return 0.02
        peak = profile['peak_day']
        return math.exp(-((day - peak) ** 2) / (2 * self.SIGMA ** 2))

    def _phase_of(self, profile: dict, day: int) -> str:
        peak = profile['peak_day']
        if day < peak - 1:
            return 'exposure'
        if day <= peak + 1:
            return 'ferment'
        return 'aftermath'

    def _pick_sentiment(self, profile: dict) -> str:
        bias = profile['sentiment_bias']
        return self.rng.choices(
            list(bias.keys()), weights=list(bias.values()), k=1
        )[0]

    def _make_content(self, profile: dict, day: int, sentiment: str, content_type: str) -> str:
        if content_type == 'comment':
            text = self.rng.choice(COMMENT_TEMPLATES[sentiment])
            # 30% 概率带上事件指代，丰富评论语境
            if self.rng.random() < 0.3:
                aspect = self.rng.choice(PHASE_ASPECTS[self._phase_of(profile, day)])
                text = f'{self.keyword}{aspect}，{text}'
            return text + self.rng.choice(COMMENT_SUFFIXES)
        template = self.rng.choice(profile['templates'][sentiment])
        aspect = self.rng.choice(PHASE_ASPECTS[self._phase_of(profile, day)])
        return template.format(kw=self.keyword, aspect=aspect)

    def _make_engagement(self, profile: dict, day: int, content_type: str) -> dict:
        """互动指标：峰值期互动更高，评论低于主帖"""
        intensity = self._daily_weight(profile, day)
        base = self.rng.uniform(0.4, 1.0) * intensity * profile['volume'] * 5000
        if content_type == 'comment':
            base *= 0.15
        likes = int(base * self.rng.uniform(0.5, 1.5))
        return {
            'like_count': likes,
            'comment_count': int(likes * self.rng.uniform(0.05, 0.2)),
            'share_count': int(likes * self.rng.uniform(0.02, 0.12)),
        }

    def _allocate_counts(self, total: int, platforms: list) -> dict:
        """将总数据量按平台体量分配到目标平台"""
        volumes = {p: PLATFORM_PROFILES[p]['volume'] for p in platforms}
        volume_sum = sum(volumes.values())
        return {p: max(1, round(total * v / volume_sum)) for p, v in volumes.items()}

    def generate(self, total: int = 600, platforms: list = None) -> list:
        """
        生成模拟舆情数据。
        :param total: 目标数据总量
        :param platforms: 限定平台列表，默认全部平台
        :return: 原始舆情记录列表
        """
        records = []
        target_platforms = platforms or list(PLATFORM_PROFILES.keys())
        allocation = self._allocate_counts(total, target_platforms)

        for platform, profile in PLATFORM_PROFILES.items():
            if platform not in target_platforms:
                continue
            count = allocation[platform]

            # 按生命周期曲线将数据分配到每一天
            weights = [self._daily_weight(profile, d) for d in range(self.days)]
            weight_sum = sum(weights)
            day_counts = [round(c := count * w / weight_sum) or (1 if c > 0.5 else 0)
                          for w in weights]

            for day, n in enumerate(day_counts):
                for _ in range(n):
                    sentiment = self._pick_sentiment(profile)
                    content_type = (
                        profile['main_type'] if self.rng.random() < 0.7 else 'comment'
                    )
                    published = (
                        self.end_date
                        - timedelta(days=self.days - 1 - day)
                        + timedelta(
                            hours=self.rng.randint(0, 22),
                            minutes=self.rng.randint(0, 59),
                        )
                    )
                    records.append({
                        'platform': platform,
                        'content_type': content_type,
                        'content': self._make_content(profile, day, sentiment, content_type),
                        'source': profile['source'],
                        'author': self.rng.choice(profile['authors']),
                        'url': f'https://mock.{platform}.com/item/{self.rng.randint(10**9, 10**10)}',
                        'published_at': published,
                        'expected_sentiment': sentiment,
                        **self._make_engagement(profile, day, content_type),
                    })

        self.rng.shuffle(records)
        return records
