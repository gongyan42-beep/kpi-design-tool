"""
字段映射转换 - 将数据库字段转换为飞书多维表格字段
"""
import json
from datetime import datetime
from typing import Dict, Any, Optional


class FieldMapper:
    """字段映射转换器"""

    @staticmethod
    def _format_datetime(dt_str: Optional[str]) -> Optional[int]:
        """将 ISO 时间字符串转换为飞书时间戳（毫秒）"""
        if not dt_str:
            return None
        try:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            return int(dt.timestamp() * 1000)
        except:
            return None

    @staticmethod
    def _truncate_text(text: str, max_len: int = 50000) -> str:
        """截断文本"""
        if not text:
            return ""
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + "..."

    @staticmethod
    def _json_to_text(data: Any, max_len: int = 5000) -> str:
        """将 JSON 数据转换为可读文本"""
        if not data:
            return ""
        try:
            if isinstance(data, str):
                data = json.loads(data)
            text = json.dumps(data, ensure_ascii=False, indent=2)
            return FieldMapper._truncate_text(text, max_len)
        except:
            return str(data)[:max_len]

    def map_profile(self, profile: Dict) -> Dict:
        """映射用户资料"""
        return {
            "用户ID": profile.get('id', ''),
            "昵称": profile.get('nickname', ''),
            "公司": profile.get('company', ''),
            "手机号": profile.get('phone', ''),
            "积分余额": profile.get('credits', 0),
            "猫币": profile.get('cat_coins', 0),
            "用户类型": profile.get('user_type', 'normal'),
            "创建时间": self._format_datetime(profile.get('created_at')),
            "更新时间": self._format_datetime(profile.get('updated_at')),
        }

    def map_session(self, session: Dict) -> Dict:
        """映射对话会话"""
        messages = session.get('messages', [])
        if isinstance(messages, str):
            try:
                messages = json.loads(messages)
            except:
                messages = []

        return {
            "会话ID": session.get('id', ''),
            "模块": session.get('module', ''),
            "用户ID": session.get('user_id', ''),
            "用户邮箱": session.get('user_email', ''),
            "状态": session.get('status', 'in_progress'),
            "消息数量": len(messages) if isinstance(messages, list) else 0,
            "创建时间": self._format_datetime(session.get('created_at')),
            "更新时间": self._format_datetime(session.get('updated_at')),
        }

    def map_credit_log(self, log: Dict) -> Dict:
        """映射积分变动"""
        return {
            "记录ID": str(log.get('id', '')),  # 确保转为字符串
            "用户ID": str(log.get('user_id', '')),
            "变动金额": log.get('amount', 0),
            "变动后余额": log.get('balance', 0),
            "原因": str(log.get('reason', '')),
            "创建时间": self._format_datetime(log.get('created_at')),
        }

    def map_redeem_code(self, code: Dict) -> Dict:
        """映射兑换码"""
        return {
            "记录ID": str(code.get('id', '')),
            "兑换码": str(code.get('code', '')),
            "目标用户": str(code.get('target_name', '')),
            "积分": code.get('credits', 0),
            "猫币": code.get('cat_coins', 0),
            "创建人": str(code.get('created_by', '')),
            "备注": str(code.get('note', '')),
            "是否使用": code.get('is_used', False),
            "使用时间": self._format_datetime(code.get('used_at')),
            "使用者ID": str(code.get('used_by_user_id', '') or ''),
            "创建时间": self._format_datetime(code.get('created_at')),
        }

    def map_admin_log(self, log: Dict) -> Dict:
        """映射管理员日志"""
        return {
            "记录ID": str(log.get('id', '')),
            "管理员": str(log.get('admin_name', '')),
            "操作类型": str(log.get('action_type', 'OTHER')),
            "操作目标": str(log.get('target', '') or log.get('target_name', '')),
            "详情": str(log.get('description', '') or log.get('details', '')),
            "创建时间": self._format_datetime(log.get('created_at')),
        }

    def map_message(self, message: Dict, session: Dict, index: int, user_profile: Dict = None) -> Dict:
        """映射单条对话消息（包含用户详细信息）"""
        # 生成消息ID：会话ID + 序号
        session_id = session.get('id', '')
        message_id = f"{session_id}_{index:04d}"

        # 获取消息时间（优先用消息自带的时间，否则用会话创建时间）
        msg_time = message.get('time') or message.get('timestamp')
        if not msg_time:
            msg_time = session.get('created_at')

        # 用户信息（从 profiles 表关联）
        user_nickname = ''
        user_company = ''
        user_phone = ''
        if user_profile:
            user_nickname = user_profile.get('nickname', '') or ''
            user_company = user_profile.get('company', '') or ''
            user_phone = user_profile.get('phone', '') or ''

        return {
            "消息ID": message_id,
            "会话ID": session_id,
            "用户邮箱": session.get('user_email', '') or '',
            "用户昵称": user_nickname,
            "公司": user_company,
            "手机号": user_phone,
            "模块": session.get('module', ''),
            "角色": message.get('role', 'user'),
            "消息内容": self._truncate_text(message.get('content', ''), 50000),
            "消息时间": self._format_datetime(msg_time) if msg_time else None,
        }
