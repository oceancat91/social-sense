"""数据采集服务：优先真实采集（agent PlatformAdapter），失败/无 cookie 回退 mock"""
import logging

from app.services.mock_data_service import MockDataGenerator, PLATFORM_PROFILES
from app.services.real_crawler_bridge import RealCrawlUnavailable, collect

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = list(PLATFORM_PROFILES.keys())


class CrawlerService:
    """
    社交媒体数据采集服务。

    采集策略（按平台）：
      1) 优先走 agent/PlatformCrawler 的真实采集适配器（需配置各平台 cookie）；
      2) 缺 cookie 或采集失败时，回退到 mock 数据源（data_source='mock'），
         保证监控任务与多 Agent 引擎在无凭证环境下仍可端到端演示。
    """

    @staticmethod
    def _try_real_crawl(keyword: str, platform: str, days: int, limit: int) -> list:
        """尝试真实采集；不可用则返回 None（由调用方回退 mock）。"""
        try:
            records = collect(keyword, platform, days=days, limit=limit)
            if records:
                return records
            logger.info('平台 %s 真实采集返回空，回退 mock', platform)
            return []
        except RealCrawlUnavailable as e:
            logger.info('平台 %s 真实采集不可用，回退 mock: %s', platform, e)
            return []
        except Exception as e:  # noqa: BLE001
            logger.warning('平台 %s 真实采集异常，回退 mock: %s', platform, e)
            return []

    @classmethod
    def crawl(cls, keyword: str, platform: str = 'all',
              days: int = 14, limit: int = 600, progress_cb=None) -> list:
        """
        按平台采集关键词相关舆情数据。
        :param keyword: 监控关键词（事件主题）
        :param platform: 平台标识，'all' 表示全平台
        :param days: 回溯天数
        :param limit: 数据量上限
        :param progress_cb: 可选进度回调 progress_cb(platform, state)，
            state 为 'running'（开始采集）或 'done'（采集结束，含 mock 兜底）。
        """
        if platform == 'all':
            platforms = SUPPORTED_PLATFORMS
        else:
            # 支持逗号分隔的多平台（如 'bilibili,weibo,xiaohongshu'）
            platforms = [p.strip().lower() for p in str(platform).split(',') if p.strip()]
        invalid = [p for p in platforms if p not in SUPPORTED_PLATFORMS]
        if invalid:
            raise ValueError(f'不支持的平台: {invalid}')

        records: list = []
        real_count = 0
        mock_platforms: list = []
        for p in platforms:
            if progress_cb:
                progress_cb(p, 'running')
            real = cls._try_real_crawl(keyword, p, days=days, limit=limit)
            if real:
                records.extend(real)
                real_count += len(real)
            else:
                mock_platforms.append(p)
            if progress_cb:
                progress_cb(p, 'done')

        if mock_platforms:
            generator = MockDataGenerator(keyword=keyword, days=days)
            records.extend(generator.generate(total=limit, platforms=mock_platforms))

        logger.info(
            '采集完成: keyword=%s platforms=%s raw=%d real=%d mock=%d',
            keyword, platforms, len(records), real_count, len(records) - real_count,
        )
        return records
