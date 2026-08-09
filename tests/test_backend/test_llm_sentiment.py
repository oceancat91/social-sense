"""大模型情感分析器测试（mock HTTP 调用，不真实请求 API）"""
import sys
import os
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app.services.sentiment_service import _LLMAnalyzer


def _make_response(content: str):
    resp = mock.Mock()
    resp.json.return_value = {'choices': [{'message': {'content': content}}]}
    return resp


class TestLLMAnalyzer:
    """_LLMAnalyzer 解析与调用逻辑测试"""

    def setup_method(self):
        self.analyzer = _LLMAnalyzer(api_key='sk-test')

    def test_available_requires_key(self):
        assert _LLMAnalyzer(api_key='').available is False
        assert _LLMAnalyzer(api_key='sk-x').available is True

    def test_default_endpoint(self):
        assert self.analyzer.base_url == 'https://api.deepseek.com'
        assert self.analyzer.model == 'deepseek-chat'

    def test_parse_positive(self):
        result = self.analyzer._parse_result('{"sentiment": "positive", "confidence": 0.95}')
        assert result['sentiment'] == 'positive'
        assert result['score'] == 0.95

    def test_parse_negative(self):
        result = self.analyzer._parse_result('{"sentiment": "negative", "confidence": 0.9}')
        assert result['sentiment'] == 'negative'
        assert result['score'] == -0.9

    def test_parse_neutral(self):
        result = self.analyzer._parse_result('{"sentiment": "neutral", "confidence": 0.7}')
        assert result['sentiment'] == 'neutral'
        assert result['score'] == 0.0

    def test_parse_markdown_fence(self):
        result = self.analyzer._parse_result('```json\n{"sentiment": "negative"}\n```')
        assert result['sentiment'] == 'negative'

    def test_parse_chinese_label(self):
        result = self.analyzer._parse_result('{"sentiment": "正面", "confidence": 0.8}')
        assert result['sentiment'] == 'positive'

    def test_parse_invalid_output_raises(self):
        import pytest
        with pytest.raises(Exception):
            self.analyzer._parse_result('我不是JSON')

    def test_analyze_batch_calls_api(self):
        with mock.patch('app.services.sentiment_service.requests.post') as mock_post:
            mock_post.side_effect = [
                _make_response('{"sentiment": "positive", "confidence": 0.9}'),
                _make_response('{"sentiment": "negative", "confidence": 0.8}'),
            ]
            results = self.analyzer.analyze_batch(['太好了', '太离谱了'])
            assert [r['sentiment'] for r in results] == ['positive', 'negative']
            assert mock_post.call_count == 2

    def test_single_failure_falls_back_to_dictionary(self):
        """单条 API 失败时该条降级为词典分析，不影响其他条"""
        with mock.patch('app.services.sentiment_service.requests.post') as mock_post:
            mock_post.side_effect = [
                RuntimeError('network error'),
                _make_response('{"sentiment": "positive", "confidence": 0.9}'),
            ]
            results = self.analyzer.analyze_batch(['太离谱了', '太好了'])
            assert results[0]['sentiment'] == 'negative'  # 词典兜底
            assert results[1]['sentiment'] == 'positive'
