"""多 Agent 分析任务编排：DB 交互 + 后台线程 + 调用 agent_engine"""
import json
import logging
import threading

from app import db
from app.models.agent_report import AgentReport
from app.services.agent_engine import run_full_analysis

logger = logging.getLogger(__name__)


class AgentService:
    """跨平台多 Agent 分析任务服务"""

    @classmethod
    def run_in_background(cls, app, report_id: int):
        """后台线程执行分析，避免阻塞请求。"""
        thread = threading.Thread(
            target=cls._run, args=(app, report_id), daemon=True
        )
        thread.start()
        return thread

    @classmethod
    def _load_rows_by_platform(cls, report: AgentReport) -> dict[str, list]:
        """按平台分组加载该报告对应的 SentimentData 行。"""
        from app.models.sentiment import SentimentData
        from app.models.task import MonitorTask

        task_ids = [t.id for t in MonitorTask.query.filter_by(user_id=report.user_id).all()]
        query = SentimentData.query.filter(SentimentData.task_id.in_(task_ids or [-1]))
        if report.task_id:
            query = query.filter(SentimentData.task_id == report.task_id)

        rows_by_platform: dict[str, list] = {}
        for row in query.all():
            rows_by_platform.setdefault(row.platform, []).append(row)
        return rows_by_platform

    @classmethod
    def _run(cls, app, report_id: int) -> None:
        with app.app_context():
            report = db.session.get(AgentReport, report_id)
            if not report:
                logger.error('分析报告不存在: %s', report_id)
                return
            report.status = 'running'
            db.session.commit()

            try:
                rows_by_platform = cls._load_rows_by_platform(report)
                platforms = report.platform_list() or list(rows_by_platform.keys())
                result = run_full_analysis(
                    keyword=report.keyword,
                    platforms=platforms,
                    rows_by_platform=rows_by_platform,
                    use_llm=True,  # 引擎内部在无 LLM 时自动降级
                )
                report.result = json.dumps(result, ensure_ascii=False)
                ct = result.get('cross_platform') or {}
                report.status = (
                    'partial' if ct.get('CT_status') in ('failed_calibration', 'failed')
                    else 'success'
                )
                logger.info('分析报告 %s 完成: platforms=%s', report_id, platforms)
            except Exception as exc:  # noqa: BLE001
                db.session.rollback()
                report = db.session.get(AgentReport, report_id)
                if report:
                    report.status = 'failed'
                    report.error = str(exc)
                logger.exception('分析报告 %s 执行失败: %s', report_id, exc)
            finally:
                db.session.commit()
