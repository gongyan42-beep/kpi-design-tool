#!/usr/bin/env python3
"""
飞书多维表格自动创建脚本
创建 KPI 工具数据备份所需的 5 张表
"""
import os
import sys
import time
import json
import requests
from pathlib import Path

# 加载 .devrc 中的配置
DEVRC_PATH = Path.home() / '.devrc'
if DEVRC_PATH.exists():
    with open(DEVRC_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

FEISHU_APP_ID = os.getenv('FEISHU_APP_ID')
FEISHU_APP_SECRET = os.getenv('FEISHU_APP_SECRET')

if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
    print("❌ 错误：未找到飞书 APP_ID 或 APP_SECRET")
    print("请在 ~/.devrc 中配置：")
    print("  FEISHU_APP_ID=xxx")
    print("  FEISHU_APP_SECRET=xxx")
    sys.exit(1)

BASE_URL = "https://open.feishu.cn/open-apis"


def get_token():
    """获取 tenant_access_token"""
    url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={
        "app_id": FEISHU_APP_ID,
        "app_secret": FEISHU_APP_SECRET
    }, timeout=15)
    data = resp.json()

    if data.get("code") != 0:
        print(f"❌ 获取 Token 失败: {data}")
        sys.exit(1)

    return data["tenant_access_token"]


def api_request(token, method, path, **kwargs):
    """发起飞书 API 请求"""
    url = f"{BASE_URL}{path}"
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    headers["Content-Type"] = "application/json"

    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    data = resp.json()

    if data.get("code") != 0:
        print(f"❌ API 错误 [{path}]: {data.get('code')} - {data.get('msg')}")
        return None

    return data


def create_bitable_app(token, name="KPI工具数据备份"):
    """创建多维表格应用"""
    print(f"\n📦 创建多维表格应用: {name}")

    # 创建多维表格
    data = api_request(token, "POST", "/bitable/v1/apps", json={
        "name": name
    })

    if not data:
        return None

    app_token = data["data"]["app"]["app_token"]
    print(f"   ✅ 创建成功! app_token: {app_token}")
    return app_token


def create_table(token, app_token, table_name, fields):
    """在多维表格中创建数据表"""
    print(f"\n📋 创建数据表: {table_name}")

    data = api_request(token, "POST", f"/bitable/v1/apps/{app_token}/tables", json={
        "table": {
            "name": table_name,
            "fields": fields
        }
    })

    if not data:
        return None

    table_id = data["data"]["table_id"]
    print(f"   ✅ 创建成功! table_id: {table_id}")
    return table_id


