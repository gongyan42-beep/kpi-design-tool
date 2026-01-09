"""
初始化默认用户脚本
运行一次即可创建默认用户
"""
from modules.auth_service import auth_service

# 默认用户列表
DEFAULT_USERS = [
    {"username": "huahua", "password": "123456", "company": "猫课", "position": "管理员"},
    {"username": "jianghui", "password": "123456", "company": "猫课", "position": "管理员"},
    {"username": "huohuo", "password": "123456", "company": "猫课", "position": "管理员"},
    {"username": "maoke", "password": "123456", "company": "猫课", "position": "管理员"},
]

def init_default_users():
    """创建默认用户"""
    print("开始创建默认用户...")

    for user in DEFAULT_USERS:
        success, message, data = auth_service.register(
            username=user["username"],
            password=user["password"],
            company=user["company"],
            position=user["position"]
        )

        if success:
            print(f"✅ 用户 {user['username']} 创建成功")
        else:
            print(f"⚠️ 用户 {user['username']}: {message}")

    print("\n默认用户创建完成！")
    print("用户名: huahua, jianghui, huohuo, maoke")
    print("密码: 123456")

if __name__ == "__main__":
    init_default_users()
