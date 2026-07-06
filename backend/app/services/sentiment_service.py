"""情感分析服务"""
import jieba


class SentimentService:
    """情感分析核心服务"""

    POSITIVE_WORDS = {'好', '棒', '优秀', '喜欢', '支持', '赞', '不错', '满意', '开心', '感谢'}
    NEGATIVE_WORDS = {'差', '烂', '垃圾', '讨厌', '反对', '失望', '糟糕', '愤怒', '难过', '骗'}

    @classmethod
    def analyze(cls, text: str) -> dict:
        """
        对文本进行简单的情感分析。
        实际项目中应使用预训练模型（如 BERT）以获得更高准确率。
        """
        words = jieba.lcut(text)

        pos_count = sum(1 for w in words if w in cls.POSITIVE_WORDS)
        neg_count = sum(1 for w in words if w in cls.NEGATIVE_WORDS)

        if pos_count > neg_count:
            sentiment = 'positive'
            score = min(pos_count / max(len(words), 1), 1.0)
        elif neg_count > pos_count:
            sentiment = 'negative'
            score = -min(neg_count / max(len(words), 1), 1.0)
        else:
            sentiment = 'neutral'
            score = 0.0

        return {
            'sentiment': sentiment,
            'score': round(score, 4),
            'word_count': len(words)
        }

    @classmethod
    def extract_keywords(cls, text: str, top_k: int = 10) -> list:
        """提取关键词"""
        import jieba.analyse
        return jieba.analyse.extract_tags(text, topK=top_k, withWeight=True)
