"""多 Agent 分析任务编排：采集 + DB 交互 + 后台线程 + 调用 agent_engine"""
import json
import logging
import threading

from app import db
from app.constants import PLATFORMS
from app.models.agent_report import AgentReport
from app.models.sentiment import SentimentData
from app.models.task import MonitorTask
from app.services.agent_engine import run_full_analysis
from app.services.pipeline_service import PipelineService

logger = logging.getLogger(__name__)

# 分析阶段定义：phase -> (序号, 中文名)。前端据此渲染步骤条。
PHASES = {
    'collect': (1, '采集舆情数据'),
    'clean': (2, '清洗与情感分析'),
    'skill': (3, '单平台 Agent 分析'),
    'fusion': (4, '跨平台对齐融合'),
}
PHASE_TOTAL = len(PHASES)


def _platform_name(code: str) -> str:
    return (PLATFORMS.get(code) or {}).get('name', code)


class AgentService:
    """跨平台多 Agent 分析任务服务：支持「采集并分析」一体化。

    流程：采集（真实优先 / mock 兜底）→ 入库 SentimentData → 跨平台分析。
    各阶段实时写入 report.progress，供前端步骤条/进度条呈现。
    """

    @classmethod
    def run_in_background(cls, app, report_id: int, *, days: int = 14):
        """后台线程：先采集，再跨平台分析。"""
        thread = threading.Thread(
            target=cls._run_collect_and_analyze, args=(app, report_id, days), daemon=True
        )
        thread.start()
        return thread

    # ------------------------------------------------------------------ #
    # 进度
    # ------------------------------------------------------------------ #

    @classmethod
    def _set_progress(cls, report_id: int, phase: str, percent: int,
                      detail: str = '', platform_status: dict | None = None) -> None:
        """把结构化进度写回 report.progress（用 update 语句，避免会话对象冲突）。"""
        idx, _ = PHASES.get(phase, (1, phase))
        payload = {
            'phase': phase,
            'phase_index': idx,
            'phase_total': PHASE_TOTAL,
            'percent': max(0, min(100, int(percent))),
            'detail': detail,
            'platform_status': platform_status or {},
        }
        db.session.query(AgentReport).filter_by(id=report_id).update(
            {'progress': json.dumps(payload, ensure_ascii=False)}
        )
        db.session.commit()

    # ------------------------------------------------------------------ #
    # 数据加载
    # ------------------------------------------------------------------ #

    @classmethod
    def _load_rows_by_platform(cls, report: AgentReport) -> dict[str, list]:
        """按平台分组加载该报告对应的 SentimentData 行。"""
        if report.task_id:
            query = SentimentData.query.filter(SentimentData.task_id == report.task_id)
        else:
            task_ids = [t.id for t in MonitorTask.query.filter_by(user_id=report.user_id).all()]
            query = SentimentData.query.filter(SentimentData.task_id.in_(task_ids or [-1]))

        rows_by_platform: dict[str, list] = {}
        for row in query.all():
            rows_by_platform.setdefault(row.platform, []).append(row)
        return rows_by_platform

    # ------------------------------------------------------------------ #
    # 采集
    # ------------------------------------------------------------------ #

    @classmethod
    def _collect_for_report(cls, report: AgentReport, days: int, limit: int,
                            platforms: list) -> None:
        """为报告采集数据：创建多平台任务，采集并入库（真实优先 / mock 兜底）。"""
        keyword = report.keyword
        # 'all' 或空列表展开为全部支持平台，保证进度按真实平台粒度推进
        if not platforms or 'all' in platforms:
            from app.services.crawler_service import SUPPORTED_PLATFORMS
            platforms = list(SUPPORTED_PLATFORMS)
        platform_field = ','.join(platforms) if len(platforms) > 1 else platforms[0]

        task = MonitorTask(
            user_id=report.user_id,
            keywords=keyword,
            platform=platform_field,
            status='collecting',
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id
        report.task_id = task_id
        db.session.commit()

        total = len(platforms)
        platform_status = {p: 'pending' for p in platforms}

        def on_platform(p, state):
            platform_status[p] = state
            done = sum(1 for s in platform_status.values() if s == 'done')
            if state == 'running':
                detail = f"正在采集 {_platform_name(p)}（{done + 1}/{total}）"
            else:
                detail = f"{_platform_name(p)} 采集完成（{done}/{total}）"
            cls._set_progress(report.id, 'collect', int(done / total * 45),
                              detail, dict(platform_status))

        def on_phase(phase):
            if phase == 'clean':
                cls._set_progress(report.id, 'clean', 50, '正在清洗去重并做情感分析')
            elif phase == 'sentiment':
                cls._set_progress(report.id, 'clean', 55, '情感分析与关键词提取中')

        try:
            stats = PipelineService._execute(
                task, keyword, days, limit,
                progress_cb=on_platform, phase_cb=on_phase,
            )
            task.status = 'active'
            task.data_count = SentimentData.query.filter_by(task_id=task_id).count()
            db.session.commit()
            logger.info('报告 %s 采集完成: keyword=%s platforms=%s stats=%s',
                        report.id, keyword, platform_field, stats)
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            # 用已捕获的 task_id 重新加载，避免对已过期/被删除对象取 .id
            task = db.session.get(MonitorTask, task_id)
            if task:
                task.status = 'active'
                db.session.commit()
            logger.exception('报告 %s 采集失败: %s', report.id, exc)
            raise

    # ------------------------------------------------------------------ #
    # 分析
    # ------------------------------------------------------------------ #

    @classmethod
    def _analyze_report(cls, report: AgentReport) -> None:
        """基于已入库数据执行跨平台分析，写回结果与状态。"""
        rows_by_platform = cls._load_rows_by_platform(report)
        platforms = report.platform_list() or list(rows_by_platform.keys())
        total = len(platforms)

        def on_platform(p, done_index, _total):
            percent = 55 + int(done_index / total * 40)
            cls._set_progress(
                report.id, 'skill', percent,
                f"{_platform_name(p)} Agent 分析完成（{done_index}/{total}）",
                {p: 'done'},
            )

        cls._set_progress(report.id, 'skill', 55, '各平台 Agent 正在分析（Skill2-6）')

        result = run_full_analysis(
            keyword=report.keyword,
            platforms=platforms,
            rows_by_platform=rows_by_platform,
            use_llm=True,  # 引擎内部在无 LLM 时自动降级
            progress_cb=on_platform,
        )

        cls._set_progress(report.id, 'fusion', 95, '跨平台对齐融合与校准门禁中')

        report.result = json.dumps(result, ensure_ascii=False)
        ct = result.get('cross_platform') or {}
        report.status = (
            'partial' if ct.get('CT_status') in ('failed_calibration', 'failed')
            else 'success'
        )
        cls._set_progress(report.id, 'fusion', 100, '分析完成')
        logger.info('分析报告 %s 完成: platforms=%s', report.id, platforms)

    # ------------------------------------------------------------------ #
    # 后台主流程
    # ------------------------------------------------------------------ #

    @classmethod
    def _run_collect_and_analyze(cls, app, report_id: int, days: int) -> None:
        with app.app_context():
            report = db.session.get(AgentReport, report_id)
            if not report:
                logger.error('分析报告不存在: %s', report_id)
                return
            limit = int(app.config.get('CRAWL_MAX_RECORDS', 600))
            try:
                platforms = report.platform_list() or ['all']
                report.status = 'collecting'
                db.session.commit()

                cls._collect_for_report(report, days, limit, platforms)

                report.status = 'running'
                db.session.commit()
                cls._analyze_report(report)
            except Exception as exc:  # noqa: BLE001
                db.session.rollback()
                report = db.session.get(AgentReport, report_id)
                if report:
                    report.status = 'failed'
                    report.error = str(exc)
                logger.exception('报告 %s 采集分析失败: %s', report_id, exc)
            finally:
                db.session.commit()
