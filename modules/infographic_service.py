"""
信息图生成服务 - 使用 Gemini Flash 分析聊天记录生成信息图
"""
import os
import requests
import logging
from typing import List, Dict, Optional
from config import Config

# 配置日志
logger = logging.getLogger(__name__)


class InfographicService:
    """信息图生成服务，使用 Gemini Flash 分析聊天记录"""

    def __init__(self):
        # 优先使用 CloseAI（更稳定）
        self.closeai_api_key = Config.CLOSEAI_API_KEY
        self.closeai_base_url = Config.CLOSEAI_BASE_URL

        # 使用 Flash 模型（快速、便宜）
        self.model = 'gemini-2.0-flash'  # 更稳定的模型

    def _get_api_config(self):
        """获取 API 配置"""
        return self.closeai_api_key, self.closeai_base_url

    def generate_infographic(
        self,
        messages: List[Dict],
        module_name: str,
        module_info: Dict
    ) -> Dict:
        """
        从聊天记录生成信息图

        Args:
            messages: 聊天记录 [{"role": "user/assistant", "content": "..."}]
            module_name: 模块名称（如 'kpi', 'market_price'）
            module_info: 模块信息

        Returns:
            {
                'success': bool,
                'html': str,  # 信息图 HTML
                'title': str,
                'summary': str,
                'key_points': list
            }
        """
        api_key, base_url = self._get_api_config()

        if not api_key:
            return {'success': False, 'error': 'API 密钥未配置'}

        # 构建聊天记录文本
        chat_text = self._format_messages(messages)

        # 生成信息图内容
        prompt = self._build_analysis_prompt(chat_text, module_name, module_info)

        try:
            # 调用 AI 分析聊天记录
            analysis = self._call_ai(api_key, base_url, prompt)

            if not analysis:
                return {'success': False, 'error': 'AI 分析失败'}

            # 生成 HTML 信息图
            html = self._generate_html_infographic(analysis, module_info)

            return {
                'success': True,
                'html': html,
                'title': analysis.get('title', f'{module_info.get("name", "")}分析报告'),
                'summary': analysis.get('summary', ''),
                'key_points': analysis.get('key_points', [])
            }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _format_messages(self, messages: List[Dict]) -> str:
        """格式化聊天记录"""
        lines = []
        for msg in messages:
            role = "用户" if msg['role'] == 'user' else "AI顾问"
            lines.append(f"{role}: {msg['content']}")
        return "\n\n".join(lines)

    def _build_analysis_prompt(self, chat_text: str, module_name: str, module_info: Dict) -> str:
        """构建分析提示词"""
        return f"""你是一个专业的信息图内容分析师。请分析以下关于「{module_info.get('name', module_name)}」的对话记录，提取关键信息并生成结构化内容。

## 对话记录
{chat_text}

## 要求
请以 JSON 格式输出以下内容：

```json
{{
    "title": "信息图标题（简洁有力，10字以内）",
    "subtitle": "副标题（补充说明，20字以内）",
    "summary": "核心结论（50字以内）",
    "key_points": [
        {{
            "icon": "emoji图标",
            "title": "要点标题",
            "value": "关键数值或结论",
            "description": "简短说明"
        }}
    ],
    "metrics": [
        {{
            "label": "指标名称",
            "value": "数值",
            "unit": "单位",
            "trend": "up/down/stable"
        }}
    ],
    "recommendations": [
        "建议1",
        "建议2",
        "建议3"
    ],
    "conclusion": "总结性结论（30字以内）"
}}
```

## 注意
1. 从对话中提取具体的数据、指标、结论
2. key_points 提取 3-5 个最重要的要点
3. metrics 提取对话中提到的具体数值指标
4. 如果对话中没有明确数据，可以基于讨论内容总结定性结论
5. 保持简洁，适合信息图展示

请只输出 JSON，不要其他内容。"""

    def _call_ai(self, api_key: str, base_url: str, prompt: str) -> Optional[Dict]:
        """调用 AI API"""
        import json

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': self.model,
            'messages': [
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.3,
            'max_tokens': 2000
        }

        logger.info(f"信息图 AI 请求 [{self.model}] 发起中...")

        try:
            response = requests.post(
                f'{base_url}/chat/completions',
                headers=headers,
                json=payload,
                timeout=60
            )

            logger.info(f"信息图 AI 响应状态: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                logger.info(f"信息图 AI 响应成功，长度: {len(content)}")

                # 提取 JSON
                # 尝试找到 JSON 块
                if '```json' in content:
                    start = content.find('```json') + 7
                    end = content.find('```', start)
                    content = content[start:end].strip()
                elif '```' in content:
                    start = content.find('```') + 3
                    end = content.find('```', start)
                    content = content[start:end].strip()

                return json.loads(content)
            else:
                logger.error(f"信息图 API 错误: {response.status_code} - {response.text[:500]}")
                return None

        except json.JSONDecodeError as e:
            logger.error(f"信息图 JSON 解析错误: {e}")
            return None
        except Exception as e:
            logger.error(f"信息图 API 调用错误: {e}")
            return None

    def _generate_html_infographic(self, analysis: Dict, module_info: Dict) -> str:
        """生成 HTML 信息图"""
        title = analysis.get('title', '分析报告')
        subtitle = analysis.get('subtitle', '')
        summary = analysis.get('summary', '')
        key_points = analysis.get('key_points', [])
        metrics = analysis.get('metrics', [])
        recommendations = analysis.get('recommendations', [])
        conclusion = analysis.get('conclusion', '')

        color = module_info.get('color', '#1a56db')
        icon = module_info.get('icon', '📊')

        # 生成要点 HTML
        points_html = ''
        for i, point in enumerate(key_points[:5]):
            points_html += f'''
            <div class="key-point">
                <div class="point-icon">{point.get('icon', '📌')}</div>
                <div class="point-content">
                    <div class="point-title">{point.get('title', '')}</div>
                    <div class="point-value">{point.get('value', '')}</div>
                    <div class="point-desc">{point.get('description', '')}</div>
                </div>
            </div>
            '''

        # 生成指标 HTML
        metrics_html = ''
        for metric in metrics[:4]:
            trend_icon = '📈' if metric.get('trend') == 'up' else ('📉' if metric.get('trend') == 'down' else '➡️')
            metrics_html += f'''
            <div class="metric-card">
                <div class="metric-value">{metric.get('value', '-')}<span class="metric-unit">{metric.get('unit', '')}</span></div>
                <div class="metric-label">{metric.get('label', '')} {trend_icon}</div>
            </div>
            '''

        # 生成建议 HTML
        recommendations_html = ''
        for i, rec in enumerate(recommendations[:5], 1):
            recommendations_html += f'<div class="recommendation"><span class="rec-num">{i}</span>{rec}</div>'

        # 生成条件 HTML 片段（避免嵌套 f-string）
        metrics_section = f'<div class="metrics-section">{metrics_html}</div>' if metrics_html else ''

        recommendations_section = ''
        if recommendations_html:
            recommendations_section = f'''<div class="section">
            <div class="section-title">💡 行动建议</div>
            <div class="recommendations">
                {recommendations_html}
            </div>
        </div>'''

        conclusion_section = f'<div class="conclusion"><p>💎 {conclusion}</p></div>' if conclusion else ''

        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px;
        }}
        .infographic {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 24px;
            overflow: hidden;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
        }}
        .header {{
            background: linear-gradient(135deg, {color} 0%, {color}dd 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .header-icon {{ font-size: 48px; margin-bottom: 16px; }}
        .header h1 {{ font-size: 32px; font-weight: 700; margin-bottom: 8px; }}
        .header .subtitle {{ font-size: 18px; opacity: 0.9; }}

        .summary {{
            background: #f8fafc;
            padding: 24px 40px;
            text-align: center;
            border-bottom: 1px solid #e2e8f0;
        }}
        .summary p {{
            font-size: 18px;
            color: #475569;
            line-height: 1.6;
        }}

        .metrics-section {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 16px;
            padding: 32px 40px;
            background: white;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
            padding: 20px;
            border-radius: 16px;
            text-align: center;
        }}
        .metric-value {{
            font-size: 28px;
            font-weight: 700;
            color: {color};
        }}
        .metric-unit {{ font-size: 14px; color: #64748b; }}
        .metric-label {{ font-size: 14px; color: #64748b; margin-top: 8px; }}

        .section {{ padding: 32px 40px; }}
        .section-title {{
            font-size: 20px;
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .key-points {{ display: flex; flex-direction: column; gap: 16px; }}
        .key-point {{
            display: flex;
            gap: 16px;
            padding: 20px;
            background: #f8fafc;
            border-radius: 12px;
            border-left: 4px solid {color};
        }}
        .point-icon {{ font-size: 24px; }}
        .point-title {{ font-weight: 600; color: #1e293b; margin-bottom: 4px; }}
        .point-value {{ font-size: 18px; color: {color}; font-weight: 600; margin-bottom: 4px; }}
        .point-desc {{ font-size: 14px; color: #64748b; }}

        .recommendations {{ display: flex; flex-direction: column; gap: 12px; }}
        .recommendation {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 16px;
            background: #f0fdf4;
            border-radius: 12px;
            color: #166534;
        }}
        .rec-num {{
            width: 28px;
            height: 28px;
            background: #166534;
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 14px;
            flex-shrink: 0;
        }}

        .conclusion {{
            background: linear-gradient(135deg, {color}15 0%, {color}05 100%);
            padding: 32px 40px;
            text-align: center;
            border-top: 2px solid {color}30;
        }}
        .conclusion p {{
            font-size: 18px;
            color: {color};
            font-weight: 600;
        }}

        .footer {{
            padding: 20px 40px;
            text-align: center;
            color: #94a3b8;
            font-size: 12px;
            border-top: 1px solid #e2e8f0;
        }}
    </style>
</head>
<body>
    <div class="infographic">
        <div class="header">
            <div class="header-icon">{icon}</div>
            <h1>{title}</h1>
            <div class="subtitle">{subtitle}</div>
        </div>

        <div class="summary">
            <p>{summary}</p>
        </div>

        {metrics_section}

        <div class="section">
            <div class="section-title">📌 核心要点</div>
            <div class="key-points">
                {points_html}
            </div>
        </div>

        {recommendations_section}

        {conclusion_section}

        <div class="footer">
            由 AI 智能分析生成 · 猫课电商管理落地班
        </div>
    </div>
</body>
</html>'''


# 单例实例
infographic_service = InfographicService()
