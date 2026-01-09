"""
用户记忆仓库服务 - 跨模块共享用户信息
"""
from typing import Dict, Optional
from datetime import datetime


class MemoryService:
    """用户记忆管理服务"""

    def __init__(self):
        self.client = None
        self._init_client()

    def _init_client(self):
        """初始化 Supabase 客户端"""
        try:
            from modules.supabase_client import get_client
            self.client = get_client()
        except Exception as e:
            print(f"MemoryService: 初始化 Supabase 客户端失败: {e}")

    def get_memory(self, user_id: str) -> Dict:
        """获取用户记忆"""
        if not self.client or not user_id:
            return {}

        try:
            response = self.client.table('user_memory').select('*').eq('user_id', user_id).execute()
            if response.data:
                return response.data[0]
            return {}
        except Exception as e:
            print(f"获取用户记忆失败: {e}")
            return {}

    def update_memory(self, user_id: str, data: Dict) -> bool:
        """更新用户记忆（合并更新）"""
        if not self.client or not user_id:
            return False

        try:
            # 获取现有记忆
            existing = self.get_memory(user_id)

            # 合并数据
            merged_data = {
                'user_id': user_id,
                'updated_at': datetime.now().isoformat()
            }

            # 合并已有数据
            for key in ['company_name', 'industry', 'platforms', 'annual_revenue',
                        'employee_count', 'positions', 'key_challenges']:
                if key in data and data[key]:
                    merged_data[key] = data[key]
                elif key in existing and existing[key]:
                    merged_data[key] = existing[key]

            # Upsert（插入或更新）
            self.client.table('user_memory').upsert(merged_data).execute()
            return True
        except Exception as e:
            print(f"更新用户记忆失败: {e}")
            return False

    def extract_from_messages(self, messages: list) -> Dict:
        """从对话消息中提取关键信息（简单版本，基于关键词）"""
        extracted = {}

        # 拼接所有用户消息
        user_texts = ' '.join([
            msg.get('content', '')
            for msg in messages
            if msg.get('role') == 'user'
        ])

        # 简单的关键信息提取（后续可以用 AI 增强）
        # 这里使用简单的模式匹配

        # 提取公司名相关
        # (未来可以调用 AI 来做更智能的提取)

        return extracted

    def get_memory_context(self, user_id: str) -> str:
        """获取用于注入到系统提示词的记忆上下文"""
        memory = self.get_memory(user_id)

        if not memory:
            return ""

        context_parts = []

        if memory.get('company_name'):
            context_parts.append(f"- 公司名称: {memory['company_name']}")

        if memory.get('industry'):
            context_parts.append(f"- 行业: {memory['industry']}")

        if memory.get('platforms'):
            platforms = memory['platforms']
            if isinstance(platforms, list):
                context_parts.append(f"- 电商平台: {', '.join(platforms)}")
            else:
                context_parts.append(f"- 电商平台: {platforms}")

        if memory.get('annual_revenue'):
            context_parts.append(f"- 年销售额: {memory['annual_revenue']}")

        if memory.get('employee_count'):
            context_parts.append(f"- 员工人数: {memory['employee_count']}")

        if memory.get('positions'):
            positions = memory['positions']
            if isinstance(positions, list) and positions:
                pos_names = [p.get('name', '') for p in positions if p.get('name')]
                if pos_names:
                    context_parts.append(f"- 已讨论岗位: {', '.join(pos_names)}")

        if not context_parts:
            return ""

        return """
## 用户已知信息（不要重复询问这些信息）
""" + '\n'.join(context_parts) + """

请基于这些已知信息进行对话，避免重复询问。
"""


# 单例实例
memory_service = MemoryService()
