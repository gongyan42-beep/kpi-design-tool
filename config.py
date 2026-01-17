import os
from dotenv import load_dotenv

# 在 Docker 环境中不覆盖环境变量
# 检查是否在 Docker 中运行（通过检查 FLASK_ENV=production）
is_docker = os.getenv('FLASK_ENV') == 'production'
load_dotenv(override=not is_docker)

class Config:
    # 端口（Docker 环境使用环境变量，本地使用 .env）
    PORT = int(os.getenv('KPI_PORT', os.getenv('PORT', 5009)))

    # AI API配置 - 双 API 自动切换
    # 主用：云雾 API（便宜）
    YUNWU_API_KEY = os.getenv('YUNWU_API_KEY')
    YUNWU_BASE_URL = os.getenv('YUNWU_BASE_URL', 'https://api.yunwu.ai/v1')
    # 备用：CloseAI（更快）
    CLOSEAI_API_KEY = os.getenv('CLOSEAI_API_KEY')
    CLOSEAI_BASE_URL = os.getenv('CLOSEAI_BASE_URL', 'https://api.closeai-asia.com/v1')
    DEFAULT_MODEL = os.getenv('DEFAULT_MODEL', 'gemini-3-flash-preview')

    # 可用模型
    AVAILABLE_MODELS = {
        'flash': 'gemini-3-flash-preview',
        'pro': 'gemini-3-pro-preview'
    }

    # Flask配置
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')

    # Session 配置 - 保持登录状态 30 天
    PERMANENT_SESSION_LIFETIME = 30 * 24 * 60 * 60  # 30天（秒）

    # 数据库
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/kpi_tool.db')

    # Supabase 配置
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')  # 管理员权限 key

    # 飞书多维表格配置（数据备份）
    FEISHU_APP_ID = os.getenv('FEISHU_APP_ID')
    FEISHU_APP_SECRET = os.getenv('FEISHU_APP_SECRET')
    FEISHU_BITABLE_APP_TOKEN = os.getenv('FEISHU_BITABLE_APP_TOKEN')
    FEISHU_TABLE_PROFILES = os.getenv('FEISHU_TABLE_PROFILES')
    FEISHU_TABLE_CREDIT_LOGS = os.getenv('FEISHU_TABLE_CREDIT_LOGS')
    FEISHU_TABLE_SESSIONS = os.getenv('FEISHU_TABLE_SESSIONS')
    FEISHU_TABLE_REDEEM_CODES = os.getenv('FEISHU_TABLE_REDEEM_CODES')
    FEISHU_TABLE_ADMIN_LOGS = os.getenv('FEISHU_TABLE_ADMIN_LOGS')
    FEISHU_SYNC_ENABLED = os.getenv('FEISHU_SYNC_ENABLED', 'true').lower() == 'true'

    # 管理后台密码
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')

    # 6大模块定义
    MODULES = {
        'market_price': {
            'name': '市场价',
            'icon': '💰',
            'color': '#0e9f6e',
            'description': '确定岗位的市场薪资范围',
            'subtitle': '员工薪资 = 市场上能获得的最高价格'
        },
        'kpi': {
            'name': 'KPI',
            'icon': '📊',
            'color': '#1a56db',
            'description': '设计薪资结构和考核指标',
            'subtitle': '底薪 + 岗位工资 + 绩效，聚焦3个核心指标'
        },
        'okr': {
            'name': 'OKR',
            'icon': '🎯',
            'color': '#9061f9',
            'description': '策略训练工具（5%员工适用）',
            'subtitle': '训练员工理解业务和业绩的因果关系'
        },
        'strategy': {
            'name': '战略',
            'icon': '🚀',
            'color': '#ff8a4c',
            'description': '规划产品和渠道增量',
            'subtitle': '战略 = 增量，发现增量的能力'
        },
        'organization': {
            'name': '组织',
            'icon': '👥',
            'color': '#0694a2',
            'description': '规划人才和组织架构',
            'subtitle': '增量需要什么人才，今天如何准备'
        },
        'recruitment': {
            'name': '招人选人',
            'icon': '🔍',
            'color': '#f05252',
            'description': '制定招聘方案和选人标准',
            'subtitle': '具体的招聘和选人方法'
        }
    }
