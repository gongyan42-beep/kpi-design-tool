"""
管理员操作日志服务 - 记录管理员的所有操作
"""
from datetime import datetime
from typing import Dict, List, Optional
from modules.supabase_client import get_client


class AdminLogService:
    """管理员操作日志服务"""

    # 操作类型
    ACTION_TYPES = {
        'PROMPT_CREATE': '新增提示词',
        'PROMPT_UPDATE': '修改提示词',
        'PROMPT_DELETE': '删除提示词',
        'MODULE_CREATE': '新增模块',
        'MODULE_UPDATE': '修改模块',
        'MODULE_DELETE': '删除模块',
        'REDEEM_CREATE': '创建兑换码',
        'REDEEM_DELETE': '删除兑换码',
        'REDEEM_USED': '用户兑换',
        'CREDITS_ADD': '充值积分',
        'KNOWLEDGE_UPLOAD': '上传知识库',
        'KNOWLEDGE_DELETE': '删除知识库',
    }

    def __init__(self):
        self.client = get_client()

    def log(self, admin_name: str, action_type: str, target: str, details: str = '', extra_data: Dict = None) -> bool:
        """
        记录管理员操作日志

        Args:
            admin_name: 管理员名称
            action_type: 操作类型（参见 ACTION_TYPES）
            target: 操作目标（如模块名、用户名等）
            details: 详细描述
            extra_data: 额外数据（JSON 格式存储）
        """
        if not self.client:
            print(f"[AdminLog] 无数据库连接: {admin_name} {action_type} {target}")
            return False

        try:
            log_data = {
                'admin_name': admin_name,
                'action_type': action_type,
                'action_name': self.ACTION_TYPES.get(action_type, action_type),
                'target': target,
                'details': details,
                'extra_data': extra_data,
                'created_at': datetime.now().isoformat()
            }

            self.client.table('admin_logs').insert(log_data).execute()
            print(f"[AdminLog] {admin_name} {self.ACTION_TYPES.get(action_type, action_type)}: {target}")
            return True
        except Exception as e:
            print(f"[AdminLog] 记录日志失败: {e}")
            return False

    def log_prompt_create(self, admin_name: str, module_name: str, prompt_preview: str = ''):
        """记录新增提示词"""
        return self.log(
            admin_name=admin_name,
            action_type='PROMPT_CREATE',
            target=module_name,
            details=f"新增提示词，内容预览: {prompt_preview[:100]}..." if len(prompt_preview) > 100 else prompt_preview
        )

    def log_prompt_update(self, admin_name: str, module_name: str, prompt_preview: str = ''):
        """记录修改提示词"""
        return self.log(
            admin_name=admin_name,
            action_type='PROMPT_UPDATE',
            target=module_name,
            details=f"修改提示词，新内容预览: {prompt_preview[:100]}..." if len(prompt_preview) > 100 else prompt_preview
        )

    def log_prompt_delete(self, admin_name: str, module_name: str):
        """记录删除提示词"""
        return self.log(
            admin_name=admin_name,
            action_type='PROMPT_DELETE',
            target=module_name,
            details=f"删除模块 {module_name} 的提示词"
        )

    def log_module_create(self, admin_name: str, module_id: str, module_name: str):
        """记录新增模块"""
        return self.log(
            admin_name=admin_name,
            action_type='MODULE_CREATE',
            target=module_name,
            details=f"新增模块: {module_name} (ID: {module_id})"
        )

    def log_module_delete(self, admin_name: str, module_id: str, module_name: str):
        """记录删除模块"""
        return self.log(
            admin_name=admin_name,
            action_type='MODULE_DELETE',
            target=module_name,
            details=f"删除模块: {module_name} (ID: {module_id})"
        )

    def log_redeem_create(self, admin_name: str, target_name: str, cat_coins: int, credits: int, code: str):
        """记录创建兑换码"""
        return self.log(
            admin_name=admin_name,
            action_type='REDEEM_CREATE',
            target=target_name,
            details=f"为 {target_name} 创建兑换码，{cat_coins}个猫币兑换{credits}积分",
            extra_data={
                'cat_coins': cat_coins,
                'credits': credits,
                'code': code
            }
        )

    def log_batch_redeem_create(self, admin_name: str, count: int, credits: int):
        """记录批量创建兑换码"""
        return self.log(
            admin_name=admin_name,
            action_type='REDEEM_CREATE',
            target=f'批量生成{count}个',
            details=f"批量生成 {count} 个兑换码，每个 {credits} 积分",
            extra_data={
                'batch': True,
                'count': count,
                'credits': credits
            }
        )

    def log_credits_add(self, admin_name: str, target_user: str, cat_coins: int, credits: int, reason: str = ''):
        """记录直接充值积分"""
        return self.log(
            admin_name=admin_name,
            action_type='CREDITS_ADD',
            target=target_user,
            details=f"为 {target_user} 充值 {credits} 积分（{cat_coins}个猫币），原因: {reason}",
            extra_data={
                'cat_coins': cat_coins,
                'credits': credits,
                'reason': reason
            }
        )

    def log_redeem_used(self, user_name: str, user_id: str, code: str, credits: int, new_balance: int):
        """记录用户使用兑换码"""
        return self.log(
            admin_name='系统',  # 用户操作，记录为"系统"
            action_type='REDEEM_USED',
            target=user_name,
            details=f"用户 {user_name} 使用兑换码 {code}，获得 {credits} 积分，当前余额 {new_balance}",
            extra_data={
                'user_id': user_id,
                'code': code,
                'credits': credits,
                'new_balance': new_balance
            }
        )

    def get_logs(self, limit: int = 100, action_type: str = None) -> List[Dict]:
        """
        获取操作日志列表

        Args:
            limit: 返回数量限制
            action_type: 筛选操作类型
        """
        if not self.client:
            return []

        try:
            query = self.client.table('admin_logs').select('*').order('created_at', desc=True)

            if action_type:
                query = query.eq('action_type', action_type)

            result = query.limit(limit).execute()
            return result.data if result.data else []
        except Exception as e:
            print(f"获取日志列表失败: {e}")
            return []

    def get_redeem_logs(self, limit: int = 100) -> List[Dict]:
        """获取兑换日志（兑换码创建 + 积分充值 + 用户兑换）"""
        if not self.client:
            return []

        try:
            result = self.client.table('admin_logs').select('*').in_(
                'action_type', ['REDEEM_CREATE', 'CREDITS_ADD', 'REDEEM_USED']
            ).order('created_at', desc=True).limit(limit).execute()
            return result.data if result.data else []
        except Exception as e:
            print(f"获取兑换日志失败: {e}")
            return []

    def get_user_redeem_logs(self, limit: int = 100) -> List[Dict]:
        """获取用户兑换日志（仅用户使用兑换码）"""
        if not self.client:
            return []

        try:
            result = self.client.table('admin_logs').select('*').eq(
                'action_type', 'REDEEM_USED'
            ).order('created_at', desc=True).limit(limit).execute()
            return result.data if result.data else []
        except Exception as e:
            print(f"获取用户兑换日志失败: {e}")
            return []

    def get_prompt_logs(self, limit: int = 100) -> List[Dict]:
        """获取提示词操作日志"""
        if not self.client:
            return []

        try:
            result = self.client.table('admin_logs').select('*').in_(
                'action_type', ['PROMPT_CREATE', 'PROMPT_UPDATE', 'PROMPT_DELETE', 'MODULE_CREATE', 'MODULE_DELETE']
            ).order('created_at', desc=True).limit(limit).execute()
            return result.data if result.data else []
        except Exception as e:
            print(f"获取提示词日志失败: {e}")
            return []


# 单例实例
admin_log_service = AdminLogService()
