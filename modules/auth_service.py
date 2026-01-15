"""
用户认证服务 - 注册、登录、积分管理
"""
import hashlib
import time
from typing import Optional, Dict, Tuple, List
from modules.supabase_client import get_client, get_admin


class AuthService:
    """用户认证和积分管理服务"""

    # 配置：商学院用户初始积分
    BUSINESS_SCHOOL_CREDITS = 2000
    # 配置：普通用户默认积分（如果没有猫币）
    DEFAULT_CREDITS = 10
    # 配置：每次对话消耗积分
    CREDITS_PER_CHAT = 2
    # 配置：管理员微信
    ADMIN_WECHAT = "猫课工作人员"

    def __init__(self):
        self.client = get_client()
        self.admin_client = get_admin()  # 用于 profile 更新（绕过 RLS）

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
                 phone: str = None, user_type: str = 'normal', cat_coins: int = 0) -> Tuple[bool, str, Dict]:
        """
        用户注册（使用姓名作为标识符）

        Args:
            username: 用户名
            password: 密码
            company: 公司名称
            position: 职位
            phone: 手机号（选填）
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
                # 注册成功后立即创建 profile 记录（确保 company/position/phone 被保存）
                self._create_profile(
                    user_id=response.user.id,
                    username=username,
                    company=company or '',
                    position=position or '',
                    phone=phone or '',
                    email=pseudo_email,
                    initial_credits=initial_credits,
                    credit_reason=credit_reason,
                    user_type=user_type,
                    cat_coins=cat_coins
                )

                # 检查是否有预充值积分需要发放
                pending_credits = 0
                pending_records = []
                if phone:
                    try:
                        from database import db
                        pending_credits, pending_records = db.claim_pending_credits(phone, response.user.id)

                        if pending_credits > 0:
                            # 将预充值积分追加到用户账户
                            success, msg, _ = self.add_credits(response.user.id, pending_credits, '预充值积分自动到账')
                            if success:
                                print(f"[注册] 用户 {username} 领取预充值积分 {pending_credits}")
                            else:
                                # 🔴 add_credits 失败，回滚预充值记录状态
                                print(f"[注册] add_credits 失败: {msg}，回滚预充值记录")
                                record_ids = [r['id'] for r in pending_records]
                                db.rollback_pending_credits(record_ids)
                                pending_credits = 0  # 重置，避免误导用户
                                pending_records = []
                    except Exception as pending_err:
                        print(f"[注册] 检查预充值积分失败: {pending_err}")

                total_credits = initial_credits + pending_credits
                message = "注册成功！"
                if pending_credits > 0:
                    message = f"注册成功！您有 {pending_credits} 积分的预充值已自动到账"

                return True, message, {
                    "user_id": response.user.id,
                    "username": username,
                    "credits": total_credits,
                    "initial_credits": initial_credits,
                    "pending_credits": pending_credits,
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
        用户登录（支持手机号或姓名）
        返回: (成功?, 消息, 用户数据)
        """
        import re
        try:
            login_identifier = username.strip()

            # 判断是手机号还是姓名
            if re.match(r'^1[3-9]\d{9}$', login_identifier):
                # 是手机号，先查找对应的用户
                user = self.find_user_by_phone(login_identifier)
                if not user:
                    return False, "该手机号尚未注册", {}
                # 获取真实的姓名
                real_name = user.get('nickname') or user.get('email', '').split('@')[0].replace('user_', '')
                # 尝试用 email 直接登录（更可靠）
                pseudo_email = user.get('email')
            else:
                # 是姓名，生成伪邮箱
                real_name = login_identifier
                pseudo_email = self._generate_email(login_identifier)

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
                                self.admin_client.table('profiles').update({
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
                        phone: str = '', email: str = None, initial_credits: int = None,
                        credit_reason: str = '新用户注册赠送',
                        user_type: str = 'normal', cat_coins: int = 0) -> Dict:
        """为用户创建或更新 profile（注册或首次登录时）"""
        try:
            import time

            # 生成 email（如果没有提供）
            if not email:
                email = f"{username.replace(' ', '_')}@kpi.local"

            # 确定初始积分
            if initial_credits is None:
                initial_credits = self.DEFAULT_CREDITS

            # 🔴 等待 Supabase 触发器先创建 profile（触发器可能设置了错误的默认值）
            time.sleep(0.3)

            # 基本数据 - 只包含肯定存在的字段
            base_data = {
                'nickname': username,
                'credits': initial_credits  # 强制覆盖数据库默认值
            }

            # 使用重试机制确保更新成功
            max_retries = 5
            update_success = False

            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        time.sleep(0.3 * attempt)  # 递增等待

                    # 用 admin_client 更新 profile（绕过 RLS）
                    result = self.admin_client.table('profiles').update(base_data).eq('id', user_id).execute()

                    if result.data:
                        # 🔴 验证积分是否正确更新
                        verify = self.admin_client.table('profiles').select('credits').eq('id', user_id).single().execute()
                        if verify.data and verify.data.get('credits') == initial_credits:
                            update_success = True
                            print(f"[注册] 积分设置成功: {initial_credits}")
                            break
                        else:
                            # 积分不对，再次更新
                            print(f"[注册] 积分验证失败，重试... 当前值: {verify.data.get('credits') if verify.data else 'None'}")
                            continue

                except Exception as update_err:
                    print(f"[注册] 更新 profile 尝试 {attempt+1} 失败: {update_err}")
                    if attempt == max_retries - 1:
                        # 最后一次尝试，尝试插入
                        try:
                            insert_data = {
                                'id': user_id,
                                'email': email,
                                'nickname': username,
                                'credits': initial_credits
                            }
                            self.admin_client.table('profiles').insert(insert_data).execute()
                            update_success = True
                        except Exception as insert_err:
                            print(f"[注册] 插入 profile 也失败: {insert_err}")

            # 尝试更新 company/position/phone
            try:
                update_fields = {}
                if company:
                    update_fields['company'] = company
                if position:
                    update_fields['position'] = position
                if phone:
                    update_fields['phone'] = phone
                if update_fields:
                    self.admin_client.table('profiles').update(update_fields).eq('id', user_id).execute()
            except Exception as field_err:
                print(f"更新 company/position/phone 失败: {field_err}")

            # 记录初始积分日志
            try:
                self.admin_client.table('credit_logs').insert({
                    'user_id': user_id,
                    'amount': initial_credits,
                    'balance': initial_credits,
                    'reason': credit_reason
                }).execute()
            except Exception as log_err:
                print(f"记录初始积分日志失败: {log_err}")

            # 飞书同步：异步备份新用户资料
            try:
                from modules.feishu_sync import feishu_sync_service
                from datetime import datetime
                feishu_sync_service.sync_profile_async({
                    'id': user_id,
                    'nickname': username,
                    'company': company,
                    'phone': phone,
                    'credits': initial_credits,
                    'cat_coins': cat_coins,
                    'user_type': user_type,
                    'created_at': datetime.now().isoformat()
                })
                # 同时备份初始积分日志
                feishu_sync_service.sync_credit_log_async({
                    'id': f"{user_id}_init",
                    'user_id': user_id,
                    'amount': initial_credits,
                    'balance': initial_credits,
                    'reason': credit_reason,
                    'created_at': datetime.now().isoformat()
                })
            except:
                pass  # 飞书同步失败不影响注册

            return {
                'id': user_id,
                'username': username,
                'nickname': username,
                'company': company,
                'position': position,
                'phone': phone,
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
                response = self.admin_client.table('profiles').update({
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
                    self.admin_client.table('credit_logs').insert({
                        'user_id': user_id,
                        'amount': -amount,
                        'balance': new_balance,
                        'reason': reason
                    }).execute()
                except Exception as log_err:
                    print(f"记录积分日志失败（不影响扣费）: {log_err}")

                # 飞书同步：异步备份积分变动
                try:
                    from modules.feishu_sync import feishu_sync_service
                    from datetime import datetime
                    feishu_sync_service.sync_credit_log_async({
                        'id': f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        'user_id': user_id,
                        'amount': -amount,
                        'balance': new_balance,
                        'reason': reason,
                        'created_at': datetime.now().isoformat()
                    })
                except:
                    pass  # 飞书同步失败不影响主流程

                return True, f"消耗 {amount} 积分", new_balance

            except Exception as e:
                if attempt < max_retries - 1:
                    continue
                return False, f"扣费失败: {str(e)}", 0

        return False, "扣费失败，请重试", 0

    def add_credits(self, user_id: str, amount: int, reason: str = "充值") -> Tuple[bool, str, int]:
        """
        增加积分（使用乐观锁防止并发问题）
        返回: (成功?, 消息, 新余额)
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                current_credits = self.get_credits(user_id)
                new_balance = current_credits + amount

                # 使用乐观锁更新：只有当 credits 仍等于 current_credits 时才更新
                response = self.admin_client.table('profiles').update({
                    'credits': new_balance
                }).eq('id', user_id).eq('credits', current_credits).execute()

                # 检查是否成功更新
                if not response.data or len(response.data) == 0:
                    # 并发冲突，重试
                    if attempt < max_retries - 1:
                        time.sleep(0.1 * (attempt + 1))
                        continue
                    else:
                        return False, "操作冲突，请重试", current_credits

                # 记录积分变动（忽略 RLS 权限错误）
                try:
                    self.admin_client.table('credit_logs').insert({
                        'user_id': user_id,
                        'amount': amount,
                        'balance': new_balance,
                        'reason': reason
                    }).execute()
                except Exception as log_err:
                    print(f"记录积分日志失败（不影响充值）: {log_err}")

                # 飞书同步：异步备份积分变动
                try:
                    from modules.feishu_sync import feishu_sync_service
                    from datetime import datetime
                    feishu_sync_service.sync_credit_log_async({
                        'id': f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        'user_id': user_id,
                        'amount': amount,
                        'balance': new_balance,
                        'reason': reason,
                        'created_at': datetime.now().isoformat()
                    })
                except:
                    pass  # 飞书同步失败不影响主流程

                return True, f"增加 {amount} 积分", new_balance

            except Exception as e:
                if attempt < max_retries - 1:
                    continue
                return False, f"充值失败: {str(e)}", 0

        return False, "充值失败，请重试", 0

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

    # ========================================
    # 手机号相关操作
    # ========================================

    def find_user_by_phone(self, phone: str) -> Optional[Dict]:
        """通过手机号查找用户"""
        if not phone:
            return None

        try:
            # 规范化手机号（去除空格和横杠）
            phone = phone.strip().replace(' ', '').replace('-', '')

            response = self.admin_client.table('profiles').select('*').eq('phone', phone).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            print(f"通过手机号查找用户失败: {e}")
            return None

    def add_credits_by_phone(self, phone: str, amount: int, reason: str = "管理员充值",
                             admin_name: str = "admin") -> Tuple[bool, str, int, Optional[Dict]]:
        """
        通过手机号给用户充值积分（支持预充值）

        如果用户已注册：直接充值
        如果用户未注册：创建预充值记录，用户注册后自动到账

        Args:
            phone: 手机号
            amount: 积分数量
            reason: 充值原因
            admin_name: 操作管理员

        Returns: (成功?, 消息, 新余额或预充值积分, 用户数据或None)
        """
        # 查找用户
        user = self.find_user_by_phone(phone)

        if user:
            # 用户存在，直接充值
            user_id = user.get('id')
            user_name = user.get('nickname') or user.get('email', '未知用户')

            # 增加积分
            success, msg, new_balance = self.add_credits(user_id, amount, reason)

            if success:
                # 记录管理员操作日志
                try:
                    from modules.admin_log_service import admin_log_service
                    admin_log_service.log_credits_add(
                        admin_name=admin_name,
                        target_user=f"{user_name} ({phone})",
                        cat_coins=0,
                        credits=amount,
                        reason=reason
                    )
                except Exception as log_err:
                    print(f"记录管理员操作日志失败: {log_err}")

                return True, f"成功为 {user_name} 充值 {amount} 积分", new_balance, user
            else:
                return False, msg, 0, user
        else:
            # 用户不存在，创建预充值记录
            try:
                from database import db
                success, msg, record_id = db.add_pending_credits(
                    phone=phone,
                    credits=amount,
                    reason=reason,
                    admin_name=admin_name
                )

                if success:
                    # 记录管理员操作日志
                    try:
                        from modules.admin_log_service import admin_log_service
                        admin_log_service.log_credits_add(
                            admin_name=admin_name,
                            target_user=f"预充值 ({phone})",
                            cat_coins=0,
                            credits=amount,
                            reason=f"{reason}（预充值-待用户注册）"
                        )
                    except Exception as log_err:
                        print(f"记录管理员操作日志失败: {log_err}")

                    return True, msg, amount, None
                else:
                    return False, msg, 0, None
            except Exception as e:
                print(f"创建预充值记录失败: {e}")
                return False, f"预充值失败: {e}", 0, None


# 单例服务
auth_service = AuthService()
