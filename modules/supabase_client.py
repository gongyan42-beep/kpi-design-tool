"""
Supabase 客户端模块 - 用户认证和数据存储
"""
from supabase import create_client, Client
from config import Config


def get_supabase_client() -> Client:
    """获取 Supabase 客户端实例（anon key，受 RLS 限制）"""
    if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
        raise ValueError("Supabase 配置缺失，请检查 .env 文件")

    return create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)


def get_admin_client() -> Client:
    """获取 Supabase 管理员客户端（service_role key，绕过 RLS）"""
    if not Config.SUPABASE_URL or not Config.SUPABASE_SERVICE_KEY:
        # 如果没有 service_key，回退到普通 key
        print("警告：SUPABASE_SERVICE_KEY 未配置，使用普通 key")
        return get_supabase_client()

    return create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_KEY)


# 单例客户端
supabase: Client = None
admin_supabase: Client = None

def get_client() -> Client:
    """获取单例客户端（anon key）"""
    global supabase
    if supabase is None:
        supabase = get_supabase_client()
    return supabase


def get_admin() -> Client:
    """获取管理员单例客户端（service_role key）"""
    global admin_supabase
    if admin_supabase is None:
        admin_supabase = get_admin_client()
    return admin_supabase
