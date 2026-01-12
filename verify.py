#!/usr/bin/env python3
"""
AI 自我验证脚本 - 让 Claude 能验证自己的修改

使用方式：
1. Claude 修改代码后运行此脚本
2. 脚本会启动浏览器、截图、检查错误
3. Claude 根据结果决定是否需要迭代修改

安装依赖：pip install playwright && playwright install chromium
"""

import subprocess
import sys
import time
import requests
from pathlib import Path

# 尝试导入 playwright
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


def check_server_running(port=5009, timeout=10):
    """检查服务器是否在运行"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"http://localhost:{port}", timeout=2)
            return True, resp.status_code
        except:
            time.sleep(0.5)
    return False, None


def verify_with_playwright(url="http://localhost:5009", screenshot_path="verify_screenshot.png"):
    """
    用浏览器验证页面
    返回：(成功与否, 错误信息, 控制台日志)
    """
    if not HAS_PLAYWRIGHT:
        return False, "playwright 未安装，运行: pip install playwright && playwright install chromium", []

    console_logs = []
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 收集控制台日志
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))

        # 收集页面错误
        page.on("pageerror", lambda err: errors.append(str(err)))

        try:
            # 访问页面
            response = page.goto(url, wait_until="networkidle", timeout=30000)

            # 等待页面加载
            time.sleep(1)

            # 截图
            page.screenshot(path=screenshot_path)
            print(f"✅ 截图已保存: {screenshot_path}")

            # 检查 HTTP 状态
            if response.status >= 400:
                errors.append(f"HTTP 错误: {response.status}")

            # 检查页面是否有明显错误文本
            page_content = page.content()
            if "Error" in page_content or "错误" in page_content or "Exception" in page_content:
                # 提取错误信息
                error_elements = page.query_selector_all(".error, .alert-danger, [class*='error']")
                for el in error_elements[:3]:  # 只取前3个
                    errors.append(f"页面错误: {el.text_content()[:100]}")

            browser.close()

            if errors:
                return False, errors, console_logs
            return True, None, console_logs

        except Exception as e:
            browser.close()
            return False, [str(e)], console_logs


def verify_api_endpoints(base_url="http://localhost:5009"):
    """验证关键 API 端点"""
    endpoints = [
        ("/", "GET", 200),
        ("/admin", "GET", 200),
    ]

    results = []
    for path, method, expected_status in endpoints:
        try:
            resp = requests.request(method, f"{base_url}{path}", timeout=5)
            ok = resp.status_code == expected_status
            results.append({
                "endpoint": path,
                "status": resp.status_code,
                "expected": expected_status,
                "ok": ok
            })
        except Exception as e:
            results.append({
                "endpoint": path,
                "error": str(e),
                "ok": False
            })

    return results


def main():
    """主验证流程"""
    print("=" * 50)
    print("🔍 AI 自我验证开始")
    print("=" * 50)

    # 1. 检查服务器
    print("\n[1/3] 检查服务器状态...")
    running, status = check_server_running()
    if not running:
        print("❌ 服务器未运行！请先执行: ./start.sh")
        print("   或者在后台启动: nohup ./start.sh &")
        return 1
    print(f"✅ 服务器运行中 (HTTP {status})")

    # 2. API 端点验证
    print("\n[2/3] 验证 API 端点...")
    api_results = verify_api_endpoints()
    all_ok = True
    for r in api_results:
        if r.get("ok"):
            print(f"  ✅ {r['endpoint']} -> {r['status']}")
        else:
            print(f"  ❌ {r['endpoint']} -> {r.get('status', r.get('error'))}")
            all_ok = False

    # 3. 浏览器验证
    print("\n[3/3] 浏览器验证...")
    if HAS_PLAYWRIGHT:
        success, errors, console_logs = verify_with_playwright()

        if console_logs:
            print("\n  📋 控制台日志:")
            for log in console_logs[-10:]:  # 只显示最后10条
                print(f"    {log}")

        if success:
            print("\n✅ 浏览器验证通过")
        else:
            print("\n❌ 浏览器验证失败:")
            for err in errors:
                print(f"    - {err}")
            all_ok = False
    else:
        print("  ⚠️ playwright 未安装，跳过浏览器验证")
        print("  安装命令: pip install playwright && playwright install chromium")

    # 总结
    print("\n" + "=" * 50)
    if all_ok:
        print("🎉 验证通过！修改可以提交。")
        return 0
    else:
        print("⚠️ 发现问题，请检查上述错误并修改代码。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
