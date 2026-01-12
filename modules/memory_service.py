"""
用户记忆仓库服务 - 跨模块共享用户信息（AI 增强版）
"""
import json
import re
from typing import Dict, Optional, List
from datetime import datetime


class MemoryService:
    """用户记忆管理服务"""

    # AI 提取的提示词模板
    EXTRACT_PROMPT = """请从以下对话内容中提取用户的关键业务信息。只提取明确提到的信息，不要推测。

对话内容：
{conversation}

请以 JSON 格式返回提取的信息，只返回 JSON，不要其他内容。如果某个字段没有明确提到，设为 null。

{{
    "company_name": "公司名称（如果提到）",
    "industry": "行业（如：电商、教育、餐饮等）",
    "platforms": ["电商平台列表，如：淘宝、天猫、抖音、拼多多"],
    "annual_revenue": "年销售额/年营收（如：500万、1000万）",
    "employee_count": "员工人数（如：10人、50人）",
    "positions": ["讨论过的岗位名称列表，如：运营、客服、主播"],
    "key_challenges": ["用户提到的核心痛点或挑战"]
}}"""

    def __init__(self):
        self.client = None
        self.ai_service = None
        self._init_client()

    def _init_client(self):
        """初始化客户端"""
        try:
            from modules.supabase_client import get_client
            self.client = get_client()
        except Exception as e:
            print(f"MemoryService: 初始化 Supabase 客户端失败: {e}")

        try:
            from modules.ai_service import ai_service
            self.ai_service = ai_service
        except Exception as e:
            print(f"MemoryService: 初始化 AI 服务失败: {e}")

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
        """更新用户记忆（合并更新，只更新非空值）"""
        if not self.client or not user_id:
            return False

        try:
            # 获取现有记忆
            existing = self.get_memory(user_id)

            # 合并数据（只更新有值的字段）
            merged_data = {
                'user_id': user_id,
                'updated_at': datetime.now().isoformat()
            }

            # 合并字段
            for key in ['company_name', 'industry', 'platforms', 'annual_revenue',
                        'employee_count', 'positions', 'key_challenges']:
                new_value = data.get(key)
                old_value = existing.get(key)

                # 新值有效则用新值，否则保留旧值
                if new_value and new_value != 'null' and new_value != []:
                    # 对于列表类型，合并去重
                    if isinstance(new_value, list) and isinstance(old_value, list):
                        merged_data[key] = list(set(old_value + new_value))
                    else:
                        merged_data[key] = new_value
                elif old_value:
                    merged_data[key] = old_value

            # Upsert（插入或更新）
            self.client.table('user_memory').upsert(merged_data).execute()
            print(f"[MemoryService] 更新用户 {user_id[:8]}... 的记忆: {list(merged_data.keys())}")
            return True
        except Exception as e:
            print(f"更新用户记忆失败: {e}")
            return False

    def extract_from_messages(self, messages: List[Dict], use_ai: bool = True) -> Dict:
        """
        从对话消息中提取关键信息

        Args:
            messages: 对话消息列表
            use_ai: 是否使用 AI 提取（默认 True）

        Returns:
            提取的用户信息字典
        """
        if not messages:
            return {}

        # 拼接对话内容（限制长度避免 token 过多）
        conversation_parts = []
        total_len = 0
        max_len = 4000  # 限制最大长度

        for msg in messages[-20:]:  # 只取最近 20 条消息
            role = '用户' if msg.get('role') == 'user' else 'AI'
            content = msg.get('content', '')[:500]  # 每条消息限制 500 字
            line = f"{role}: {content}"

            if total_len + len(line) > max_len:
                break
            conversation_parts.append(line)
            total_len += len(line)

        conversation = '\n'.join(conversation_parts)

        if not conversation.strip():
            return {}

        # 方案1：使用 AI 提取（推荐）
        if use_ai and self.ai_service:
            try:
                extracted = self._extract_with_ai(conversation)
                if extracted:
                    return extracted
            except Exception as e:
                print(f"[MemoryService] AI 提取失败，回退到规则提取: {e}")

        # 方案2：使用规则提取（降级方案）
        return self._extract_with_rules(conversation)

    def _extract_with_ai(self, conversation: str) -> Dict:
        """使用 AI 提取信息"""
        if not self.ai_service:
            return {}

        prompt = self.EXTRACT_PROMPT.format(conversation=conversation)

        try:
            # 调用 AI（使用快速模型）
            response = self.ai_service.chat(
                messages=[{'role': 'user', 'content': prompt}],
                system_prompt="你是一个信息提取助手，只返回 JSON 格式的结果，不要其他内容。",
                model='flash'  # 使用快速模型节省成本
            )

            # 解析 JSON
            # 尝试从响应中提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                extracted = json.loads(json_match.group())

                # 清理 null 值
                cleaned = {}
                for key, value in extracted.items():
                    if value and value != 'null' and value != [] and value != '':
                        cleaned[key] = value

                print(f"[MemoryService] AI 提取成功: {list(cleaned.keys())}")
                return cleaned

        except json.JSONDecodeError as e:
            print(f"[MemoryService] AI 返回的 JSON 解析失败: {e}")
        except Exception as e:
            print(f"[MemoryService] AI 提取异常: {e}")

        return {}

    def _extract_with_rules(self, conversation: str) -> Dict:
        """使用规则提取信息（降级方案）"""
        extracted = {}

        # 提取公司名（模式：XX公司、XX店、XX有限公司等）
        company_patterns = [
            r'(?:我们?(?:公司|店铺?|企业)|(?:叫|是|在))[\s:：]*([^\s,，。]{2,15}(?:公司|店铺?|有限公司|企业|工作室))',
            r'([^\s,，。]{2,10}(?:电商|科技|贸易|商贸)(?:有限)?公司)',
        ]
        for pattern in company_patterns:
            match = re.search(pattern, conversation)
            if match:
                extracted['company_name'] = match.group(1)
                break

        # 提取电商平台
        platforms = []
        platform_keywords = ['淘宝', '天猫', '京东', '拼多多', '抖音', '快手', '小红书', '得物', '1688', '亚马逊']
        for platform in platform_keywords:
            if platform in conversation:
                platforms.append(platform)
        if platforms:
            extracted['platforms'] = platforms

        # 提取员工人数
        employee_patterns = [
            r'(?:员工|人员|团队|人数)[\s:：]*(\d+)\s*(?:人|个)',
            r'(\d+)\s*(?:人|个)\s*(?:的)?(?:团队|员工)',
        ]
        for pattern in employee_patterns:
            match = re.search(pattern, conversation)
            if match:
                extracted['employee_count'] = f"{match.group(1)}人"
                break

        # 提取年销售额
        revenue_patterns = [
            r'(?:年销售?额?|年营收|GMV|销售额)[\s:：]*(\d+(?:\.\d+)?)\s*(?:万|亿|W|w)',
            r'(\d+(?:\.\d+)?)\s*(?:万|亿)\s*(?:的)?(?:年销售?额?|销售|营收)',
        ]
        for pattern in revenue_patterns:
            match = re.search(pattern, conversation)
            if match:
                num = match.group(1)
                unit = '万' if '万' in conversation[match.start():match.end()+5] or 'w' in conversation[match.start():match.end()+5].lower() else '亿'
                extracted['annual_revenue'] = f"{num}{unit}"
                break

        # 提取岗位
        positions = []
        position_keywords = ['运营', '客服', '主播', '剪辑', '文案', '设计', '美工', '仓管', '打包', '采购', '财务', '人事', 'HR']
        for pos in position_keywords:
            if pos in conversation:
                positions.append(pos)
        if positions:
            extracted['positions'] = positions

        if extracted:
            print(f"[MemoryService] 规则提取成功: {list(extracted.keys())}")

        return extracted

    def extract_and_update(self, user_id: str, messages: List[Dict]) -> bool:
        """
        从对话中提取信息并更新用户记忆（便捷方法）

        Args:
            user_id: 用户ID
            messages: 对话消息列表

        Returns:
            是否成功更新
        """
        if not user_id or not messages:
            return False

        # 只有足够的对话内容才提取（至少 3 轮对话）
        user_messages = [m for m in messages if m.get('role') == 'user']
        if len(user_messages) < 3:
            return False

        # 提取信息
        extracted = self.extract_from_messages(messages)

        if not extracted:
            return False

        # 更新记忆
        return self.update_memory(user_id, extracted)

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
                # 处理可能是字符串列表或字典列表的情况
                pos_names = []
                for p in positions:
                    if isinstance(p, dict):
                        pos_names.append(p.get('name', ''))
                    else:
                        pos_names.append(str(p))
                pos_names = [p for p in pos_names if p]
                if pos_names:
                    context_parts.append(f"- 已讨论岗位: {', '.join(pos_names)}")

        if memory.get('key_challenges'):
            challenges = memory['key_challenges']
            if isinstance(challenges, list) and challenges:
                context_parts.append(f"- 核心痛点: {', '.join(challenges[:3])}")  # 最多显示3个

        if not context_parts:
            return ""

        return """
## 用户已知信息（不要重复询问这些信息）
""" + '\n'.join(context_parts) + """

请基于这些已知信息进行对话，避免重复询问。
"""


# 单例实例
memory_service = MemoryService()
