"""数据采集服务：统一采集接口，当前由模拟数据源驱动"""
import logging

from app.services.mock_data_service import MockDataGenerator, PLATFORM_PROFILES

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = list(PLATFORM_PROFILES.keys())


class CrawlerService:
    """
    社交媒体数据采集服务。

    当前阶段所有平台均由模拟数据源驱动（data_source='mock'），
    真实采集器预留接口，接入合规数据源后可按平台逐步替换。
    """

    @staticmethod
    def crawl_weibo(keyword: str, **kwargs) -> list:
        """微博真实采集器（预留）。接入需使用微博开放平台或合规数据服务。"""
        # TODO: 接入真实微博数据源
        return []

    @staticmethod
    def crawl_zhihu(keyword: str, **kwargs) -> list:
        """知乎真实采集器（预留）。"""
        # TODO: 接入真实知乎数据源
        return []

    @classmethod
    def crawl(cls, keyword: str, platform: str = 'all',
              days: int = 14, limit: int = 600) -> list:
        """
        按平台采集关键词相关舆情数据。
        :param keyword: 监控关键词（事件主题）
        :param platform: 平台标识，'all' 表示全平台
        :param days: 回溯天数（模拟事件的时间跨度）
        :param limit: 数据量上限
        """
        platforms = SUPPORTED_PLATFORMS if platform == 'all' else [platform]
        invalid = [p for p in platforms if p not in SUPPORTED_PLATFORMS]
        if invalid:
            raise ValueError(f'不支持的平台: {invalid}')

        generator = MockDataGenerator(keyword=keyword, days=days)
        records = generator.generate(total=limit, platforms=platforms)
        logger.info('采集完成: keyword=%s platform=%s raw=%d', keyword, platform, len(records))
        return records
