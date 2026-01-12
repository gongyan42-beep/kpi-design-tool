# AI 自我验证工作流程

## 核心原理

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌─────┐  │
│   │ 修改代码 │ -> │ 运行验证 │ -> │ 看结果   │ -> │迭代 │  │
│   └──────────┘    └──────────┘    └──────────┘    └─────┘  │
│        ^                                            │       │
│        └────────────────────────────────────────────┘       │
│                      反馈循环                                │
└─────────────────────────────────────────────────────────────┘
```

## 方式 1: 手动验证脚本

```bash
# 1. Claude 修改代码
# 2. 运行验证
python verify.py

# 3. 查看截图
# verify_screenshot.png 会显示页面状态

# 4. 根据结果迭代
```

## 方式 2: Claude Code Hooks（自动触发）

在 `.claude/settings.json` 中配置：

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python verify.py"
          }
        ]
      }
    ]
  }
}
```

这样每次 Claude 修改文件后，都会**自动运行验证**。

## 方式 3: 浏览器自动化详解

### 安装 Playwright

```bash
pip install playwright
playwright install chromium
```

### 验证脚本能做什么

1. **截图** - Claude 可以看到页面实际渲染效果
2. **收集控制台错误** - 捕获 JavaScript 错误
3. **检查 HTTP 状态** - 确保 API 正常响应
4. **提取页面错误文本** - 自动发现显示的错误信息

### 更高级：交互式测试

```python
# 模拟用户操作
page.click("#login-button")
page.fill("#username", "test@example.com")
page.click("button[type='submit']")

# 验证结果
assert page.query_selector(".success-message")
```

## 方式 4: 测试套件（推荐生产项目）

```bash
# 添加 pytest
pip install pytest pytest-flask

# 运行测试
pytest tests/ -v
```

## 实际案例

### 场景：修改管理后台界面

1. **用户请求**: "把管理后台的标题改成红色"

2. **Claude 修改代码**:
   ```python
   # 修改 templates/admin.html
   <h1 style="color: red;">管理后台</h1>
   ```

3. **Claude 运行验证**:
   ```bash
   python verify.py
   ```

4. **验证结果**:
   ```
   ✅ 服务器运行中 (HTTP 200)
   ✅ /admin -> 200
   ✅ 截图已保存: verify_screenshot.png
   🎉 验证通过！
   ```

5. **Claude 查看截图确认修改生效**

6. **如果有问题，迭代修改直到验证通过**

## 关键配置文件

- `verify.py` - 验证脚本
- `.claude/settings.json` - Claude Code hooks 配置
- `requirements.txt` - 添加 playwright 依赖

## 为什么这样做能提升 2-3 倍质量？

1. **即时反馈** - 不用等人来测试
2. **全面检查** - 自动检查 HTTP 状态、JS 错误、页面渲染
3. **可复现** - 每次修改都经过相同验证流程
4. **迭代快** - 发现问题立即修复，不会积累
