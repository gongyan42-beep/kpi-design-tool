"""
提示词管理服务 - 动态加载和编辑模块提示词
"""
from typing import Dict, List, Optional
from datetime import datetime
import json


class PromptService:
    """提示词管理服务"""

    def __init__(self):
        self.client = None
        self._init_client()
        self._cache = {}  # 缓存提示词

    def _init_client(self):
        """初始化 Supabase 客户端"""
        try:
            from modules.supabase_client import get_client
            self.client = get_client()
        except Exception as e:
            print(f"PromptService: 初始化 Supabase 客户端失败: {e}")

    def get_all_modules(self) -> List[Dict]:
        """获取所有模块配置（合并本地和 Supabase，支持删除同步）"""
        from config import Config

        # 先构建本地模块字典
        local_modules = {}
        for idx, (key, info) in enumerate(Config.MODULES.items()):
            local_modules[key] = {
                'id': key,
                'name': info['name'],
                'icon': info['icon'],
                'color': info['color'],
                'description': info['description'],
                'subtitle': info.get('subtitle', ''),
                'sort_order': idx,
                'is_active': True
            }

        # 尝试从 Supabase 获取所有模块（包括禁用的，用于判断哪些被删除）
        supabase_modules = {}
        disabled_modules = set()  # 记录被禁用的模块ID

        if self.client:
            try:
                # 获取所有模块，包括禁用的
                response = self.client.table('modules').select('*').order('sort_order').execute()
                if response.data:
                    for m in response.data:
                        if m.get('is_active', True):
                            supabase_modules[m['id']] = m
                        else:
                            # 记录被禁用的模块
                            disabled_modules.add(m['id'])
            except Exception as e:
                print(f"获取 Supabase 模块列表失败: {e}")

        # 合并逻辑：
        # 1. 本地模块如果在 Supabase 中被禁用，则不显示
        # 2. Supabase 启用的模块覆盖本地同名模块
        # 3. Supabase 独有的新模块追加
        merged = {}

        # 先添加本地模块（排除被禁用的）
        for key, module in local_modules.items():
            if key in disabled_modules:
                # 该模块在 Supabase 中被标记为删除，跳过
                continue
            if key in supabase_modules:
                # Supabase 版本覆盖本地版本
                merged[key] = supabase_modules[key]
            else:
                merged[key] = module

        # 再添加 Supabase 独有的新模块（已经是 is_active=True 的）
        for key, module in supabase_modules.items():
            if key not in merged:
                merged[key] = module

        # 按 sort_order 排序返回
        modules_list = list(merged.values())
        modules_list.sort(key=lambda x: x.get('sort_order', 99))

        return modules_list

    def get_module(self, module_id: str) -> Optional[Dict]:
        """获取单个模块配置（优先 Supabase，回退本地）"""
        # 先尝试从 Supabase 获取
        if self.client:
            try:
                response = self.client.table('modules').select('*').eq('id', module_id).execute()
                if response.data:
                    module = response.data[0]
                    # 检查模块是否被禁用（软删除）
                    if not module.get('is_active', True):
                        # 模块被删除，不回退到本地，直接返回 None
                        return None
                    return module
            except Exception as e:
                print(f"获取 Supabase 模块失败: {e}")

        # 回退到本地配置前，检查 Supabase 中是否有禁用记录
        # 防止被删除的本地模块仍然可以访问
        if self.client:
            try:
                disabled = self.client.table('modules').select('id').eq('id', module_id).eq('is_active', False).execute()
                if disabled.data:
                    # 存在禁用记录，不返回本地配置
                    return None
            except Exception as e:
                print(f"检查禁用模块失败: {e}")

        # 回退到本地配置
        from config import Config
        if module_id in Config.MODULES:
            info = Config.MODULES[module_id]
            return {
                'id': module_id,
                'name': info['name'],
                'icon': info['icon'],
                'color': info['color'],
                'description': info['description'],
                'subtitle': info.get('subtitle', '')
            }

        return None

    def get_prompt(self, module_id: str) -> str:
        """获取模块的提示词（优先 Supabase -> 本地 -> 默认）

        注意：禁用缓存以确保多 worker 环境下修改即时生效
        """
        from database import db

        # 尝试从 Supabase 获取（不使用缓存，确保即时生效）
        if self.client:
            try:
                response = self.client.table('module_prompts').select('prompt').eq('module_id', module_id).execute()
                if response.data:
                    prompt = response.data[0].get('prompt', '')
                    return prompt
            except Exception as e:
                print(f"Supabase 获取提示词失败: {e}")

        # 尝试从本地 SQLite 获取
        local_prompt = db.get_local_prompt(module_id)
        if local_prompt:
            return local_prompt

        # 回退到默认提示词
        from modules.prompts import MODULE_PROMPTS
        return MODULE_PROMPTS.get(module_id, '')

    def save_prompt(self, module_id: str, prompt: str) -> bool:
        """保存模块的提示词（优先 Supabase，失败则用本地）"""
        from database import db

        # 尝试 Supabase
        if self.client:
            try:
                # 先检查是否存在
                existing = self.client.table('module_prompts').select('id').eq('module_id', module_id).execute()

                if existing.data:
                    # 更新
                    self.client.table('module_prompts').update({
                        'prompt': prompt,
                        'updated_at': datetime.now().isoformat()
                    }).eq('module_id', module_id).execute()
                else:
                    # 插入
                    self.client.table('module_prompts').insert({
                        'module_id': module_id,
                        'prompt': prompt,
                        'created_at': datetime.now().isoformat()
                    }).execute()

                return True
            except Exception as e:
                print(f"Supabase 保存提示词失败，尝试本地保存: {e}")

        # 回退到本地 SQLite
        return db.save_local_prompt(module_id, prompt)

    def create_module(self, module_data: Dict) -> bool:
        """创建新模块"""
        if not self.client:
            return False

        try:
            # 插入模块配置
            self.client.table('modules').insert({
                'id': module_data['id'],
                'name': module_data['name'],
                'icon': module_data.get('icon', '📋'),
                'color': module_data.get('color', '#6b7280'),
                'description': module_data.get('description', ''),
                'subtitle': module_data.get('subtitle', ''),
                'sort_order': module_data.get('sort_order', 99),
                'is_active': True,
                'created_at': datetime.now().isoformat()
            }).execute()

            # 插入默认提示词
            self.client.table('module_prompts').insert({
                'module_id': module_data['id'],
                'prompt': module_data.get('prompt', ''),
                'created_at': datetime.now().isoformat()
            }).execute()

            return True
        except Exception as e:
            print(f"创建模块失败: {e}")
            return False

    def update_module(self, module_id: str, module_data: Dict) -> bool:
        """更新模块配置"""
        if not self.client:
            return False

        try:
            self.client.table('modules').update({
                'name': module_data.get('name'),
                'icon': module_data.get('icon'),
                'color': module_data.get('color'),
                'description': module_data.get('description'),
                'subtitle': module_data.get('subtitle'),
                'is_active': module_data.get('is_active', True),
                'updated_at': datetime.now().isoformat()
            }).eq('id', module_id).execute()

            return True
        except Exception as e:
            print(f"更新模块失败: {e}")
            return False

    def delete_module(self, module_id: str) -> bool:
        """删除模块（软删除）"""
        if not self.client:
            return False

        try:
            # 先检查 Supabase 中是否存在该模块
            existing = self.client.table('modules').select('id').eq('id', module_id).execute()

            if existing.data:
                # 已存在，直接更新为禁用
                self.client.table('modules').update({
                    'is_active': False,
                    'updated_at': datetime.now().isoformat()
                }).eq('id', module_id).execute()
            else:
                # 不存在（只在本地 Config 中），插入一条禁用记录
                # 这样 get_all_modules 才能正确排除它
                from config import Config
                local_info = Config.MODULES.get(module_id, {})
                self.client.table('modules').insert({
                    'id': module_id,
                    'name': local_info.get('name', module_id),
                    'icon': local_info.get('icon', '📋'),
                    'color': local_info.get('color', '#6b7280'),
                    'description': local_info.get('description', ''),
                    'subtitle': local_info.get('subtitle', ''),
                    'is_active': False,  # 标记为禁用
                    'created_at': datetime.now().isoformat()
                }).execute()

            return True
        except Exception as e:
            print(f"删除模块失败: {e}")
            return False

    def get_knowledge_files(self, module_id: str) -> List[Dict]:
        """获取模块的知识库文件列表"""
        if not self.client:
            return []

        try:
            response = self.client.table('knowledge_files').select('*').eq('module_id', module_id).order('created_at', desc=True).execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"获取知识库文件失败: {e}")
            return []

    def add_knowledge_file(self, module_id: str, filename: str, content: str, file_type: str) -> bool:
        """添加知识库文件"""
        if not self.client:
            return False

        try:
            self.client.table('knowledge_files').insert({
                'module_id': module_id,
                'filename': filename,
                'content': content,
                'file_type': file_type,
                'created_at': datetime.now().isoformat()
            }).execute()

            return True
        except Exception as e:
            print(f"添加知识库文件失败: {e}")
            return False

    def delete_knowledge_file(self, file_id: str) -> bool:
        """删除知识库文件"""
        if not self.client:
            return False

        try:
            self.client.table('knowledge_files').delete().eq('id', file_id).execute()
            return True
        except Exception as e:
            print(f"删除知识库文件失败: {e}")
            return False

    def get_knowledge_context(self, module_id: str) -> str:
        """获取模块的知识库上下文（用于注入到提示词）"""
        files = self.get_knowledge_files(module_id)

        if not files:
            return ""

        context = "\n## 参考知识库\n"
        for f in files:
            content = f.get('content', '')
            if len(content) > 2000:
                content = content[:2000] + "...(内容已截断)"
            context += f"\n### {f.get('filename', '未知文件')}\n{content}\n"

        return context

    def clear_cache(self):
        """清除提示词缓存"""
        self._cache = {}


# 单例实例
prompt_service = PromptService()
