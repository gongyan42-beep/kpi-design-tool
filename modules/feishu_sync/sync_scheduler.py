"""
定时任务调度 - 管理增量同步和全量对账任务
"""
import os
import logging
from threading import Thread
import time

logger = logging.getLogger(__name__)


class FeishuSyncScheduler:
    """飞书同步定时任务调度器（简化版，使用线程）"""

    def __init__(self):
        self._is_started = False
        self._stop_flag = False
        self._thread = None

    def _run_scheduler(self):
        """调度器主循环"""
        from .sync_service import feishu_sync_service

        if not feishu_sync_service.is_enabled():
            logger.info("[飞书同步] 未配置飞书 API，跳过定时任务")
            return

        logger.info("[飞书同步] 定时任务调度器已启动")

        # 计数器
        interval_count = 0  # 5分钟间隔计数
        daily_synced = False  # 今日是否已全量同步

        while not self._stop_flag:
            try:
                time.sleep(60)  # 每分钟检查一次
                interval_count += 1

                # 每1分钟执行消息增量同步
                try:
                    feishu_sync_service.sync_messages_incremental()
                except Exception as e:
                    logger.debug(f"[飞书同步] 消息增量同步: {e}")

                # 每5分钟执行会话和日志增量同步
                if interval_count >= 5:
                    interval_count = 0
                    try:
                        feishu_sync_service.sync_sessions_incremental()
                        feishu_sync_service.sync_admin_logs_incremental()
                    except Exception as e:
                        logger.warning(f"[飞书同步] 增量同步失败: {e}")

                # 每天凌晨3点执行全量同步
                current_hour = time.localtime().tm_hour
                if current_hour == 3 and not daily_synced:
                    try:
                        feishu_sync_service.full_sync_profiles()
                        daily_synced = True
                        logger.info("[飞书同步] 每日全量同步完成")
                    except Exception as e:
                        logger.warning(f"[飞书同步] 全量同步失败: {e}")
                elif current_hour != 3:
                    daily_synced = False

            except Exception as e:
                logger.error(f"[飞书同步] 调度器错误: {e}")

    def start(self):
        """启动调度器"""
        if self._is_started:
            return

        # 检查是否启用
        if os.getenv('FEISHU_SYNC_ENABLED', 'true').lower() != 'true':
            logger.info("[飞书同步] 同步已禁用")
            return

        self._stop_flag = False
        self._thread = Thread(target=self._run_scheduler, daemon=True)
        self._thread.start()
        self._is_started = True

    def stop(self):
        """停止调度器"""
        if self._is_started:
            self._stop_flag = True
            self._is_started = False


# 单例
feishu_sync_scheduler = FeishuSyncScheduler()
