"""
兑换码服务 - 生成和兑换积分码
"""
import random
import string
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from modules.supabase_client import get_client
from modules.auth_service import AuthService


class RedeemService:
    """兑换码管理服务"""

    def __init__(self):
        self.client = get_client()

    @staticmethod
    def calculate_credits(cat_coins: int) -> int:
        """根据猫币数量计算积分（复用 AuthService 的逻辑）"""
        return AuthService.calculate_credits_from_cat_coins(cat_coins)

    def _generate_code(self, length: int = 8) -> str:
        """生成随机兑换码（大写字母+数字）"""
        chars = string.ascii_uppercase + string.digits
        # 排除容易混淆的字符
        chars = chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '').replace('L', '')
        return ''.join(random.choice(chars) for _ in range(length))

    def create_code(
        self,
        target_name: str,
        cat_coins: int,
        created_by: str,
        note: str = ''
    ) -> Tuple[bool, str, Dict]:
        """
        创建兑换码

        Args:
            target_name: 目标用户姓名
            cat_coins: 猫币数量
            created_by: 创建人（管理员）
            note: 备注

        Returns:
            (成功?, 消息, 兑换码数据)
        """
        if not self.client:
            return False, "数据库连接失败", {}

        if cat_coins <= 0:
            return False, "猫币数量必须大于0", {}

        # 计算积分
        credits = self.calculate_credits(cat_coins)

        try:
            # 生成唯一兑换码
            code = self._generate_code()

            # 检查是否重复（极小概率）
            existing = self.client.table('redeem_codes').select('id').eq('code', code).execute()
            if existing.data:
                code = self._generate_code(10)  # 重新生成更长的

            # 插入数据库
            data = {
                'code': code,
                'target_name': target_name,
                'cat_coins': cat_coins,
                'credits': credits,
                'created_by': created_by,
                'note': note,
                'is_used': False,
                'created_at': datetime.now().isoformat()
            }

            result = self.client.table('redeem_codes').insert(data).execute()

            if result.data:
                # 记录管理员操作日志
                try:
                    from modules.admin_log_service import admin_log_service
                    admin_log_service.log_redeem_create(
                        admin_name=created_by,
                        target_name=target_name,
                        cat_coins=cat_coins,
                        credits=credits,
                        code=code
                    )
                except Exception as log_err:
                    print(f"记录管理员日志失败: {log_err}")

                return True, "兑换码创建成功", result.data[0]
            else:
                return False, "创建失败", {}

        except Exception as e:
            return False, f"创建失败: {str(e)}", {}

    def create_code_with_credits(
        self,
        target_name: str,
        credits: int,
        created_by: str,
        note: str = ''
    ) -> Tuple[bool, str, Dict]:
        """
        创建兑换码（直接指定积分，用于商学院用户）

        Args:
            target_name: 目标用户姓名
            credits: 直接指定的积分数量
            created_by: 创建人（管理员）
            note: 备注

        Returns:
            (成功?, 消息, 兑换码数据)
        """
        if not self.client:
            return False, "数据库连接失败", {}

        if credits <= 0:
            return False, "积分数量必须大于0", {}

        try:
            # 生成唯一兑换码
            code = self._generate_code()

            # 检查是否重复（极小概率）
            existing = self.client.table('redeem_codes').select('id').eq('code', code).execute()
            if existing.data:
                code = self._generate_code(10)  # 重新生成更长的

            # 插入数据库
            data = {
                'code': code,
                'target_name': target_name,
                'cat_coins': 0,  # 商学院用户不使用猫币
                'credits': credits,
                'created_by': created_by,
                'note': note,
                'is_used': False,
                'created_at': datetime.now().isoformat()
            }

            result = self.client.table('redeem_codes').insert(data).execute()

            if result.data:
                # 记录管理员操作日志
                try:
                    from modules.admin_log_service import admin_log_service
                    admin_log_service.log_redeem_create(
                        admin_name=created_by,
                        target_name=target_name,
                        cat_coins=0,
                        credits=credits,
                        code=code
                    )
                except Exception as log_err:
                    print(f"记录管理员日志失败: {log_err}")

                return True, "兑换码创建成功", result.data[0]
            else:
                return False, "创建失败", {}

        except Exception as e:
            return False, f"创建失败: {str(e)}", {}

    def redeem_code(self, code: str, user_id: str) -> Tuple[bool, str, int]:
        """
        兑换积分码

        Args:
            code: 兑换码
            user_id: 用户ID

        Returns:
            (成功?, 消息, 获得的积分)
        """
        if not self.client:
            return False, "数据库连接失败", 0

        code = code.strip().upper()

        if not code:
            return False, "请输入兑换码", 0

        try:
            # 查找兑换码
            result = self.client.table('redeem_codes').select('*').eq('code', code).execute()

            if not result.data:
                return False, "兑换码不存在", 0

            redeem_data = result.data[0]

            # 检查是否已使用
            if redeem_data.get('is_used'):
                return False, "该兑换码已被使用", 0

            credits = redeem_data.get('credits', 0)

            # 标记为已使用
            self.client.table('redeem_codes').update({
                'is_used': True,
                'used_by': user_id,
                'used_at': datetime.now().isoformat()
            }).eq('code', code).execute()

            # 给用户增加积分
            from modules.auth_service import auth_service
            success, msg, new_balance = auth_service.add_credits(
                user_id,
                credits,
                f"兑换码充值: {code}"
            )

            if success:
                # 记录用户兑换日志
                try:
                    from modules.admin_log_service import admin_log_service
                    # 获取用户名
                    profile = auth_service.get_profile(user_id)
                    user_name = profile.get('nickname', '未知用户') if profile else '未知用户'
                    admin_log_service.log_redeem_used(
                        user_name=user_name,
                        user_id=user_id,
                        code=code,
                        credits=credits,
                        new_balance=new_balance
                    )
                except Exception as log_err:
                    print(f"记录用户兑换日志失败: {log_err}")

                return True, f"兑换成功！获得 {credits} 积分（{credits // 2} 次回答机会）", credits
            else:
                # 回滚：重新标记为未使用
                self.client.table('redeem_codes').update({
                    'is_used': False,
                    'used_by': None,
                    'used_at': None
                }).eq('code', code).execute()
                return False, f"积分添加失败: {msg}", 0

        except Exception as e:
            return False, f"兑换失败: {str(e)}", 0

    def get_all_codes(self, limit: int = 100) -> List[Dict]:
        """获取所有兑换码（管理后台用）"""
        if not self.client:
            return []

        try:
            result = self.client.table('redeem_codes').select('*').order('created_at', desc=True).limit(limit).execute()
            return result.data if result.data else []
        except Exception as e:
            print(f"获取兑换码列表失败: {e}")
            return []

    def delete_code(self, code_id: str) -> Tuple[bool, str]:
        """删除未使用的兑换码"""
        if not self.client:
            return False, "数据库连接失败"

        try:
            # 检查是否已使用
            result = self.client.table('redeem_codes').select('is_used').eq('id', code_id).execute()
            if result.data and result.data[0].get('is_used'):
                return False, "已使用的兑换码不能删除"

            self.client.table('redeem_codes').delete().eq('id', code_id).execute()
            return True, "删除成功"
        except Exception as e:
            return False, f"删除失败: {str(e)}"

    def batch_create_codes(
        self,
        credits: int,
        count: int,
        created_by: str,
        note: str = ''
    ) -> Tuple[bool, str, List[Dict]]:
        """
        批量生成兑换码（用户名留空）

        Args:
            credits: 每个兑换码的积分数量
            count: 生成数量
            created_by: 创建人（管理员）
            note: 备注

        Returns:
            (成功?, 消息, 兑换码列表)
        """
        if not self.client:
            return False, "数据库连接失败", []

        if credits <= 0:
            return False, "积分数量必须大于0", []

        if count <= 0 or count > 100:
            return False, "生成数量必须在1-100之间", []

        try:
            codes_data = []
            generated_codes = set()

            for _ in range(count):
                # 生成唯一兑换码
                code = self._generate_code()
                while code in generated_codes:
                    code = self._generate_code(10)
                generated_codes.add(code)

                # 检查数据库是否重复
                existing = self.client.table('redeem_codes').select('id').eq('code', code).execute()
                if existing.data:
                    code = self._generate_code(10)

                data = {
                    'code': code,
                    'target_name': '',  # 用户名留空
                    'cat_coins': 0,
                    'credits': credits,
                    'created_by': created_by,
                    'note': note or '批量生成',
                    'is_used': False,
                    'created_at': datetime.now().isoformat()
                }
                codes_data.append(data)

            # 批量插入数据库
            result = self.client.table('redeem_codes').insert(codes_data).execute()

            if result.data:
                # 记录管理员操作日志
                try:
                    from modules.admin_log_service import admin_log_service
                    admin_log_service.log_batch_redeem_create(
                        admin_name=created_by,
                        count=count,
                        credits=credits
                    )
                except Exception as log_err:
                    print(f"记录管理员日志失败: {log_err}")

                return True, f"成功生成 {count} 个兑换码", result.data
            else:
                return False, "批量创建失败", []

        except Exception as e:
            return False, f"批量创建失败: {str(e)}", []


# 单例实例
redeem_service = RedeemService()
