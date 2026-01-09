"""
对话上下文智能压缩服务
当对话过长时，自动生成摘要压缩历史消息
"""
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ContextCompressor:
    """对话上下文压缩器"""

    # 配置
    MAX_CHARS_BEFORE_COMPRESS = 30000  # 超过此字符数触发压缩
    KEEP_RECENT_MESSAGES = 8  # 保留最近的消息数（4轮对话）
    SUMMARY_MAX_CHARS = 2000  # 摘要最大长度

    def __init__(self):
        self.ai_service = None

    def _get_ai_service(self):
        """懒加载 AI 服务"""
        if self.ai_service is None:
            from modules.ai_service import ai_service
            self.ai_service = ai_service
        return self.ai_service

    def should_compress(self, messages: List[Dict]) -> bool:
        """判断是否需要压缩"""
        if len(messages) <= self.KEEP_RECENT_MESSAGES + 2:
            return False

        total_chars = sum(len(msg.get('content', '')) for msg in messages)
        return total_chars > self.MAX_CHARS_BEFORE_COMPRESS

    def generate_summary(self, messages: List[Dict], module: str = '') -> str:
        """
        用 AI 生成对话摘要

        Args:
            messages: 需要压缩的消息列表
            module: 当前模块名称

        Returns:
            压缩后的摘要文本
        """
        if not messages:
            return ""

        # 构建压缩提示词
        compress_prompt = """你是一个对话摘要专家。请将以下对话历史压缩成一个简洁的摘要。

要求：
1. 提取所有用户提供的关键信息（公司名、岗位、数字、需求等）
2. 记录当前讨论到哪个阶段
3. 记录已经得出的结论或建议
4. 用列表形式组织，便于快速理解
5. 摘要控制在500字以内

输出格式：
## 已收集信息
- 信息1: xxx
- 信息2: xxx

## 当前进度
正在讨论：xxx

## 重要结论
- 结论1
- 结论2
"""

        # 构建对话文本
        conversation_text = "\n".join([
            f"{'用户' if msg['role'] == 'user' else 'AI'}: {msg['content']}"
            for msg in messages
        ])

        try:
            ai = self._get_ai_service()
            summary = ai.chat(
                messages=[{'role': 'user', 'content': f"请压缩以下对话：\n\n{conversation_text}"}],
                system_prompt=compress_prompt,
                model='flash',  # 使用快速模型压缩
                temperature=0.3,
                max_tokens=1000
            )
            logger.info(f"生成摘要成功，长度: {len(summary)}")
            return summary
        except Exception as e:
            logger.error(f"生成摘要失败: {e}")
            # 降级：简单提取用户消息
            return self._fallback_summary(messages)

    def _fallback_summary(self, messages: List[Dict]) -> str:
        """降级方案：简单提取关键信息"""
        user_messages = [
            msg['content'][:200]  # 每条消息取前200字
            for msg in messages
            if msg.get('role') == 'user'
        ]
        return "## 用户历史输入摘要\n" + "\n".join([f"- {m}" for m in user_messages[-5:]])

    def compress_messages(
        self,
        messages: List[Dict],
        module: str = '',
        force: bool = False
    ) -> List[Dict]:
        """
        智能压缩消息列表

        Args:
            messages: 完整消息列表
            module: 当前模块
            force: 是否强制压缩

        Returns:
            压缩后的消息列表
        """
        if not force and not self.should_compress(messages):
            # 不需要压缩，直接返回
            return [{'role': m['role'], 'content': m['content']} for m in messages]

        logger.info(f"开始压缩对话，原始消息数: {len(messages)}")

        # 分离：第一条(欢迎消息) + 中间消息(需压缩) + 最近消息(保留)
        first_message = messages[0] if messages else None
        recent_messages = messages[-self.KEEP_RECENT_MESSAGES:]
        middle_messages = messages[1:-self.KEEP_RECENT_MESSAGES] if len(messages) > self.KEEP_RECENT_MESSAGES + 1 else []

        result = []

        # 1. 保留第一条
        if first_message:
            result.append({
                'role': first_message['role'],
                'content': first_message['content']
            })

        # 2. 如果有中间消息，生成摘要
        if middle_messages:
            summary = self.generate_summary(middle_messages, module)
            if summary:
                result.append({
                    'role': 'system',
                    'content': f"[以下是之前对话的摘要]\n{summary}\n[摘要结束，以下是最近的对话]"
                })

        # 3. 保留最近消息
        for msg in recent_messages:
            result.append({
                'role': msg['role'],
                'content': msg['content']
            })

        logger.info(f"压缩完成，压缩后消息数: {len(result)}")
        return result


# 单例实例
context_compressor = ContextCompressor()
