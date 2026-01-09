"""
用户认证服务 - 注册、登录、积分管理
"""
import hashlib
import time
from typing import Optional, Dict, Tuple
from modules.supabase_client import get_client


class AuthService:
    """用户认证和积分管理服务"""

    # 配置：商学院用户初始积分
    BUSINESS_SCHOOL_CREDITS = 2000
    # 配置：普通用户默认积分（如果没有猫币）
    DEFAULT_CREDITS = 10
    # 配置：每次对话消耗积分
    CREDITS_PER_CHAT = 2
    # 配置：管理员微信
    ADMIN_WECHAT = "huohuo1616"

    def __init__(self):
        self.client = get_client()

    @staticmethod
    def calculate_credits_from_cat_coins(cat_coins: int) -> int:
        """
        根据猫币数量计算积分
        规则：每个猫币 = 20积分
        """
        if cat_coins <= 0:
            return 0
        return cat_coins * 20

    def _generate_email(self, username: str) -> str:
        """
        根据用户名生成有效的邮箱地址
        使用 MD5 哈希确保唯一性和兼容性
        """
        # 使用用户名的哈希值作为邮箱前缀（支持中文）
        hash_str = hashlib.md5(username.encode('utf-8')).hexdigest()[:12]
        return f"user_{hash_str}@kpi-tool.com"

    # ========================================
    # 用户认证
    # ========================================

    def register(self, username: str, password: str, company: str = None, position: str = None,
                 user_type: str = 'normal', cat_coins: int = 0) -> Tuple[bool, str, Dict]:
        """
        用户注册（使用姓名作为标识符）

        Args:
            username: 用户名
            password: 密码
            company: 公司名称
            position: 职位
            user_type: 用户类型 ('business_school' 商学院 / 'normal' 普通用户)
            cat_coins: 猫币数量（仅普通用户）

        返回: (成功?, 消息, 用户数据)
        """
        try:
            # 计算初始积分
            if user_type == 'business_school':
                initial_credits = self.BUSINESS_SCHOOL_CREDITS
                credit_reason = '商学院学员注册赠送'
            elif cat_coins > 0:
                initial_credits = self.calculate_credits_from_cat_coins(cat_coins)
                credit_reason = f'猫币兑换（{cat_coins}个猫币）'
            else:
                initial_credits = self.DEFAULT_CREDITS
                credit_reason = '新用户注册赠送'

            # 生成有效的邮箱地址（支持中文姓名）
            pseudo_email = self._generate_email(username)

            # 注册用户（Supabase Auth）
            response = self.client.auth.sign_up({
                "email": pseudo_email,
                "password": password,
                "options": {
                    "data": {
                        "username": username,
                        "company": company or '',
                        "position": position or ''
                    }
                }
            })

            if response.user:
                # 注册成功后立即创建 profile 记录（确保 company/position 被保存）
                self._create_profile(
                    user_id=response.user.id,
                    username=username,
                    company=company or '',
                    position=position or '',
                    email=pseudo_email,
                    initial_credits=initial_credits,
                    credit_reason=credit_reason,
                    user_type=user_type,
                    cat_coins=cat_coins
                )

                return True, "注册成功！", {
                    "user_id": response.user.id,
                    "username": username,
                    "credits": initial_credits,
                    "user_type": user_type
                }
            else:
                return False, "注册失败，请稍后重试", {}

        except Exception as e:
            error_msg = str(e)
            if "already registered" in error_msg.lower():
                return False, "该姓名已注册，请直接登录", {}
            return False, f"注册失败: {error_msg}", {}

    def login(self, username: str, password: str) -> Tuple[bool, str, Dict]:
        """
        用户登录（使用姓名）
        返回: (成功?, 消息, 用户数据)
        """
        try:
            # 生成相同的邮箱地址（与注册时一致）
            pseudo_email = self._generate_email(username)

            response = self.client.auth.sign_in_with_password({
                "email": pseudo_email,
                "password": password
            })

            if response.user:
                # 获取用户资料和积分
                profile = self.get_profile(response.user.id)

                # 从 user metadata 获取真实用户名
                user_meta = response.user.user_metadata or {}
                real_username = user_meta.get('username', username)

                # 如果没有 profile，创建一个（兼容旧用户）
                if not profile:
                    company = user_meta.get('company', '')
                    position = user_meta.get('position', '')
                    profile = self._create_profile(response.user.id, real_username, company, position, pseudo_email)
                else:
                    # profile 存在但可能缺少 company/position，尝试更新
                    if not profile.get('company') or not profile.get('position'):
                        company = user_meta.get('company', '') or profile.get('company', '')
                        position = user_meta.get('position', '') or profile.get('position', '')
                        if company or position:
                            try:
                                self.client.table('profiles').update({
                                    'company': company,
                                    'position': position
                                }).eq('id', response.user.id).execute()
                                profile['company'] = company
                                profile['position'] = position
                            except Exception as update_err:
                                # 如果字段不存在，忽略更新
                                if 'company' not in str(update_err) and 'position' not in str(update_err):
                                    print(f"更新 profile 失败（不影响登录）: {update_err}")

                return True, "登录成功", {
                    "user_id": response.user.id,
                    "username": real_username,
                    "email": response.user.email,  # 保留以兼容
                    "access_token": response.session.access_token,
                    "profile": profile
                }
            else:
                return False, "登录失败", {}

        except Exception as e:
            error_msg = str(e)
            if "invalid" in error_msg.lower():
                return False, "姓名或密码错误", {}
            return False, f"登录失败: {error_msg}", {}

    def _create_profile(self, user_id: str, username: str, company: str = '', position: str = '',
                        email: str = None, initial_credits: int = None, credit_reason: str = '新用户注册赠送',
                        user_type: str = 'normal', cat_coins: int = 0) -> Dict:
        """为用户创建或更新 profile（注册或首次登录时）"""
        try:
            # 生成 email（如果没有提供）
            if not email:
                email = f"{username.replace(' ', '_')}@kpi.local"

            # 确定初始积分
            if initial_credits is None:
                initial_credits = self.DEFAULT_CREDITS

            # 基本数据（不包含可能不存在的字段）
            base_data = {
                'nickname': username,  # 使用真实姓名
                'credits': initial_credits,
                'user_type': user_type,  # 用户类型
                'cat_coins': cat_coins   # 猫币数量
            }

            # 尝试更新现有记录（Supabase Auth 可能已通过触发器创建了 profile）
            try:
                # 首先尝试只更新 nickname 和 credits
                self.client.table('profiles').update(base_data).eq('id', user_id).execute()
            except Exception as update_err:
                # 如果更新失败，尝试插入新记录
                print(f"更新 profile 失败，尝试插入: {update_err}")
                try:
                    insert_data = {
                        'id': user_id,
                        'email': email,
                        'nickname': username,
                        'credits': self.INITIAL_CREDITS
                    }
                    self.client.table('profiles').insert(insert_data).execute()
                except Exception as insert_err:
                    print(f"插入 profile 也失败（可能已存在）: {insert_err}")

            # 尝试更新 company/position（如果字段存在）
            try:
                if company or position:
                    update_fields = {}
                    if company:
                        update_fields['company'] = company
                    if position:
                        update_fields['position'] = position
                    if update_fields:
                        self.client.table('profiles').update(update_fields).eq('id', user_id).execute()
            except Exception as field_err:
                # 字段不存在或权限问题，忽略
                print(f"更新 company/position 失败（可能字段不存在）: {field_err}")

            # 记录初始积分（忽略 RLS 权限错误，不影响主流程）
            try:
                self.client.table('credit_logs').insert({
                    'user_id': user_id,
                    'amount': initial_credits,
                    'balance': initial_credits,
                    'reason': credit_reason
                }).execute()
            except Exception as log_err:
                print(f"记录初始积分日志失败（不影响注册）: {log_err}")

            return {
                'id': user_id,
                'username': username,
                'nickname': username,
                'company': company,
                'position': position,
                'credits': initial_credits,
                'user_type': user_type,
                'cat_coins': cat_coins
            }
        except Exception as e:
            print(f"创建 profile 失败: {e}")
            return None

    def logout(self) -> bool:
        """登出"""
        try:
            self.client.auth.sign_out()
            return True
        except Exception as e:
            print(f"登出失败: {e}")
            return False

    def get_current_user(self) -> Optional[Dict]:
        """获取当前登录用户"""
        try:
            response = self.client.auth.get_user()
            if response and response.user:
                return {
                    "user_id": response.user.id,
                    "email": response.user.email
                }
        except Exception as e:
            print(f"获取当前用户失败: {e}")
        return None

    # ========================================
    # 用户资料
    # ========================================

    def get_profile(self, user_id: str) -> Optional[Dict]:
        """获取用户资料（含积分）"""
        try:
            response = self.client.table('profiles').select('*').eq('id', user_id).single().execute()
            return response.data
        except Exception as e:
            print(f"获取用户资料失败: {e}")
            return None

    # ========================================
    # 积分系统
    # ========================================

    def get_credits(self, user_id: str) -> int:
        """获取用户积分余额"""
        profile = self.get_profile(user_id)
        return profile.get('credits', 0) if profile else 0

    def use_credits(self, user_id: str, amount: int, reason: str = "AI对话消耗") -> Tuple[bool, str, int]:
        """
        消耗积分（使用乐观锁防止竞态条件）
        返回: (成功?, 消息, 剩余积分)
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 获取当前积分
                current_credits = self.get_credits(user_id)

                if current_credits < amount:
                    return False, f"积分不足，当前: {current_credits}，需要: {amount}", current_credits

                # 计算新余额
                new_balance = current_credits - amount

                # 使用乐观锁更新：只有当 credits 仍等于 current_credits 时才更新
                # 这可以防止并发请求导致的双重扣费
                response = self.client.table('profiles').update({
                    'credits': new_balance
                }).eq('id', user_id).eq('credits', current_credits).execute()

                # 检查是否成功更新（如果没有匹配的行，说明 credits 已被其他请求修改）
                if not response.data or len(response.data) == 0:
                    # 并发冲突，重试
                    if attempt < max_retries - 1:
                        time.sleep(0.1 * (attempt + 1))  # 退避重试
                        continue
                    else:
                        return False, "操作冲突，请重试", current_credits

                # 更新成功，记录积分变动（忽略 RLS 权限错误）
                try:
                    self.client.table('credit_logs').insert({
                        'user_id': user_id,
                        'amount': -amount,
                        'balance': new_balance,
                        'reason': reason
                    }).execute()
                except Exception as log_err:
                    print(f"记录积分日志失败（不影响扣费）: {log_err}")

                return True, f"消耗 {amount} 积分", new_balance

            except Exception as e:
                if attempt < max_retries - 1:
                    continue
                return False, f"扣费失败: {str(e)}", 0

        return False, "扣费失败，请重试", 0

    def add_credits(self, user_id: str, amount: int, reason: str = "充值") -> Tuple[bool, str, int]:
        """
        增加积分
        返回: (成功?, 消息, 新余额)
        """
        try:
            current_credits = self.get_credits(user_id)
            new_balance = current_credits + amount

            # 更新积分
            self.client.table('profiles').update({
                'credits': new_balance
            }).eq('id', user_id).execute()

            # 记录积分变动（忽略 RLS 权限错误）
            try:
                self.client.table('credit_logs').insert({
                    'user_id': user_id,
                    'amount': amount,
                    'balance': new_balance,
                    'reason': reason
                }).execute()
            except Exception as log_err:
                print(f"记录积分日志失败（不影响充值）: {log_err}")

            return True, f"增加 {amount} 积分", new_balance

        except Exception as e:
            return False, f"充值失败: {str(e)}", 0

    def get_credit_logs(self, user_id: str, limit: int = 20) -> list:
        """获取积分变动记录"""
        try:
            response = self.client.table('credit_logs')\
                .select('*')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()
            return response.data
        except Exception as e:
            print(f"获取积分记录失败: {e}")
            return []


# 单例服务
auth_service = AuthService()
