"""情感分析服务测试"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app.services.sentiment_service import SentimentService, _DictionaryAnalyzer


class TestDictionaryAnalyzer:
    """词典情感分析器测试（确定性，不依赖预训练模型）"""

    def test_positive_text(self):
        result = _DictionaryAnalyzer.analyze('这个结果令人满意，必须点赞，太暖心了')
        assert result['sentiment'] == 'positive'
        assert result['score'] > 0

    def test_negative_text(self):
        result = _DictionaryAnalyzer.analyze('太离谱了，必须严查到底，让人愤怒')
        assert result['sentiment'] == 'negative'
        assert result['score'] < 0

    def test_neutral_text(self):
        result = _DictionaryAnalyzer.analyze('蹲一个后续，先观望一下')
        assert result['sentiment'] == 'neutral'
        assert result['score'] == 0.0

    def test_negation_flips_polarity(self):
        """否定词应翻转情感极性"""
        result = _DictionaryAnalyzer.analyze('这个处理结果不太好')
        assert result['sentiment'] == 'negative'

    def test_batch_consistency(self):
        texts = ['太好了', '太离谱了', '蹲后续']
        results = SentimentService.analyze_batch(texts)
        assert len(results) == 3
        assert all('sentiment' in r and 'score' in r for r in results)

    def test_keyword_extraction(self):
        keywords = SentimentService.extract_keywords('校园食品安全问题引发全网热议，官方通报来了')
        assert len(keywords) > 0
        words = [w for w, _ in keywords]
        assert any('食品' in w or '校园' in w for w in words)
