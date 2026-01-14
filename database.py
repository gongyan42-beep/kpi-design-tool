"""
数据库模块 - Supabase 云存储 + SQLite 本地备用
优先使用 Supabase 存储会话数据，确保数据不丢失
"""
import sqlite3
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from config import Config


class Database:
    """数据库管理 - Supabase 优先，SQLite 备用"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DATABASE_PATH
        self.supabase = None
        self.use_supabase = False

        # 初始化 Supabase
        self._init_supabase()

        # 初始化本地 SQLite（作为备用）
        self._init_db()

    def _init_supabase(self):
        """初始化 Supabase 客户端"""
        try:
            from modules.supabase_client import get_admin
            self.supabase = get_admin()
            # 测试连接
            self.supabase.table('sessions').select('id').limit(1).execute()
            self.use_supabase = True
            print("✅ 使用 Supabase 存储会话数据")
        except Exception as e:
            print(f"⚠️ Supabase sessions 表不可用，使用本地 SQLite: {e}")
            self.use_supabase = False

    def _get_conn(self) -> sqlite3.Connection:
        """获取 SQLite 数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _safe_json_loads(self, data: str, default=None):
        """
        安全的 JSON 解析，防止损坏数据导致崩溃

        Args:
            data: JSON 字符串
            default: 解析失败时的默认值

        Returns: 解析后的对象或默认值
        """
        if default is None:
            default = {}
        if not data:
            return default
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError) as e:
            print(f"JSON 解析失败，使用默认值: {e}")
            return default

    def _init_db(self):
        """初始化本地 SQLite 数据库表"""
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

        # 检查是否需要添加新列
        cursor.execute("PRAGMA table_info(sessions)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'user_id' not in columns:
            cursor.execute('ALTER TABLE sessions ADD COLUMN user_id TEXT')
        if 'user_email' not in columns:
            cursor.execute('ALTER TABLE sessions ADD COLUMN user_email TEXT')

        # 本地提示词表
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

        # 预充值表（用户未注册时先存储，注册后自动发放）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_credits (
                id TEXT PRIMARY KEY,
                phone TEXT NOT NULL,
                credits INTEGER NOT NULL,
                reason TEXT DEFAULT '管理员预充值',
                admin_name TEXT DEFAULT 'admin',
                status TEXT DEFAULT 'pending',
                claimed_at TIMESTAMP,
                claimed_user_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 为预充值表创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pending_credits_phone ON pending_credits(phone)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pending_credits_status ON pending_credits(status)')

        # 用户调研记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_research_notes (
                id TEXT PRIMARY KEY,
                user_email TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT,
                file_url TEXT,
                file_name TEXT,
                file_type TEXT,
                file_text_content TEXT,
                notes TEXT,
                created_by TEXT DEFAULT 'admin',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_research_user ON user_research_notes(user_email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_research_category ON user_research_notes(category)')

        conn.commit()
        conn.close()

    # ========================================
    # 会话管理 - Supabase 优先
    # ========================================

    def create_session(
        self,
        module: str,
        user_id: str = None,
        user_email: str = None,
        user_nickname: str = None,
        user_company: str = None,
        module_name: str = None
    ) -> str:
        """
        创建新会话（增强版：记录更多用户信息）

        Args:
            module: 模块ID
            user_id: 用户ID
            user_email: 用户邮箱
            user_nickname: 用户昵称（方便管理后台直接显示）
            user_company: 用户公司（方便管理后台直接显示）
            module_name: 模块中文名称（方便管理后台显示）
        """
        session_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        # 将额外信息存入 collected_data
        collected_data = {
            '_user_info': {
                'nickname': user_nickname or '',
                'company': user_company or ''
            },
            '_module_info': {
                'name': module_name or module
            }
        }

        # 优先尝试 Supabase
        if self.use_supabase:
            try:
                self.supabase.table('sessions').insert({
                    'id': session_id,
                    'module': module,
                    'user_id': user_id,
                    'user_email': user_email,
                    'status': 'in_progress',
                    'collected_data': collected_data,
                    'messages': [],
                    'created_at': now,
                    'updated_at': now
                }).execute()
                return session_id
            except Exception as e:
                print(f"Supabase 创建会话失败，回退到 SQLite: {e}")

        # 回退到 SQLite
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sessions (id, module, user_id, user_email, collected_data, messages)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, module, user_id, user_email, json.dumps(collected_data, ensure_ascii=False), '[]'))
        conn.commit()
        conn.close()
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话详情"""
        # 优先尝试 Supabase
        if self.use_supabase:
            try:
                result = self.supabase.table('sessions').select('*').eq('id', session_id).execute()
                if result.data:
                    row = result.data[0]
                    return {
                        'id': row['id'],
                        'module': row['module'],
                        'user_id': row.get('user_id'),
                        'user_email': row.get('user_email'),
                        'status': row.get('status', 'in_progress'),
                        'collected_data': row.get('collected_data') or {},
                        'messages': row.get('messages') or [],
                        'output_document': row.get('output_document'),
                        'created_at': row.get('created_at'),
                        'updated_at': row.get('updated_at')
                    }
            except Exception as e:
                print(f"Supabase 获取会话失败，回退到 SQLite: {e}")

        # 回退到 SQLite
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
                'collected_data': self._safe_json_loads(row['collected_data'], {}),
                'messages': self._safe_json_loads(row['messages'], []),
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

        now = datetime.now().isoformat()

        # 优先尝试 Supabase
        if self.use_supabase:
            try:
                self.supabase.table('sessions').update({
                    'messages': messages,
                    'updated_at': now
                }).eq('id', session_id).execute()
                return True
            except Exception as e:
                print(f"Supabase 添加消息失败，回退到 SQLite: {e}")

        # 回退到 SQLite
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

        now = datetime.now().isoformat()

        # 优先尝试 Supabase
        if self.use_supabase:
            try:
                self.supabase.table('sessions').update({
                    'collected_data': collected_data,
                    'updated_at': now
                }).eq('id', session_id).execute()
                return True
            except Exception as e:
                print(f"Supabase 更新数据失败，回退到 SQLite: {e}")

        # 回退到 SQLite
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
        now = datetime.now().isoformat()

        # 优先尝试 Supabase
        if self.use_supabase:
            try:
                self.supabase.table('sessions').update({
                    'output_document': document,
                    'status': 'completed',
                    'updated_at': now
                }).eq('id', session_id).execute()
                return True
            except Exception as e:
                print(f"Supabase 保存文档失败，回退到 SQLite: {e}")

        # 回退到 SQLite
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
        """获取用于API调用的消息格式（智能压缩版）"""
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
            return self._simple_truncate(all_messages, max_chars)

    def _simple_truncate(self, messages: List[Dict], max_chars: int) -> List[Dict]:
        """智能截断（降级方案）- 保留关键上下文"""
        if not messages:
            return []

        api_messages = []

        # 保留第一条
        first_msg = messages[0]
        api_messages.append({'role': first_msg['role'], 'content': first_msg['content']})
        first_len = len(first_msg.get('content', ''))

        # 提取用户输入摘要
        user_inputs_summary = []
        for msg in messages[1:]:
            if msg.get('role') == 'user':
                content = msg.get('content', '')[:300]
                user_inputs_summary.append(f"- {content}")

        if user_inputs_summary:
            summary = "【历史对话摘要】用户之前提供的信息：\n" + "\n".join(user_inputs_summary[-10:])
            api_messages.append({
                'role': 'system',
                'content': summary + "\n\n请基于以上信息继续对话，不要重复询问已提供的信息。"
            })

        # 计算剩余空间
        used_chars = first_len + len(api_messages[-1]['content']) if len(api_messages) > 1 else first_len
        remaining_chars = max_chars - used_chars - 1000

        # 从最近的消息往前加
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
        # 优先尝试 Supabase
        if self.use_supabase:
            try:
                result = self.supabase.table('sessions').select(
                    'id, module, status, created_at, updated_at'
                ).order('updated_at', desc=True).limit(limit).execute()
                return result.data or []
            except Exception as e:
                print(f"Supabase 列出会话失败，回退到 SQLite: {e}")

        # 回退到 SQLite
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
        # 优先尝试 Supabase
        if self.use_supabase:
            try:
                result = self.supabase.table('sessions').select(
                    'id, module, user_id, user_email, status, messages, created_at, updated_at'
                ).order('updated_at', desc=True).limit(limit).execute()

                sessions = []
                for row in (result.data or []):
                    session_dict = dict(row)
                    session_dict['session_id'] = session_dict['id']
                    session_dict['messages'] = row.get('messages') or []
                    session_dict['message_count'] = len(session_dict['messages'])
                    sessions.append(session_dict)
                return sessions
            except Exception as e:
                print(f"Supabase 获取管理会话失败，回退到 SQLite: {e}")

        # 回退到 SQLite
        conn = self._get_conn()
        cursor = conn.cursor()
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
            session_dict['session_id'] = session_dict['id']
            session_dict['messages'] = self._safe_json_loads(session_dict['messages'], [])
            session_dict['message_count'] = len(session_dict['messages'])
            result.append(session_dict)
        return result

    def get_user_sessions(self, user_id: str, limit: int = 20) -> List[Dict]:
        """获取指定用户的所有会话（带预览）"""
        # 优先尝试 Supabase
        if self.use_supabase:
            try:
                result = self.supabase.table('sessions').select(
                    'id, module, status, messages, created_at, updated_at'
                ).eq('user_id', user_id).order('updated_at', desc=True).limit(limit).execute()

                sessions = []
                for row in (result.data or []):
                    session_dict = dict(row)
                    messages = row.get('messages') or []
                    session_dict['messages'] = messages

                    # 生成预览
                    preview = '新对话'
                    for msg in messages:
                        if msg.get('role') == 'user':
                            content = msg.get('content', '')
                            preview = content[:50] + ('...' if len(content) > 50 else '')
                            break
                    session_dict['preview'] = preview
                    sessions.append(session_dict)
                return sessions
            except Exception as e:
                print(f"Supabase 获取用户会话失败，回退到 SQLite: {e}")

        # 回退到 SQLite
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
            messages = self._safe_json_loads(session_dict['messages'], [])
            session_dict['messages'] = messages

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

    # ========================================
    # 预充值管理（用户未注册时先存储积分）
    # ========================================

    def add_pending_credits(self, phone: str, credits: int, reason: str = "管理员预充值",
                           admin_name: str = "admin") -> Tuple[bool, str, str]:
        """
        添加预充值记录

        Args:
            phone: 手机号
            credits: 积分数量
            reason: 充值原因
            admin_name: 操作管理员

        Returns: (成功?, 消息, 预充值ID)
        """
        try:
            # 🔴 规范化手机号（去除空格和横杠），确保与查询时格式一致
            phone = phone.strip().replace(' ', '').replace('-', '')

            conn = self._get_conn()
            cursor = conn.cursor()

            record_id = str(uuid.uuid4())
            cursor.execute('''
                INSERT INTO pending_credits (id, phone, credits, reason, admin_name, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)
            ''', (record_id, phone, credits, reason, admin_name))

            conn.commit()
            conn.close()
            return True, f"已为手机号 {phone} 预充值 {credits} 积分，用户注册后自动到账", record_id
        except Exception as e:
            print(f"添加预充值记录失败: {e}")
            return False, f"预充值失败: {e}", ""

    def get_pending_credits_by_phone(self, phone: str) -> List[Dict]:
        """
        获取指定手机号的所有待发放预充值记录

        Args:
            phone: 手机号

        Returns: 预充值记录列表
        """
        try:
            # 🔴 规范化手机号
            phone = phone.strip().replace(' ', '').replace('-', '')

            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, phone, credits, reason, admin_name, status, created_at
                FROM pending_credits
                WHERE phone = ? AND status = 'pending'
                ORDER BY created_at ASC
            ''', (phone,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"获取预充值记录失败: {e}")
            return []

    def claim_pending_credits(self, phone: str, user_id: str) -> Tuple[int, List[Dict]]:
        """
        领取预充值积分（用户注册时调用）

        Args:
            phone: 手机号
            user_id: 用户ID

        Returns: (总领取积分数, 领取的记录列表)
        """
        try:
            # 🔴 规范化手机号
            phone = phone.strip().replace(' ', '').replace('-', '')

            conn = self._get_conn()
            cursor = conn.cursor()

            # 获取所有待发放的记录
            cursor.execute('''
                SELECT id, credits, reason, admin_name, created_at
                FROM pending_credits
                WHERE phone = ? AND status = 'pending'
            ''', (phone,))
            rows = cursor.fetchall()

            if not rows:
                conn.close()
                return 0, []

            total_credits = 0
            claimed_records = []

            for row in rows:
                record = dict(row)
                total_credits += record['credits']
                claimed_records.append(record)

                # 标记为已领取
                cursor.execute('''
                    UPDATE pending_credits
                    SET status = 'claimed', claimed_at = CURRENT_TIMESTAMP, claimed_user_id = ?
                    WHERE id = ?
                ''', (user_id, record['id']))

            conn.commit()
            conn.close()
            return total_credits, claimed_records
        except Exception as e:
            print(f"领取预充值积分失败: {e}")
            return 0, []

    def rollback_pending_credits(self, record_ids: List[str]) -> bool:
        """
        回滚预充值记录状态（当 add_credits 失败时调用）
        将 claimed 状态改回 pending

        Args:
            record_ids: 需要回滚的记录 ID 列表

        Returns: 是否成功
        """
        if not record_ids:
            return True

        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            for record_id in record_ids:
                cursor.execute('''
                    UPDATE pending_credits
                    SET status = 'pending', claimed_at = NULL, claimed_user_id = NULL
                    WHERE id = ?
                ''', (record_id,))

            conn.commit()
            conn.close()
            print(f"[预充值] 回滚了 {len(record_ids)} 条记录")
            return True
        except Exception as e:
            print(f"回滚预充值记录失败: {e}")
            return False

    def get_all_pending_credits(self, status: str = None, limit: int = 100) -> List[Dict]:
        """
        获取所有预充值记录（管理后台用）

        Args:
            status: 状态筛选（'pending' / 'claimed' / None表示全部）
            limit: 数量限制

        Returns: 预充值记录列表
        """
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            if status:
                cursor.execute('''
                    SELECT id, phone, credits, reason, admin_name, status, claimed_at, claimed_user_id, created_at
                    FROM pending_credits
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                ''', (status, limit))
            else:
                cursor.execute('''
                    SELECT id, phone, credits, reason, admin_name, status, claimed_at, claimed_user_id, created_at
                    FROM pending_credits
                    ORDER BY created_at DESC
                    LIMIT ?
                ''', (limit,))

            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"获取预充值记录列表失败: {e}")
            return []

    # ========================================
    # 用户调研记录管理
    # ========================================

    def get_research_notes_by_user(self, user_email: str) -> List[Dict]:
        """获取用户的所有调研记录（按时间倒序）"""
        # 优先尝试 Supabase
        if self.use_supabase:
            try:
                result = self.supabase.table('user_research_notes').select('*') \
                    .eq('user_email', user_email) \
                    .order('created_at', desc=True) \
                    .execute()
                return result.data or []
            except Exception as e:
                print(f"Supabase 获取调研记录失败，回退到 SQLite: {e}")

        # 回退到 SQLite
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM user_research_notes
            WHERE user_email = ?
            ORDER BY created_at DESC
        ''', (user_email,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def create_research_note(
        self,
        user_email: str,
        category: str,
        content: str = '',
        file_url: str = None,
        file_name: str = None,
        file_type: str = None,
        file_text_content: str = None,
        notes: str = '',
        created_by: str = 'admin'
    ) -> str:
        """创建新的调研记录"""
        note_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        # 优先尝试 Supabase
        if self.use_supabase:
            try:
                self.supabase.table('user_research_notes').insert({
                    'id': note_id,
                    'user_email': user_email,
                    'category': category,
                    'content': content,
                    'file_url': file_url,
                    'file_name': file_name,
                    'file_type': file_type,
                    'file_text_content': file_text_content,
                    'notes': notes,
                    'created_by': created_by,
                    'created_at': now,
                    'updated_at': now
                }).execute()
                return note_id
            except Exception as e:
                print(f"Supabase 创建调研记录失败，回退到 SQLite: {e}")

        # 回退到 SQLite
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_research_notes
            (id, user_email, category, content, file_url, file_name, file_type,
             file_text_content, notes, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (note_id, user_email, category, content, file_url, file_name,
              file_type, file_text_content, notes, created_by, now, now))
        conn.commit()
        conn.close()
        return note_id

    def delete_research_note(self, note_id: str) -> bool:
        """删除调研记录"""
        # 优先尝试 Supabase
        if self.use_supabase:
            try:
                self.supabase.table('user_research_notes').delete().eq('id', note_id).execute()
                return True
            except Exception as e:
                print(f"Supabase 删除调研记录失败，回退到 SQLite: {e}")

        # 回退到 SQLite
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM user_research_notes WHERE id = ?', (note_id,))
        conn.commit()
        conn.close()
        return True

    def get_research_notes_text_for_analysis(self, user_email: str) -> str:
        """获取用户调研记录的文本内容（用于 AI 分析）"""
        notes = self.get_research_notes_by_user(user_email)
        if not notes:
            return ""

        # 分类标签映射
        category_names = {
            'phone_call': '电话沟通录音转文字',
            'site_visit': '现场拜访',
            'wechat_chat': '微信沟通',
            'email': '邮件沟通',
            'meeting': '会议记录',
            'survey': '问卷调研',
            'other': '其他'
        }

        text_parts = []
        for note in notes:
            category = note.get('category', 'other')
            category_name = category_names.get(category, category)
            created_at = note.get('created_at', '')[:10]

            text_parts.append(f"\n--- 调研记录 ({category_name}) - {created_at} ---")

            if note.get('content'):
                text_parts.append(note['content'])

            if note.get('file_text_content'):
                text_parts.append(f"[文件内容: {note.get('file_name', 'unknown')}]")
                text_parts.append(note['file_text_content'])

            if note.get('notes'):
                text_parts.append(f"[备注] {note['notes']}")

        return '\n'.join(text_parts)


# 单例实例
db = Database()
