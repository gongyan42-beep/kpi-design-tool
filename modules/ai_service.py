"""
AI服务模块 - 双 API 自动切换（云雾优先，CloseAI 备用）
支持普通请求、流式输出和多模态（图片+文本）
"""
import os
import time
import json
import base64
import requests
import logging
from typing import List, Dict, Optional, Generator
from config import Config

# 配置日志
logger = logging.getLogger(__name__)


class AIService:
    """AI对话服务，支持双 API 自动切换"""

    def __init__(self):
        # 主用 API：CloseAI（更快）
        self.primary_api_key = Config.CLOSEAI_API_KEY
        self.primary_base_url = Config.CLOSEAI_BASE_URL
        # 备用 API：云雾（便宜）
        self.backup_api_key = Config.YUNWU_API_KEY
        self.backup_base_url = Config.YUNWU_BASE_URL

        self.default_model = Config.DEFAULT_MODEL
        self.available_models = Config.AVAILABLE_MODELS

        # 超时设置（云雾稍慢，给更多时间）
        self.primary_timeout = 30  # 云雾超时 30 秒
        self.backup_timeout = 60   # CloseAI 超时 60 秒

    def _call_api(
        self,
        api_key: str,
        base_url: str,
        payload: dict,
        timeout: int,
        api_name: str
    ) -> Optional[str]:
        """
        调用单个 API

        Returns:
            成功返回内容，失败返回 None
        """
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        try:
            logger.info(f"[{api_name}] 发起请求，模型: {payload.get('model')}")
            response = requests.post(
                f'{base_url}/chat/completions',
                headers=headers,
                json=payload,
                timeout=timeout
            )

            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message'].get('content', '')
                if content:
                    logger.info(f"[{api_name}] 响应成功，长度: {len(content)}")
                    return content
                else:
                    logger.warning(f"[{api_name}] 响应内容为空")
                    return None
            else:
                logger.warning(f"[{api_name}] 请求失败: {response.status_code}")
                return None

        except requests.exceptions.Timeout:
            logger.warning(f"[{api_name}] 请求超时 ({timeout}s)")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"[{api_name}] 网络错误: {e}")
            return None
        except Exception as e:
            logger.warning(f"[{api_name}] 未知错误: {e}")
            return None

    def chat(
        self,
        messages: List[Dict],
        system_prompt: str,
        model: str = 'flash',
        temperature: float = 0.7,
        max_tokens: int = 16000
    ) -> str:
        """
        发送对话请求（双 API 自动切换）

        策略：云雾优先 → 失败/超时自动切换 CloseAI
        """
        model_name = self.available_models.get(model, self.default_model)

        full_messages = [
            {'role': 'system', 'content': system_prompt}
        ] + messages

        payload = {
            'model': model_name,
            'messages': full_messages,
            'temperature': temperature,
            'max_tokens': max_tokens
        }

        # 1. 尝试 CloseAI（主用，更快）
        if self.primary_api_key:
            content = self._call_api(
                self.primary_api_key,
                self.primary_base_url,
                payload,
                self.primary_timeout,
                "CloseAI"
            )
            if content:
                return content
            logger.info("CloseAI 失败，切换到云雾...")

        # 2. 尝试云雾（备用）
        if self.backup_api_key:
            content = self._call_api(
                self.backup_api_key,
                self.backup_base_url,
                payload,
                self.backup_timeout,
                "云雾"
            )
            if content:
                return content

        # 3. 都失败了
        raise Exception("所有 AI API 均不可用，请稍后重试")

    def chat_stream(
        self,
        messages: List[Dict],
        system_prompt: str,
        model: str = 'flash',
        temperature: float = 0.7,
        max_tokens: int = 16000,
        images: List[str] = None  # Base64 图片列表
    ) -> Generator[str, None, None]:
        """
        流式对话请求（双 API 自动切换）- 支持多模态
        """
        model_name = self.available_models.get(model, self.default_model)

        # 构建消息（支持多模态）
        full_messages = [
            {'role': 'system', 'content': system_prompt}
        ]

        # 添加历史消息
        for msg in messages[:-1]:  # 除了最后一条消息
            full_messages.append(msg)

        # 处理最后一条用户消息（可能包含图片）
        if messages:
            last_msg = messages[-1]
            if images and last_msg.get('role') == 'user':
                # 构建多模态消息
                content_parts = []

                # 添加图片
                for img_base64 in images:
                    # 确保图片是完整的 data URL 格式
                    if not img_base64.startswith('data:'):
                        img_base64 = f"data:image/jpeg;base64,{img_base64}"

                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": img_base64}
                    })

                # 添加文本（如果有）
                text_content = last_msg.get('content', '').strip()
                if text_content and not text_content.startswith('[图片]') and '[附图' not in text_content:
                    content_parts.append({
                        "type": "text",
                        "text": text_content
                    })
                elif not text_content:
                    # 如果没有文字，添加默认提示
                    content_parts.append({
                        "type": "text",
                        "text": "请分析这张图片"
                    })
                else:
                    # 有标记的消息，提取原始文本
                    original_text = text_content.replace('[图片]', '').strip()
                    if '[附图' in original_text:
                        original_text = original_text.split('[附图')[0].strip()
                    if original_text:
                        content_parts.append({
                            "type": "text",
                            "text": original_text
                        })
                    else:
                        content_parts.append({
                            "type": "text",
                            "text": "请分析这张图片"
                        })

                full_messages.append({
                    'role': 'user',
                    'content': content_parts
                })
            else:
                full_messages.append(last_msg)

        payload = {
            'model': model_name,
            'messages': full_messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
            'stream': True
        }

        # 尝试的 API 列表（CloseAI 优先）
        apis = []
        if self.primary_api_key:
            apis.append(("CloseAI", self.primary_api_key, self.primary_base_url, self.primary_timeout + 30))
        if self.backup_api_key:
            apis.append(("云雾", self.backup_api_key, self.backup_base_url, self.backup_timeout + 30))

        for api_name, api_key, base_url, timeout in apis:
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }

            has_images = images and len(images) > 0
            logger.info(f"[{api_name}] 流式请求，模型: {model_name}，包含图片: {has_images}")

            try:
                response = requests.post(
                    f'{base_url}/chat/completions',
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                    stream=True
                )

                if response.status_code != 200:
                    logger.warning(f"[{api_name}] 流式请求失败: {response.status_code}, {response.text[:200]}")
                    continue

                # 成功，开始流式输出
                has_content = False
                for line in response.iter_lines():
                    if line:
                        line = line.decode('utf-8')
                        if line.startswith('data: '):
                            data_str = line[6:]
                            if data_str == '[DONE]':
                                break
                            try:
                                data = json.loads(data_str)
                                delta = data.get('choices', [{}])[0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    has_content = True
                                    yield content
                            except json.JSONDecodeError:
                                continue

                if has_content:
                    logger.info(f"[{api_name}] 流式响应完成")
                    return
                else:
                    logger.warning(f"[{api_name}] 流式响应无内容")
                    continue

            except requests.exceptions.Timeout:
                logger.warning(f"[{api_name}] 流式请求超时")
                continue
            except requests.exceptions.RequestException as e:
                logger.warning(f"[{api_name}] 流式网络错误: {e}")
                continue

        # 所有 API 都失败
        yield "[ERROR]所有 AI API 均不可用，请稍后重试"

    def get_available_models(self) -> Dict[str, str]:
        """获取可用模型列表"""
        return {
            'flash': {
                'id': 'flash',
                'name': 'Gemini Flash',
                'description': '快速响应，适合日常对话',
                'model': self.available_models['flash']
            },
            'pro': {
                'id': 'pro',
                'name': 'Gemini Pro',
                'description': '深度思考，适合复杂问题',
                'model': self.available_models['pro']
            }
        }


# 单例实例
ai_service = AIService()
