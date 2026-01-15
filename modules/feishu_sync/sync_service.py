"""
飞书多维表格同步服务 - 核心同步逻辑
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Optional

from .feishu_client import FeishuBitableClient
from .field_mapper import FieldMapper
from .sync_status import SyncStatusManager

logger = logging.getLogger(__name__)


class FeishuSyncService:
    """飞书多维表格同步服务"""

    def __init__(self):
        self.client = FeishuBitableClient()
        self.mapper = FieldMapper()
        self.status_manager = SyncStatusManager()

        # 表格配置（从环境变量读取）
        self.app_token = os.getenv('FEISHU_BITABLE_APP_TOKEN', '')
        self.table_ids = {
            'profiles': os.getenv('FEISHU_TABLE_PROFILES', ''),
            'sessions': os.getenv('FEISHU_TABLE_SESSIONS', ''),
            'messages': os.getenv('FEISHU_TABLE_MESSAGES', ''),
            'credit_logs': os.getenv('FEISHU_TABLE_CREDIT_LOGS', ''),
            'redeem_codes': os.getenv('FEISHU_TABLE_REDEEM_CODES', ''),
            'admin_logs': os.getenv('FEISHU_TABLE_ADMIN_LOGS', ''),
        }

    def is_enabled(self) -> bool:
        """检查飞书同步是否启用"""
        enabled = os.getenv('FEISHU_SYNC_ENABLED', 'true').lower() == 'true'
        has_config = bool(
            os.getenv('FEISHU_APP_ID') and
            os.getenv('FEISHU_APP_SECRET') and
            self.app_token
        )
        return enabled and has_config

    # ========================================
    # 实时同步（异步非阻塞）
    # ========================================

    def sync_profile_async(self, profile_data: Dict):
        """异步同步用户资料（不阻塞主线程）"""
        if not self.is_enabled():
            return

        try:
            fields = self.mapper.map_profile(profile_data)
            self.client.upsert_record_async(
                self.app_token,
                self.table_ids['profiles'],
                "用户ID",
                profile_data.get('id', ''),
                fields
            )
            logger.debug(f"[飞书同步] 异步同步用户资料: {profile_data.get('nickname', 'unknown')}")
        except Exception as e:
            logger.warning(f"[飞书同步] 用户资料同步失败: {e}")

    def sync_credit_log_async(self, log_data: Dict):
        """异步同步积分变动（不阻塞主线程）"""
        if not self.is_enabled():
            return

        try:
            fields = self.mapper.map_credit_log(log_data)
            self.client.insert_record_async(
                self.app_token,
                self.table_ids['credit_logs'],
                fields
            )
            logger.debug(f"[飞书同步] 异步同步积分变动: {log_data.get('amount', 0)}")
        except Exception as e:
            logger.warning(f"[飞书同步] 积分变动同步失败: {e}")

    def sync_redeem_code_async(self, code_data: Dict):
        """异步同步兑换码（不阻塞主线程）"""
        if not self.is_enabled():
            return

        try:
            fields = self.mapper.map_redeem_code(code_data)
            self.client.upsert_record_async(
                self.app_token,
                self.table_ids['redeem_codes'],
                "记录ID",
                code_data.get('id', ''),
                fields
            )
            logger.debug(f"[飞书同步] 异步同步兑换码: {code_data.get('code', 'unknown')}")
        except Exception as e:
            logger.warning(f"[飞书同步] 兑换码同步失败: {e}")

    # ========================================
    # 批量同步（定时任务）
    # ========================================

    def sync_sessions_incremental(self) -> int:
        """增量同步会话数据"""
        if not self.is_enabled():
            return 0

        try:
            from modules.supabase_client import get_admin
            supabase = get_admin()

            last_sync = self.status_manager.get_last_sync_time('sessions')

            query = supabase.table('sessions').select('*')
            if last_sync:
                query = query.gt('updated_at', last_sync)
            result = query.order('updated_at').limit(500).execute()

            if not result.data:
                return 0

            count = 0
            for session in result.data:
                fields = self.mapper.map_session(session)
                try:
                    self.client.upsert_record(
                        self.app_token,
                        self.table_ids['sessions'],
                        "会话ID",
                        session['id'],
                        fields
                    )
                    count += 1
                except Exception as e:
                    logger.warning(f"[飞书同步] 会话 {session['id']} 失败: {e}")

            if result.data:
                latest_time = max(r.get('updated_at', '') for r in result.data if r.get('updated_at'))
                if latest_time:
                    self.status_manager.update_last_sync_time('sessions', latest_time)

            logger.info(f"[飞书同步] 增量同步会话: {count} 条")
            return count

        except Exception as e:
            logger.error(f"[飞书同步] 会话增量同步失败: {e}")
            return 0

    def sync_admin_logs_incremental(self) -> int:
        """增量同步管理员日志"""
        if not self.is_enabled():
            return 0

        try:
            from modules.supabase_client import get_admin
            supabase = get_admin()

            last_sync = self.status_manager.get_last_sync_time('admin_logs')

            query = supabase.table('admin_logs').select('*')
            if last_sync:
                query = query.gt('created_at', last_sync)
            result = query.order('created_at').limit(500).execute()

            if not result.data:
                return 0

            records = [self.mapper.map_admin_log(log) for log in result.data]

            for i in range(0, len(records), 100):
                batch = records[i:i + 100]
                try:
                    self.client.batch_insert_records(
                        self.app_token,
                        self.table_ids['admin_logs'],
                        batch
                    )
                except Exception as e:
                    logger.warning(f"[飞书同步] 管理员日志批次失败: {e}")

            if result.data:
                latest_time = max(r.get('created_at', '') for r in result.data if r.get('created_at'))
                if latest_time:
                    self.status_manager.update_last_sync_time('admin_logs', latest_time)

            logger.info(f"[飞书同步] 增量同步管理员日志: {len(records)} 条")
            return len(records)

        except Exception as e:
            logger.error(f"[飞书同步] 管理员日志增量同步失败: {e}")
            return 0

    # ========================================
    # 全量同步（每日对账）
    # ========================================

    def full_sync_profiles(self) -> int:
        """全量同步用户资料"""
        if not self.is_enabled():
            return 0

        try:
            from modules.supabase_client import get_admin
            supabase = get_admin()

            result = supabase.table('profiles').select('*').execute()

            count = 0
            for profile in (result.data or []):
                try:
                    fields = self.mapper.map_profile(profile)
                    self.client.upsert_record(
                        self.app_token,
                        self.table_ids['profiles'],
                        "用户ID",
                        profile.get('id', ''),
                        fields
                    )
                    count += 1
                except Exception as e:
                    logger.warning(f"[飞书同步] 用户 {profile.get('id')} 同步失败: {e}")

            logger.info(f"[飞书同步] 全量同步用户资料: {count} 条")
            return count

        except Exception as e:
            logger.error(f"[飞书同步] 用户资料全量同步失败: {e}")
            return 0

    def full_sync_credit_logs(self) -> int:
        """全量同步积分日志"""
        if not self.is_enabled():
            return 0

        try:
            from modules.supabase_client import get_admin
            supabase = get_admin()

            result = supabase.table('credit_logs').select('*').execute()

            count = 0
            for log in (result.data or []):
                try:
                    fields = self.mapper.map_credit_log(log)
                    self.client.upsert_record(
                        self.app_token,
                        self.table_ids['credit_logs'],
                        "记录ID",
                        log.get('id', ''),
                        fields
                    )
                    count += 1
                except Exception as e:
                    logger.warning(f"[飞书同步] 积分日志 {log.get('id')} 同步失败: {e}")

            logger.info(f"[飞书同步] 全量同步积分日志: {count} 条")
            return count

        except Exception as e:
            logger.error(f"[飞书同步] 积分日志全量同步失败: {e}")
            return 0

    def full_sync_redeem_codes(self) -> int:
        """全量同步兑换码"""
        if not self.is_enabled():
            return 0

        try:
            from modules.supabase_client import get_admin
            supabase = get_admin()

            result = supabase.table('redeem_codes').select('*').execute()

            count = 0
            for code in (result.data or []):
                try:
                    fields = self.mapper.map_redeem_code(code)
                    self.client.upsert_record(
                        self.app_token,
                        self.table_ids['redeem_codes'],
                        "记录ID",
                        code.get('id', ''),
                        fields
                    )
                    count += 1
                except Exception as e:
                    logger.warning(f"[飞书同步] 兑换码 {code.get('id')} 同步失败: {e}")

            logger.info(f"[飞书同步] 全量同步兑换码: {count} 条")
            return count

        except Exception as e:
            logger.error(f"[飞书同步] 兑换码全量同步失败: {e}")
            return 0

    def full_sync_messages(self) -> int:
        """全量同步对话消息（从 sessions 表提取）"""
        if not self.is_enabled():
            return 0

        if not self.table_ids.get('messages'):
            logger.warning("[飞书同步] messages 表ID未配置，跳过消息同步")
            return 0

        try:
            from modules.supabase_client import get_admin
            supabase = get_admin()

            # 获取所有会话及其消息
            result = supabase.table('sessions').select('*').execute()

            total_count = 0
            batch_records = []

            for session in (result.data or []):
                messages = session.get('messages', [])
                if isinstance(messages, str):
                    try:
                        messages = json.loads(messages)
                    except:
                        messages = []

                if not messages or not isinstance(messages, list):
                    continue

                # 为每条消息创建记录
                for idx, msg in enumerate(messages):
                    try:
                        fields = self.mapper.map_message(msg, session, idx)
                        batch_records.append(fields)

                        # 每100条批量插入一次
                        if len(batch_records) >= 100:
                            try:
                                self.client.batch_insert_records(
                                    self.app_token,
                                    self.table_ids['messages'],
                                    batch_records
                                )
                                total_count += len(batch_records)
                                logger.info(f"[飞书同步] 已同步 {total_count} 条消息...")
                            except Exception as e:
                                logger.warning(f"[飞书同步] 批量插入消息失败: {e}")
                            batch_records = []

                    except Exception as e:
                        logger.warning(f"[飞书同步] 消息映射失败: {e}")

            # 处理剩余记录
            if batch_records:
                try:
                    self.client.batch_insert_records(
                        self.app_token,
                        self.table_ids['messages'],
                        batch_records
                    )
                    total_count += len(batch_records)
                except Exception as e:
                    logger.warning(f"[飞书同步] 最后批次消息插入失败: {e}")

            logger.info(f"[飞书同步] 全量同步消息: {total_count} 条")
            return total_count

        except Exception as e:
            logger.error(f"[飞书同步] 消息全量同步失败: {e}")
            return 0

    def full_sync_all(self) -> Dict[str, int]:
        """全量同步所有表"""
        return {
            'profiles': self.full_sync_profiles(),
            'credit_logs': self.full_sync_credit_logs(),
            'redeem_codes': self.full_sync_redeem_codes(),
            'sessions': self.sync_sessions_incremental(),
            'messages': self.full_sync_messages(),
            'admin_logs': self.sync_admin_logs_incremental(),
        }


# 单例
feishu_sync_service = FeishuSyncService()
