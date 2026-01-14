"""
按钮配置服务 - 管理管理后台的分析按钮（用户画像、用户洞察、工具分析）
仅超级管理员可修改
支持 Supabase 优先，SQLite 备用
"""
from typing import Dict, List, Optional
from datetime import datetime
import json


# 默认按钮配置（硬编码的初始值）
DEFAULT_BUTTON_CONFIGS = {
    'user_profile': {
        'id': 'user_profile',
        'name': '生成用户画像',
        'icon': '🧠',
        'prompt': '''你是一位用户行为分析专家。请根据以下用户的聊天记录，生成一份简洁的用户画像分析。

要求：
1. summary：用一句话总结这个用户的核心特征（30字以内）
2. topics：用户关注的主要话题领域（3-5个关键词）
3. patterns：用户的行为特点（2-3个特征）
4. recommendations：针对该用户的服务建议（2-3条）

请以 JSON 格式输出，格式如下：
{
    "summary": "用户特征总结",
    "topics": ["话题1", "话题2"],
    "patterns": ["特点1", "特点2"],
    "recommendations": ["建议1", "建议2"]
}''',
        'is_active': True
    },
    'user_insight': {
        'id': 'user_insight',
        'name': '用户洞察',
        'icon': '🔍',
        'prompt': '''# 角色：需求分析专家

你是一位专业的需求分析专家，擅长从客户对话中提取关键需求信息。

## 任务
分析以下对话内容，提取客户的核心需求和关键洞察。

## 输出格式
请用 Markdown 格式输出，包含以下部分：

### 📋 客户需求摘要
（一句话概括客户的核心需求）

### 👤 基本信息
- 姓名/称呼：
- 公司/行业：
- 职位/角色：

### 📊 客户现状
（描述客户当前的业务状况、痛点和挑战）

### 🎯 客户期望
（客户想要达成的目标和期望效果）

### 🔗 参考对象
（客户提到的竞品、标杆或参考案例）

### 💡 关键洞察
（分析师的专业见解和建议）''',
        'is_active': True
    },
    'tool_analysis': {
        'id': 'tool_analysis',
        'name': '工具分析',
        'icon': '🛠️',
        'prompt': '''# 角色：产品经理和需求分析师

你是一位资深产品经理，擅长从用户对话中提取工具和功能需求。

## 任务
分析以下对话内容，提取用户可能需要的工具、功能或解决方案。

## 输出格式
请用 Markdown 格式输出，包含以下部分：

### 🎯 需求背景
（简述用户的业务背景和痛点）

### 👤 用户场景
（描述用户的典型使用场景）

### 📋 功能需求
列出可能需要的功能点：
1. 功能名称 - 简要描述
2. 功能名称 - 简要描述
...

### 🔧 工具推荐
（如果有现成工具可推荐，列出相关工具及理由）

### 📊 优先级建议
（根据重要性和紧急程度，给出功能开发优先级建议）''',
        'is_active': True
    }
}


