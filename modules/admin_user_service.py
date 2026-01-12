"""
管理员用户管理服务 - 支持动态添加/删除管理员
"""
import os
import bcrypt
import hashlib
import secrets
import string
from typing import Optional, List, Dict, Tuple
from modules.supabase_client import get_admin


class AdminUserService:
    """管理员用户管理服务"""

    def __init__(self):
        self.client = get_admin()
        self._ensure_table()

    def _generate_random_password(self, length: int = 16) -> str:
        """生成安全的随机密码"""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        return password

    def _ensure_table(self):
        """确保 admin_users 表存在（首次运行时会自动创建）"""
        # 表结构由 Supabase SQL 创建，这里只做初始化检查
        pass

    def _hash_password(self, password: str) -> str:
        """密码哈希（使用 bcrypt 安全哈希）"""
        salt = bcrypt.gensalt()
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
        return password_hash.decode('utf-8')

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """验证密码是否匹配（bcrypt）"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except Exception:
            return False

    def _verify_password_md5(self, password: str, password_hash: str) -> bool:
        """验证旧的 MD5 密码（仅用于迁移）"""
        try:
            md5_hash = hashlib.md5(password.encode('utf-8')).hexdigest()
            return md5_hash == password_hash
        except Exception:
            return False

    def _is_md5_hash(self, password_hash: str) -> bool:
        """判断是否为 MD5 哈希（32位十六进制字符）"""
        return len(password_hash) == 32 and all(c in '0123456789abcdef' for c in password_hash.lower())

    def get_all_admins(self) -> List[Dict]:
        """获取所有普通管理员列表"""
        try:
            response = self.client.table('admin_users').select('*').eq('is_deleted', False).order('created_at', desc=True).execute()
            return response.data or []
        except Exception as e:
            print(f"获取管理员列表失败: {e}")
            return []

    def add_admin(self, username: str, created_by: str, note: str = '') -> Tuple[bool, str, Dict]:
        """
        添加普通管理员（生成随机安全密码）

        Args:
            username: 管理员用户名
            created_by: 创建者（主管理员用户名）
            note: 备注

        Returns: (成功?, 消息, 管理员数据)
        """
        try:
            # 检查用户名是否已存在
            existing = self.client.table('admin_users').select('id').eq('username', username).eq('is_deleted', False).execute()
            if existing.data:
                return False, "该用户名已存在", {}

            # 生成随机安全密码
            random_password = self._generate_random_password()

            # 创建管理员
            admin_data = {
                'username': username,
                'password_hash': self._hash_password(random_password),
                'created_by': created_by,
                'note': note,
                'is_deleted': False
            }

            response = self.client.table('admin_users').insert(admin_data).execute()

            if response.data:
                return True, f"管理员 {username} 创建成功，默认密码：{random_password}（请妥善保管）", response.data[0]
            else:
                return False, "创建失败", {}

        except Exception as e:
            return False, f"创建失败: {str(e)}", {}

    def delete_admin(self, admin_id: str) -> Tuple[bool, str]:
        """
        删除管理员（软删除）

        Args:
            admin_id: 管理员 ID

        Returns: (成功?, 消息)
        """
        try:
            response = self.client.table('admin_users').update({
                'is_deleted': True
            }).eq('id', admin_id).execute()

            if response.data:
                return True, "管理员已删除"
            else:
                return False, "删除失败，管理员不存在"

        except Exception as e:
            return False, f"删除失败: {str(e)}"

    def reset_password(self, admin_id: str) -> Tuple[bool, str]:
        """
        重置管理员密码为随机安全密码

        Args:
            admin_id: 管理员 ID

        Returns: (成功?, 消息)
        """
        try:
            # 生成随机安全密码
            random_password = self._generate_random_password()

            response = self.client.table('admin_users').update({
                'password_hash': self._hash_password(random_password)
            }).eq('id', admin_id).execute()

            if response.data:
                return True, f"密码已重置为：{random_password}（请妥善保管）"
            else:
                return False, "重置失败，管理员不存在"

        except Exception as e:
            return False, f"重置失败: {str(e)}"

    def verify_admin(self, username: str, password: str) -> Tuple[bool, Optional[Dict]]:
        """
        验证普通管理员登录（支持 MD5 到 bcrypt 的平滑迁移）

        Args:
            username: 用户名
            password: 密码

        Returns: (验证通过?, 管理员数据)
        """
        try:
            # 先获取用户记录
            response = self.client.table('admin_users').select('*').eq('username', username).eq('is_deleted', False).execute()

            if not response.data:
                return False, None

            admin_data = response.data[0]
            password_hash = admin_data['password_hash']

            # 优先尝试 bcrypt 验证
            if self._verify_password(password, password_hash):
                return True, admin_data

            # 如果 bcrypt 验证失败，检查是否为旧的 MD5 密码
            if self._is_md5_hash(password_hash):
                if self._verify_password_md5(password, password_hash):
                    # MD5 验证成功，立即升级为 bcrypt
                    print(f"检测到旧密码格式，正在为用户 {username} 升级密码加密...")
                    new_hash = self._hash_password(password)

                    # 更新数据库
                    update_response = self.client.table('admin_users').update({
                        'password_hash': new_hash
                    }).eq('id', admin_data['id']).execute()

                    if update_response.data:
                        print(f"用户 {username} 的密码已成功升级为 bcrypt 加密")
                        admin_data['password_hash'] = new_hash

                    return True, admin_data

            return False, None

        except Exception as e:
            print(f"验证管理员失败: {e}")
            return False, None


# 单例服务
admin_user_service = AdminUserService()
