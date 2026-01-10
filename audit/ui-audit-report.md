# KPI 项目 UI 交互审查报告

> 审查时间：2026-01-10
> 审查工具：静态代码分析 + axe-core 可访问性检测

---

## 一、发现的问题汇总

### 🔴 严重问题（影响核心功能）

| # | 问题 | 位置 | 状态 |
|---|-----|-----|------|
| 1 | 弹窗打开时背景可滚动（滚动穿透） | `chat.html` 弹窗 | 待修复 |
| 2 | 图片预览弹窗无法用 ESC 关闭 | `chat.html:2468-2479` | 待修复 |
| 3 | 历史菜单下拉没有键盘导航支持 | `chat.html:2183-2244` | 待修复 |
| 4 | textarea 没有 label 关联（可访问性） | `chat.html:1902-1909` | 待修复 |

### 🟡 中等问题（影响用户体验）

| # | 问题 | 位置 | 状态 |
|---|-----|-----|------|
| 5 | 删除确认用 confirm()，体验差 | `chat.html:2194` | 待优化 |
| 6 | 重命名用 prompt()，体验差 | `chat.html:2217` | 待优化 |
| 7 | 快捷回复按钮没有 aria-label | `chat.html` 快捷按钮 | 待修复 |
| 8 | 模型下拉没有 role="listbox" | `chat.html:1928` | 待修复 |
| 9 | 用户头像点击无反馈/功能 | `chat.html:1874` | 待优化 |
| 10 | 图片删除按钮太小（20x20px < 44px） | `chat.html:1585-1606` | 待修复 |

### 🟢 轻微问题（可优化项）

| # | 问题 | 位置 | 状态 |
|---|-----|-----|------|
| 11 | 超小屏幕积分隐藏但仍占 DOM | `chat.html:1539-1542` | 建议 |
| 12 | 历史列表没有空状态骨架屏 | `chat.html:2100` | 建议 |
| 13 | 消息操作按钮仅 hover 显示，手机端不友好 | `chat.html:1131-1135` | 已处理 |
| 14 | Toast 没有 role="alert" | `chat.html` showToast | 待修复 |
| 15 | 部分按钮缺少 title 属性 | 多处 | 待补充 |

---

## 二、问题详细分析与修复方案

### 🔴 问题 1：弹窗滚动穿透

**现象**：打开积分弹窗、登录弹窗时，滚动鼠标滚轮会让背景页面一起滚动

**原因**：没有在弹窗打开时锁定 body 滚动

**修复方案**：
```javascript
// 打开弹窗时
document.body.style.overflow = 'hidden';

// 关闭弹窗时
document.body.style.overflow = '';
```

---

### 🔴 问题 2：图片预览弹窗无 ESC 关闭

**现象**：点击图片放大后，按 ESC 键无法关闭

**修复方案**：
```javascript
function showImagePreview(src) {
    const overlay = document.createElement('div');
    // ... 现有代码 ...

    // 添加 ESC 关闭
    const handleEsc = (e) => {
        if (e.key === 'Escape') {
            overlay.remove();
            document.removeEventListener('keydown', handleEsc);
        }
    };
    document.addEventListener('keydown', handleEsc);
}
```

---

### 🔴 问题 3：历史菜单无键盘导航

**现象**：下拉菜单只能鼠标点击，无法用键盘 Tab/Enter 操作

**修复方案**：
```html
<div class="history-dropdown" role="menu" tabindex="-1">
    <div class="history-dropdown-item" role="menuitem" tabindex="0">重命名</div>
    <div class="history-dropdown-item" role="menuitem" tabindex="0">删除</div>
</div>
```

---

### 🔴 问题 4：textarea 无 label

**现象**：屏幕阅读器无法识别输入框用途

**修复方案**：
```html
<label for="message-input" class="sr-only">输入您的问题</label>
<textarea id="message-input" ...></textarea>

<!-- CSS 隐藏但保留给屏幕阅读器 -->
<style>
.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    border: 0;
}
</style>
```

---

### 🟡 问题 10：图片删除按钮太小

**现象**：20x20px 的按钮在手机上很难点中

**修复方案**：
```css
.image-preview-remove {
    width: 28px;  /* 增大 */
    height: 28px;
    /* 或用 padding 扩大点击区域但保持视觉大小 */
    padding: 8px;
    box-sizing: content-box;
}
```

---

## 三、axe-core 可访问性检测脚本

在浏览器控制台运行以下脚本进行自动检测：

```html
<!-- 方法 1：添加到页面 -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.2/axe.min.js"></script>
<script>
axe.run().then(results => {
    console.log('可访问性问题：', results.violations.length);
    results.violations.forEach(v => {
        console.group(v.id + ' (' + v.impact + ')');
        console.log('描述:', v.description);
        console.log('影响元素:', v.nodes.map(n => n.html));
        console.log('修复建议:', v.help);
        console.groupEnd();
    });
});
</script>
```

```javascript
// 方法 2：控制台直接运行
(async function() {
    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.2/axe.min.js';
    document.head.appendChild(script);

    await new Promise(r => script.onload = r);

    const results = await axe.run();

    console.log('%c=== 可访问性审查报告 ===', 'font-size:16px;font-weight:bold;color:#1a73e8');
    console.log(`发现 ${results.violations.length} 个问题\n`);

    results.violations.forEach((v, i) => {
        const color = v.impact === 'critical' ? '#d93025' :
                      v.impact === 'serious' ? '#f9ab00' : '#5f6368';
        console.log(`%c${i+1}. [${v.impact}] ${v.id}`, `color:${color};font-weight:bold`);
        console.log(`   ${v.description}`);
        console.log(`   修复: ${v.help}`);
        console.log(`   影响 ${v.nodes.length} 个元素`);
    });
})();
```