class ButtonConfigService:
    """按钮配置服务 - Supabase 优先，SQLite 备用"""

    def __init__(self):
        self.client = None
        self.use_supabase = False
        self._init_client()
        self._init_local_db()
        self._cache = {}

    def _init_client(self):
        """初始化 Supabase 客户端"""
        try:
            from modules.supabase_client import get_admin
            self.client = get_admin()
            # 测试连接
            self.client.table('admin_buttons').select('id').limit(1).execute()
            self.use_supabase = True
            print("✅ ButtonConfigService: 使用 Supabase 存储")
        except Exception as e:
            print(f"⚠️ ButtonConfigService: Supabase admin_buttons 表不可用，使用本地 SQLite: {e}")
            self.use_supabase = False

    def _init_local_db(self):
        """初始化本地 SQLite 表"""
        try:
            from database import db
            conn = db._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_buttons (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    icon TEXT,
                    prompt TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"初始化本地 admin_buttons 表失败: {e}")

    def get_all_buttons(self) -> List[Dict]:
        """获取所有按钮配置"""
        # 先使用默认配置
        buttons = dict(DEFAULT_BUTTON_CONFIGS)

        # 尝试从数据库获取自定义配置
        if self.use_supabase and self.client:
            try:
                response = self.client.table('admin_buttons').select('*').execute()
                if response.data:
                    for btn in response.data:
                        if btn.get('is_active', True):
                            buttons[btn['id']] = btn
            except Exception as e:
                print(f"获取 Supabase 按钮配置失败: {e}")
        else:
            # 使用本地 SQLite
            try:
                from database import db
                conn = db._get_conn()
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM admin_buttons WHERE is_active = 1')
                rows = cursor.fetchall()
                conn.close()
                for row in rows:
                    buttons[row['id']] = dict(row)
            except Exception as e:
                print(f"获取本地按钮配置失败: {e}")

        # 更新缓存
        self._cache = buttons
        return list(buttons.values())

    def get_button(self, button_id: str) -> Optional[Dict]:
        """获取单个按钮配置"""
        # 检查缓存
        if button_id in self._cache:
            return self._cache[button_id]

        # 尝试从数据库获取
        if self.use_supabase and self.client:
            try:
                response = self.client.table('admin_buttons').select('*').eq('id', button_id).execute()
                if response.data:
                    btn = response.data[0]
                    self._cache[button_id] = btn
                    return btn
            except Exception as e:
                print(f"获取 Supabase 按钮配置失败: {e}")
        else:
            try:
                from database import db
                conn = db._get_conn()
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM admin_buttons WHERE id = ?', (button_id,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    btn = dict(row)
                    self._cache[button_id] = btn
                    return btn
            except Exception as e:
                print(f"获取本地按钮配置失败: {e}")

        # 返回默认配置
        if button_id in DEFAULT_BUTTON_CONFIGS:
            return DEFAULT_BUTTON_CONFIGS[button_id]

        return None

    def update_button(self, button_id: str, data: Dict) -> bool:
        """更新按钮配置（仅限超级管理员）"""
        update_data = {
            'name': data.get('name'),
            'icon': data.get('icon'),
            'prompt': data.get('prompt'),
            'is_active': data.get('is_active', True),
        }
        # 移除 None 值
        update_data = {k: v for k, v in update_data.items() if v is not None}

        # 尝试 Supabase
        if self.use_supabase and self.client:
            try:
                existing = self.client.table('admin_buttons').select('id').eq('id', button_id).execute()
                update_data['updated_at'] = datetime.now().isoformat()

                if existing.data:
                    self.client.table('admin_buttons').update(update_data).eq('id', button_id).execute()
                else:
                    insert_data = {'id': button_id, 'created_at': datetime.now().isoformat(), **update_data}
                    default = DEFAULT_BUTTON_CONFIGS.get(button_id, {})
                    insert_data.setdefault('name', default.get('name', button_id))
                    insert_data.setdefault('icon', default.get('icon', '📋'))
                    insert_data.setdefault('prompt', default.get('prompt', ''))
                    self.client.table('admin_buttons').insert(insert_data).execute()

                if button_id in self._cache:
                    del self._cache[button_id]
                return True
            except Exception as e:
                print(f"Supabase 更新按钮配置失败，尝试本地: {e}")

        # 回退到本地 SQLite
        try:
            from database import db
            conn = db._get_conn()
            cursor = conn.cursor()

            cursor.execute('SELECT id FROM admin_buttons WHERE id = ?', (button_id,))
            existing = cursor.fetchone()

            if existing:
                cursor.execute('''
                    UPDATE admin_buttons SET name = ?, icon = ?, prompt = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (update_data.get('name'), update_data.get('icon'), update_data.get('prompt'),
                      1 if update_data.get('is_active', True) else 0, button_id))
            else:
                default = DEFAULT_BUTTON_CONFIGS.get(button_id, {})
                cursor.execute('''
                    INSERT INTO admin_buttons (id, name, icon, prompt, is_active)
                    VALUES (?, ?, ?, ?, ?)
                ''', (button_id,
                      update_data.get('name', default.get('name', button_id)),
                      update_data.get('icon', default.get('icon', '📋')),
                      update_data.get('prompt', default.get('prompt', '')),
                      1 if update_data.get('is_active', True) else 0))

            conn.commit()
            conn.close()

            if button_id in self._cache:
                del self._cache[button_id]
            return True
        except Exception as e:
            print(f"本地更新按钮配置失败: {e}")
            return False

    def get_prompt(self, button_id: str) -> str:
        """获取按钮的提示词"""
        btn = self.get_button(button_id)
        if btn:
            return btn.get('prompt', '')
        return ''

    def clear_cache(self):
        """清除缓存"""
        self._cache = {}


# 单例实例
button_config_service = ButtonConfigService()
