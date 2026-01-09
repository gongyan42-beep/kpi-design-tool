"""
Supabase 客户端模块 - 用户认证和数据存储
"""
from supabase import create_client, Client
from config import Config


def get_supabase_client() -> Client:
    """获取 Supabase 客户端实例"""
    if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
        raise ValueError("Supabase 配置缺失，请检查 .env 文件")

    return create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)


# 单例客户端
supabase: Client = None

def get_client() -> Client:
    """获取单例客户端"""
    global supabase
    if supabase is None:
        supabase = get_supabase_client()
    return supabase