def main():
    print("=" * 50)
    print("🚀 飞书多维表格自动创建脚本")
    print("=" * 50)

    # 获取 Token
    print("\n🔐 获取飞书 Token...")
    token = get_token()
    print("   ✅ Token 获取成功")

    # 创建多维表格应用
    app_token = create_bitable_app(token, "KPI工具数据备份")
    if not app_token:
        print("\n❌ 创建多维表格应用失败")
        sys.exit(1)

    time.sleep(0.5)  # 等待创建完成

    # 表结构定义
    tables_config = {
        "用户资料": [
            {"field_name": "用户ID", "type": 1},      # 1=文本
            {"field_name": "昵称", "type": 1},
            {"field_name": "公司", "type": 1},
            {"field_name": "手机号", "type": 1},
            {"field_name": "积分余额", "type": 2},     # 2=数字
            {"field_name": "猫币", "type": 2},
            {"field_name": "用户类型", "type": 3, "property": {  # 3=单选
                "options": [
                    {"name": "normal"},
                    {"name": "business_school"}
                ]
            }},
            {"field_name": "创建时间", "type": 5},     # 5=日期
            {"field_name": "更新时间", "type": 5},
        ],
        "积分变动": [
            {"field_name": "记录ID", "type": 1},
            {"field_name": "用户ID", "type": 1},
            {"field_name": "变动金额", "type": 2},
            {"field_name": "变动后余额", "type": 2},
            {"field_name": "原因", "type": 1},
            {"field_name": "创建时间", "type": 5},
        ],
        "对话会话": [
            {"field_name": "会话ID", "type": 1},
            {"field_name": "模块", "type": 3, "property": {
                "options": [
                    {"name": "market_price"},
                    {"name": "kpi"},
                    {"name": "okr"},
                    {"name": "strategy"},
                    {"name": "organization"},
                    {"name": "recruitment"}
                ]
            }},
            {"field_name": "用户ID", "type": 1},
            {"field_name": "用户邮箱", "type": 1},
            {"field_name": "状态", "type": 3, "property": {
                "options": [
                    {"name": "in_progress"},
                    {"name": "completed"}
                ]
            }},
            {"field_name": "消息数量", "type": 2},
            {"field_name": "创建时间", "type": 5},
            {"field_name": "更新时间", "type": 5},
        ],
        "兑换码": [
            {"field_name": "记录ID", "type": 1},
            {"field_name": "兑换码", "type": 1},
            {"field_name": "目标用户", "type": 1},
            {"field_name": "积分", "type": 2},
            {"field_name": "猫币", "type": 2},
            {"field_name": "创建人", "type": 1},
            {"field_name": "备注", "type": 1},
            {"field_name": "是否使用", "type": 7},     # 7=复选框
            {"field_name": "使用时间", "type": 5},
            {"field_name": "使用者ID", "type": 1},
            {"field_name": "创建时间", "type": 5},
        ],
        "管理员日志": [
            {"field_name": "记录ID", "type": 1},
            {"field_name": "管理员", "type": 1},
            {"field_name": "操作类型", "type": 3, "property": {
                "options": [
                    {"name": "PROMPT_CREATE"},
                    {"name": "PROMPT_UPDATE"},
                    {"name": "PROMPT_DELETE"},
                    {"name": "REDEEM_CREATE"},
                    {"name": "REDEEM_USE"},
                    {"name": "ADMIN_CREATE"},
                    {"name": "ADMIN_DELETE"},
                    {"name": "CREDIT_ADD"},
                    {"name": "OTHER"}
                ]
            }},
            {"field_name": "操作目标", "type": 1},
            {"field_name": "详情", "type": 1},
            {"field_name": "创建时间", "type": 5},
        ],
    }

    # 创建各数据表
    table_ids = {}
    for table_name, fields in tables_config.items():
        table_id = create_table(token, app_token, table_name, fields)
        if table_id:
            table_ids[table_name] = table_id
        time.sleep(0.3)  # 避免请求过快

    # 输出结果
    print("\n" + "=" * 50)
    print("✅ 创建完成！")
    print("=" * 50)

    print(f"\n📋 多维表格 app_token: {app_token}")
    print("\n📋 各数据表 table_id:")
    for name, tid in table_ids.items():
        print(f"   {name}: {tid}")

    # 生成 .env 配置
    print("\n" + "=" * 50)
    print("📝 请将以下配置添加到 .env 文件:")
    print("=" * 50)
    env_config = f"""
# ========================================
# 飞书多维表格同步配置
# ========================================
FEISHU_BITABLE_APP_TOKEN={app_token}
FEISHU_TABLE_PROFILES={table_ids.get('用户资料', '')}
FEISHU_TABLE_CREDIT_LOGS={table_ids.get('积分变动', '')}
FEISHU_TABLE_SESSIONS={table_ids.get('对话会话', '')}
FEISHU_TABLE_REDEEM_CODES={table_ids.get('兑换码', '')}
FEISHU_TABLE_ADMIN_LOGS={table_ids.get('管理员日志', '')}
FEISHU_SYNC_ENABLED=true
"""
    print(env_config)

    # 保存配置到临时文件
    config_file = Path(__file__).parent.parent / "feishu_config.txt"
    with open(config_file, "w") as f:
        f.write(env_config)
    print(f"\n💾 配置已保存到: {config_file}")

    # 打开飞书多维表格链接
    print(f"\n🔗 多维表格链接: https://your-domain.feishu.cn/base/{app_token}")
    print("   （请在飞书中打开查看）")


if __name__ == "__main__":
    main()
