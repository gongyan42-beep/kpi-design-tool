"""
数据库模块 - SQLite会话和对话管理
"""
import sqlite3
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, List
from config import Config


class Database:
    """SQLite数据库管理"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DATABASE_PATH
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库表"""
        conn = self._get_conn()
        cursor = conn.cursor()

        # 会话表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                module TEXT NOT NULL,
                user_id TEXT,
                user_email TEXT,
                status TEXT DEFAULT 'in_progress',
                collected_data TEXT DEFAULT '{}',
                messages TEXT DEFAULT '[]',
                output_document TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 检查是否需要添加新列（兼容旧数据库）
        cursor.execute("PRAGMA table_info(sessions)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'user_id' not in columns:
            cursor.execute('ALTER TABLE sessions ADD COLUMN user_id TEXT')
        if 'user_email' not in columns:
            cursor.execute('ALTER TABLE sessions ADD COLUMN user_email TEXT')

        # 本地提示词表（作为 Supabase 的备用方案）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS local_prompts (
                module_id TEXT PRIMARY KEY,
                prompt TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 本地模块表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS local_modules (
                id TEXT PRIMARY KEY,
                name TEXT,
                icon TEXT,
                color TEXT,
                description TEXT,
                subtitle TEXT,
                sort_order INTEGER DEFAULT 99,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

    def create_session(self, module: str, user_id: str = None, user_email: str = None) -> str:
        """创建新会话"""
        session_id = str(uuid.uuid4())[:8]
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO sessions (id, module, user_id, user_email, collected_data, messages)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, module, user_id, user_email, '{}', '[]'))

        conn.commit()
        conn.close()
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话详情"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'id': row['id'],
                'module': row['module'],
                'user_id': row['user_id'],
                'user_email': row['user_email'],
                'status': row['status'],
                'collected_data': json.loads(row['collected_data']),
                'messages': json.loads(row['messages']),
                'output_document': row['output_document'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at']
            }
        return None

    def add_message(self, session_id: str, role: str, content: str) -> bool:
        """添加消息到会话"""
        session = self.get_session(session_id)
        if not session:
            return False

        messages = session['messages']
        messages.append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        })

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE sessions
            SET messages = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (json.dumps(messages, ensure_ascii=False), session_id))

        conn.commit()
        conn.close()
        return True

    def update_collected_data(self, session_id: str, new_data: dict) -> bool:
        """更新已收集的数据"""
        session = self.get_session(session_id)
        if not session:
            return False

        collected_data = session['collected_data']
        collected_data.update(new_data)

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE sessions
            SET collected_data = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (json.dumps(collected_data, ensure_ascii=False), session_id))

        conn.commit()
        conn.close()
        return True

    def save_output_document(self, session_id: str, document: str) -> bool:
        """保存产出文档"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE sessions
            SET output_document = ?, status = 'completed', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (document, session_id))

        conn.commit()
        conn.close()
        return True

    def get_messages_for_api(self, session_id: str, max_chars: int = 50000, module: str = '') -> List[Dict]:
        """
        获取用于API调用的消息格式（智能压缩版）

        策略：
        1. 如果消息数少或字符数在限制内，直接返回全部
        2. 如果超限，使用 AI 生成摘要 + 保留最近消息
        """
        session = self.get_session(session_id)
        if not session:
            return []

        all_messages = session['messages']
        if not all_messages:
            return []

        # 计算总字符数
        total_chars = sum(len(msg.get('content', '')) for msg in all_messages)

        # 如果没超限，直接返回全部
        if total_chars <= max_chars:
            return [{'role': msg['role'], 'content': msg['content']} for msg in all_messages]

        # 超限了，使用智能压缩
        try:
            from modules.context_compressor import context_compressor
            return context_compressor.compress_messages(
                all_messages,
                module=module or session.get('module', ''),
                force=True
            )
        except Exception as e:
            print(f"智能压缩失败，使用简单截断: {e}")
            # 降级：简单截断
            return self._simple_truncate(all_messages, max_chars)

    def _simple_truncate(self, messages: List[Dict], max_chars: int) -> List[Dict]:
        """智能截断（降级方案）- 保留关键上下文"""
        if not messages:
            return []

        api_messages = []

        # 1. 保留第一条（欢迎消息）
        first_msg = messages[0]
        api_messages.append({'role': first_msg['role'], 'content': first_msg['content']})
        first_len = len(first_msg.get('content', ''))

        # 2. 提取用户输入的关键信息（公司名、岗位、数字等）
        user_inputs_summary = []
        for msg in messages[1:]:
            if msg.get('role') == 'user':
                content = msg.get('content', '')[:300]  # 每条用户消息取前300字
                user_inputs_summary.append(f"- {content}")

        # 3. 生成摘要
        if user_inputs_summary:
            summary = "【历史对话摘要】用户之前提供的信息：\n" + "\n".join(user_inputs_summary[-10:])  # 最多保留10条
            api_messages.append({
                'role': 'system',
                'content': summary + "\n\n请基于以上信息继续对话，不要重复询问已提供的信息。"
            })

        # 4. 计算剩余空间，尽量多保留最近消息
        used_chars = first_len + len(api_messages[-1]['content']) if len(api_messages) > 1 else first_len
        remaining_chars = max_chars - used_chars - 1000  # 预留1000字符buffer

        # 5. 从最近的消息往前加
        recent_messages = []
        for msg in reversed(messages[1:]):
            msg_len = len(msg.get('content', ''))
            if remaining_chars >= msg_len:
                recent_messages.insert(0, {'role': msg['role'], 'content': msg['content']})
                remaining_chars -= msg_len
            else:
                break

        api_messages.extend(recent_messages)
        return api_messages

    def list_sessions(self, limit: int = 20) -> List[Dict]:
        """列出最近的会话"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, module, status, created_at, updated_at
            FROM sessions
            ORDER BY updated_at DESC
            LIMIT ?
        ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_all_sessions_for_admin(self, limit: int = 100) -> List[Dict]:
        """管理后台：获取所有会话（含用户信息和消息）"""
        conn = self._get_conn()
        cursor = conn.cursor()

        # 获取所有会话（包括未登录用户的）
        cursor.execute('''
            SELECT id, module, user_id, user_email, status, messages, created_at, updated_at
            FROM sessions
            ORDER BY updated_at DESC
            LIMIT ?
        ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        result = []
        for row in rows:
            session_dict = dict(row)
            session_dict['session_id'] = session_dict['id']  # 添加别名兼容前端
            session_dict['messages'] = json.loads(session_dict['messages'])
            session_dict['message_count'] = len(session_dict['messages'])
            result.append(session_dict)

        return result

    def get_user_sessions(self, user_id: str, limit: int = 20) -> List[Dict]:
        """获取指定用户的所有会话（带预览）"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, module, status, messages, created_at, updated_at
            FROM sessions
            WHERE user_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
        ''', (user_id, limit))

        rows = cursor.fetchall()
        conn.close()

        result = []
        for row in rows:
            session_dict = dict(row)
            messages = json.loads(session_dict['messages'])
            session_dict['messages'] = messages

            # 生成预览（第一条用户消息）
            preview = '新对话'
            for msg in messages:
                if msg.get('role') == 'user':
                    content = msg.get('content', '')
                    preview = content[:50] + ('...' if len(content) > 50 else '')
                    break

            session_dict['preview'] = preview
            result.append(session_dict)

        return result

    # ========================================
    # 本地提示词管理（作为 Supabase 备用）
    # ========================================

    def save_local_prompt(self, module_id: str, prompt: str) -> bool:
        """保存提示词到本地 SQLite"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO local_prompts (module_id, prompt, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (module_id, prompt))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"保存本地提示词失败: {e}")
            return False

    def get_local_prompt(self, module_id: str) -> Optional[str]:
        """从本地获取提示词"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            cursor.execute('SELECT prompt FROM local_prompts WHERE module_id = ?', (module_id,))
            row = cursor.fetchone()
            conn.close()

            return row['prompt'] if row else None
        except Exception as e:
            print(f"获取本地提示词失败: {e}")
            return None


# 单例实例
db = Database()