---

## 四、完整 UI 审查脚本

```javascript
// 综合 UI 审查脚本 - 在控制台运行
(function auditUI() {
    const issues = [];

    // 1. 检查触摸目标太小
    document.querySelectorAll('button, a, [onclick]').forEach(el => {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
            if (rect.width < 44 || rect.height < 44) {
                issues.push({
                    type: '触摸目标过小',
                    severity: 'medium',
                    element: el.className || el.tagName,
                    size: `${Math.round(rect.width)}x${Math.round(rect.height)}`,
                    suggest: '建议至少 44x44px'
                });
            }
        }
    });

    // 2. 检查没有 alt 的图片
    document.querySelectorAll('img:not([alt])').forEach(img => {
        issues.push({
            type: '图片缺少 alt',
            severity: 'high',
            element: img.src.split('/').pop(),
            suggest: '添加 alt 属性'
        });
    });

    // 3. 检查没有 label 的 input/textarea
    document.querySelectorAll('input, textarea, select').forEach(el => {
        const id = el.id;
        const hasLabel = id && document.querySelector(`label[for="${id}"]`);
        const hasAriaLabel = el.getAttribute('aria-label');
        if (!hasLabel && !hasAriaLabel) {
            issues.push({
                type: '表单缺少 label',
                severity: 'high',
                element: el.id || el.name || el.tagName,
                suggest: '添加 <label for="..."> 或 aria-label'
            });
        }
    });

    // 4. 检查颜色对比度（简单检测）
    document.querySelectorAll('*').forEach(el => {
        const style = getComputedStyle(el);
        const color = style.color;
        const bg = style.backgroundColor;
        // 简化检测：检查是否使用了低对比度的灰色
        if (color.includes('rgb(156') || color.includes('rgb(158') || color.includes('rgb(160')) {
            if (bg.includes('rgb(255') || bg === 'transparent') {
                // 可能对比度不足
            }
        }
    });

    // 5. 检查没有 role 的交互元素
    document.querySelectorAll('[onclick]:not(button):not(a)').forEach(el => {
        if (!el.getAttribute('role')) {
            issues.push({
                type: '缺少 ARIA role',
                severity: 'medium',
                element: el.className || el.tagName,
                suggest: '添加 role="button" 或改用 <button>'
            });
        }
    });

    // 6. 检查 z-index 复杂度
    const zIndexes = [];
    document.querySelectorAll('*').forEach(el => {
        const z = parseInt(getComputedStyle(el).zIndex);
        if (!isNaN(z) && z > 10) {
            zIndexes.push({ el: el.className, z });
        }
    });
    if (zIndexes.length > 10) {
        issues.push({
            type: 'z-index 复杂',
            severity: 'low',
            element: `${zIndexes.length} 个元素`,
            suggest: '考虑简化层级管理'
        });
    }

    // 7. 检查超出视口的元素
    document.querySelectorAll('*').forEach(el => {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.right > window.innerWidth + 20) {
            issues.push({
                type: '元素超出视口',
                severity: 'high',
                element: el.className || el.tagName,
                suggest: '检查响应式布局'
            });
        }
    });

    // 输出报告
    console.log('%c=== UI 交互审查报告 ===', 'font-size:18px;font-weight:bold;color:#4285f4');
    console.log(`共发现 ${issues.length} 个问题\n`);

    const grouped = {};
    issues.forEach(i => {
        if (!grouped[i.type]) grouped[i.type] = [];
        grouped[i.type].push(i);
    });

    Object.entries(grouped).forEach(([type, items]) => {
        const color = items[0].severity === 'high' ? '#d93025' :
                      items[0].severity === 'medium' ? '#f9ab00' : '#5f6368';
        console.log(`%c${type} (${items.length}个)`, `color:${color};font-weight:bold`);
        items.slice(0, 5).forEach(i => {
            console.log(`  - ${i.element}: ${i.suggest}`);
        });
        if (items.length > 5) console.log(`  ... 还有 ${items.length - 5} 个`);
    });

    return issues;
})();
```

---

## 五、推荐的自动化测试方案

### 1. 安装 axe DevTools Chrome 插件
- Chrome 应用商店搜索 "axe DevTools"
- 免费版已足够日常使用
- 一键扫描页面可访问性问题

### 2. 集成到 CI/CD
```bash
# 安装
npm install -D @axe-core/playwright

# playwright 测试中使用
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('可访问性检查', async ({ page }) => {
    await page.goto('https://kpi.longgonghuohuo.com');
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
});
```

### 3. 日常开发流程
1. 开发完成后运行 `/ui-audit` skill
2. 用 axe DevTools 扫描页面
3. 在控制台运行上面的综合审查脚本
4. 修复所有 high/medium 级别问题

---

## 六、修复优先级建议

1. **立即修复**（影响可用性）
   - 弹窗滚动穿透
   - 图片预览 ESC 关闭
   - textarea 添加 label

2. **本周修复**（影响体验）
   - 删除/重命名改为模态框
   - 图片删除按钮增大
   - 添加 ARIA 属性

3. **后续优化**
   - 键盘导航支持
   - 骨架屏加载
   - 颜色对比度优化
