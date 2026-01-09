/**
 * 猫课电商管理落地班 - 对话逻辑
 * 支持流式输出（打字机效果）
 */

let sessionId = null;
let isLoading = false;

/**
 * 保存 sessionId 到 localStorage（关闭浏览器后仍可恢复）
 */
function saveSessionId(id) {
    sessionId = id;
    if (id && typeof MODULE !== 'undefined') {
        localStorage.setItem(`chat_session_${MODULE}`, id);
        // 同时记录时间戳，用于判断是否过期
        localStorage.setItem(`chat_session_${MODULE}_time`, Date.now().toString());
    }
}

/**
 * 从 localStorage 恢复 sessionId
 * 超过7天的会话视为过期
 */
function restoreSessionId() {
    if (typeof MODULE !== 'undefined') {
        const savedId = localStorage.getItem(`chat_session_${MODULE}`);
        const savedTime = localStorage.getItem(`chat_session_${MODULE}_time`);

        if (savedId && savedTime) {
            const ageInDays = (Date.now() - parseInt(savedTime)) / (1000 * 60 * 60 * 24);
            if (ageInDays < 7) {
                return savedId;
            } else {
                // 过期了，清除
                localStorage.removeItem(`chat_session_${MODULE}`);
                localStorage.removeItem(`chat_session_${MODULE}_time`);
            }
        }
    }
    return null;
}

/**
 * HTML 转义，防止 XSS 攻击
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 初始化对话
 */
async function initChat(module) {
    // 先尝试恢复之前的会话
    const savedSessionId = restoreSessionId();
    if (savedSessionId) {
        try {
            const res = await fetch(`/api/session/${savedSessionId}/resume`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                saveSessionId(data.session_id);
                // 渲染历史消息
                (data.messages || []).forEach(msg => {
                    addMessage(msg.role, msg.content);
                });
                // 显示恢复成功提示
                showToast('已恢复上次对话', 'success');
                // 恢复待发送的消息（如果有）
                restorePendingMessage(module);
                return;
            } else {
                // 会话不存在或无权访问，清除本地缓存
                clearLocalSession(module);
            }
        } catch (e) {
            console.log('恢复会话失败，创建新会话');
            clearLocalSession(module);
        }
    }

    // 创建新会话
    try {
        const response = await fetch('/api/session/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ module })
        });

        const data = await response.json();

        if (data.success) {
            saveSessionId(data.session_id);
            addMessage('assistant', data.welcome_message, true);  // 显示快捷回复按钮
            // 恢复待发送的消息（如果有）
            restorePendingMessage(module);
        } else {
            showError('初始化失败: ' + data.error);
        }
    } catch (error) {
        showError('网络错误: ' + error.message);
    }
}

/**
 * 恢复待发送的消息（登录过期后重新登录时使用）
 */
function restorePendingMessage(module) {
    const pendingModule = localStorage.getItem('pending_message_module');
    const pendingMessage = localStorage.getItem('pending_message');

    if (pendingMessage && pendingModule === module) {
        const input = document.getElementById('message-input');
        if (input) {
            input.value = pendingMessage;
            autoResizeTextarea(input);
            showToast('已恢复您之前输入的内容', 'success');
        }
        // 清除已恢复的内容
        localStorage.removeItem('pending_message');
        localStorage.removeItem('pending_message_module');
    }
}

/**
 * 清除本地会话缓存
 */
function clearLocalSession(module) {
    const mod = module || (typeof MODULE !== 'undefined' ? MODULE : '');
    if (mod) {
        localStorage.removeItem(`chat_session_${mod}`);
        localStorage.removeItem(`chat_session_${mod}_time`);
    }
}

/**
 * 显示 Toast 提示
 */
function showToast(message, type = 'info') {
    // 移除已有的 toast
    const existing = document.querySelector('.toast-notification');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast-notification toast-${type}`;
    toast.textContent = message;

    document.body.appendChild(toast);

    // 3秒后消失
    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * 发送消息（流式输出版本）
 */
async function sendMessage() {
    if (isLoading) return;

    // 立即禁用按钮，防止重复点击
    const sendBtn = document.getElementById('send-btn');
    if (sendBtn) {
        sendBtn.disabled = true;
        sendBtn.textContent = '发送中...';
    }

    // 验证 sessionId 存在
    if (!sessionId) {
        showError('会话未初始化，正在重新创建...');
        // 尝试重新初始化
        if (typeof MODULE !== 'undefined') {
            await initChat(MODULE);
        }
        if (sendBtn) {
            sendBtn.disabled = false;
            sendBtn.textContent = '发送';
        }
        return;
    }

    const input = document.getElementById('message-input');
    const message = input.value.trim();

    if (!message) {
        if (sendBtn) {
            sendBtn.disabled = false;
            sendBtn.textContent = '发送';
        }
        return;
    }

    // 先保存用户输入，发送成功后再清空（防止发送失败丢失内容）
    const savedMessage = message;

    // 显示用户消息
    addMessage('user', message);

    // 显示加载状态
    setLoading(true);

    // 创建 AI 消息占位符
    const aiMessageDiv = createStreamingMessage();

    try {
        const model = document.getElementById('model-select').value;

        // 使用流式 API
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                message: message,
                model: model
            })
        });

        if (!response.ok) {
            // 非流式错误响应
            const errorData = await response.json();

            // 会话不存在，自动重建
            if (response.status === 404) {
                showToast('会话已过期，正在重建...', 'info');
                clearLocalSession();
                await initChat(MODULE);
                // 恢复用户输入
                input.value = savedMessage;
                aiMessageDiv.remove();
                setLoading(false);
                return;
            }

            if (errorData.need_login) {
                showLoginRequired();
                // 恢复用户输入
                input.value = savedMessage;
                aiMessageDiv.remove();
                return;
            }
            throw new Error(errorData.error || '请求失败');
        }

        // 发送成功，清空输入框
        input.value = '';
        autoResizeTextarea(input);

        // 读取 SSE 流
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullContent = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const text = decoder.decode(value);
            const lines = text.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));

                        if (data.error) {
                            showError('AI回复失败: ' + data.error);
                            aiMessageDiv.remove();
                            return;
                        }

                        if (data.content) {
                            fullContent += data.content;
                            updateStreamingMessage(aiMessageDiv, fullContent);
                        }

                        if (data.done) {
                            // 流结束，更新积分
                            if (data.remaining_credits !== undefined) {
                                updateCreditsDisplay(data.remaining_credits);
                            }
                            // 刷新历史
                            if (typeof loadHistory === 'function') {
                                loadHistory();
                            }
                        }
                    } catch (e) {
                        // 忽略解析错误
                    }
                }
            }
        }

        // 最终渲染 Markdown
        finalizeStreamingMessage(aiMessageDiv, fullContent);

    } catch (error) {
        if (aiMessageDiv) aiMessageDiv.remove();

        // 恢复用户输入（让用户可以重试）
        const input = document.getElementById('message-input');
        if (input && savedMessage) {
            input.value = savedMessage;
        }

        // 移除显示的用户消息（因为实际没发送成功）
        const messages = document.getElementById('messages');
        const lastUserMsg = messages.querySelector('.message-user:last-of-type');
        if (lastUserMsg) {
            lastUserMsg.remove();
        }

        if (error.name === 'AbortError') {
            showToast('请求超时，请检查网络后重试', 'error');
        } else {
            showToast('发送失败: ' + error.message + '，请重试', 'error');
        }
    } finally {
        setLoading(false);
    }
}

/**
 * 创建流式消息占位符
 */
function createStreamingMessage() {
    const container = document.getElementById('messages');

    const messageDiv = document.createElement('div');
    messageDiv.className = 'message message-assistant';

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    const avatarImg = document.createElement('img');
    avatarImg.src = '/static/images/jianghui.jpg';
    avatarImg.alt = 'AI助手';
    avatarImg.onerror = function() {
        this.style.display = 'none';
        this.parentElement.innerHTML = '<span style="font-size:20px;">🤖</span>';
    };
    avatarDiv.appendChild(avatarImg);

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content streaming';
    contentDiv.innerHTML = '<span class="cursor">▋</span>';

    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentDiv);
    container.appendChild(messageDiv);

    container.scrollTop = container.scrollHeight;

    return messageDiv;
}

/**
 * 更新流式消息内容
 */
function updateStreamingMessage(messageDiv, content) {
    const contentDiv = messageDiv.querySelector('.message-content');
    // 简单文本显示 + 光标
    contentDiv.innerHTML = content.replace(/\n/g, '<br>') + '<span class="cursor">▋</span>';

    // 滚动到底部
    const container = document.getElementById('messages');
    container.scrollTop = container.scrollHeight;
}

/**
 * 完成流式消息（渲染 Markdown）
 */
function finalizeStreamingMessage(messageDiv, content) {
    const contentDiv = messageDiv.querySelector('.message-content');
    contentDiv.classList.remove('streaming');

    // 使用 marked 渲染 Markdown
    if (typeof marked !== 'undefined') {
        contentDiv.innerHTML = marked.parse(content);
    } else {
        contentDiv.innerHTML = content.replace(/\n/g, '<br>');
    }

    // 为表格添加复制按钮
    addTableCopyButtons(contentDiv);

    // 添加快捷回复按钮
    createQuickReplyButtons(messageDiv);
}

/**
 * 添加消息到对话区域（非流式）
 */
function addMessage(role, content, showQuickReplies = false) {
    const container = document.getElementById('messages');

    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${role}`;

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';

    const avatarImg = document.createElement('img');
    if (role === 'assistant') {
        avatarImg.src = '/static/images/jianghui.jpg';
        avatarImg.alt = 'AI助手';
        avatarImg.onerror = function() {
            this.style.display = 'none';
            this.parentElement.innerHTML = '<span style="font-size:20px;">🤖</span>';
        };
    } else {
        avatarImg.src = '/static/images/user-avatar.png';
        avatarImg.alt = '用户';
        avatarImg.onerror = function() {
            this.style.display = 'none';
            this.parentElement.innerHTML = '<span style="font-size:20px;">👤</span>';
        };
    }
    avatarDiv.appendChild(avatarImg);

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    if (typeof marked !== 'undefined') {
        contentDiv.innerHTML = marked.parse(content);
    } else {
        contentDiv.innerHTML = content.replace(/\n/g, '<br>');
    }

    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentDiv);

    // 如果是 AI 消息，添加 Gemini 风格的操作按钮
    if (role === 'assistant') {
        const actionsDiv = createMessageActions(content, messageDiv);
        messageDiv.appendChild(actionsDiv);
    }

    container.appendChild(messageDiv);

    // 如果是 AI 消息，为表格添加复制按钮
    if (role === 'assistant') {
        addTableCopyButtons(contentDiv);
    }

    container.scrollTop = container.scrollHeight;

    // 如果是 AI 消息且需要显示快捷回复，添加按钮
    if (role === 'assistant' && showQuickReplies) {
        createQuickReplyButtons(messageDiv);
    }
}

/**
 * 创建 Gemini 风格的消息操作按钮
 */
function createMessageActions(content, messageDiv) {
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'message-actions';

    // 点赞按钮
    const likeBtn = document.createElement('button');
    likeBtn.className = 'action-icon-btn';
    likeBtn.title = '有帮助';
    likeBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
    </svg>`;
    likeBtn.onclick = () => {
        likeBtn.classList.toggle('active');
        showToast('感谢反馈！', 'success');
    };

    // 踩按钮
    const dislikeBtn = document.createElement('button');
    dislikeBtn.className = 'action-icon-btn';
    dislikeBtn.title = '没帮助';
    dislikeBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/>
    </svg>`;
    dislikeBtn.onclick = () => {
        dislikeBtn.classList.toggle('active');
        showToast('感谢反馈，我们会改进', 'info');
    };

    // 复制按钮
    const copyBtn = document.createElement('button');
    copyBtn.className = 'action-icon-btn';
    copyBtn.title = '复制';
    copyBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </svg>`;
    copyBtn.onclick = () => {
        copyToClipboard(content);
        copyBtn.classList.add('active');
        showToast('已复制到剪贴板', 'success');
        setTimeout(() => copyBtn.classList.remove('active'), 2000);
    };

    // 重新生成按钮
    const regenBtn = document.createElement('button');
    regenBtn.className = 'action-icon-btn';
    regenBtn.title = '重新生成';
    regenBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M23 4v6h-6M1 20v-6h6"/>
        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
    </svg>`;
    regenBtn.onclick = () => {
        showToast('重新生成功能开发中', 'info');
    };

    // 更多操作按钮
    const moreBtn = document.createElement('button');
    moreBtn.className = 'action-icon-btn';
    moreBtn.title = '更多';
    moreBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>
    </svg>`;
    moreBtn.onclick = (e) => {
        e.stopPropagation();
        showMoreActionsMenu(e, content, messageDiv);
    };

    actionsDiv.appendChild(likeBtn);
    actionsDiv.appendChild(dislikeBtn);
    actionsDiv.appendChild(copyBtn);
    actionsDiv.appendChild(regenBtn);
    actionsDiv.appendChild(moreBtn);

    return actionsDiv;
}

/**
 * 显示更多操作菜单
 */
function showMoreActionsMenu(event, content, messageDiv) {
    // 移除已有菜单
    const existingMenu = document.querySelector('.action-menu.show');
    if (existingMenu) existingMenu.remove();

    const menu = document.createElement('div');
    menu.className = 'action-menu show';
    menu.innerHTML = `
        <div class="action-menu-item" onclick="exportThisResponse()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
            </svg>
            导出此回答
        </div>
        <div class="action-menu-item" onclick="generateInfographic()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 3v18h18M9 17V9M15 17V5"/>
            </svg>
            生成信息图
        </div>
        <div class="action-menu-item" onclick="newSession()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 5v14M5 12h14"/>
            </svg>
            开始新对话
        </div>
    `;

    // 定位菜单
    const rect = event.target.getBoundingClientRect();
    menu.style.position = 'fixed';
    menu.style.bottom = (window.innerHeight - rect.top + 8) + 'px';
    menu.style.left = rect.left + 'px';

    document.body.appendChild(menu);

    // 点击外部关闭
    setTimeout(() => {
        document.addEventListener('click', function closeMenu(e) {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        });
    }, 100);
}

/**
 * 导出单条回答
 */
function exportThisResponse() {
    showToast('导出功能开发中', 'info');
}

/**
 * 复制文本到剪贴板
 */
function copyToClipboard(text) {
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text);
    } else {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
    }
}

/**
 * 设置加载状态
 */
function setLoading(loading) {
    isLoading = loading;
    const loadingEl = document.getElementById('loading');
    const sendBtn = document.getElementById('send-btn');

    if (loadingEl) loadingEl.style.display = loading ? 'flex' : 'none';
    if (sendBtn) {
        sendBtn.disabled = loading;
        sendBtn.textContent = loading ? '发送中...' : '发送';
    }

    if (loading) {
        document.getElementById('messages').scrollTop =
            document.getElementById('messages').scrollHeight;
    }
}

/**
 * 显示错误信息
 */
function showError(message) {
    const container = document.getElementById('messages');

    const errorDiv = document.createElement('div');
    errorDiv.className = 'message message-error';
    // 使用 escapeHtml 防止 XSS
    errorDiv.innerHTML = `<div class="message-content error-content">⚠️ ${escapeHtml(message)}</div>`;

    container.appendChild(errorDiv);
    container.scrollTop = container.scrollHeight;
}

/**
 * 导出文档
 */
async function exportDocument() {
    // 检查登录状态
    if (typeof isLoggedIn !== 'undefined' && !isLoggedIn) {
        alert('请先登录后再导出文档');
        return;
    }

    if (!sessionId) {
        alert('请先开始对话');
        return;
    }

    // 检查是否有对话内容
    const messagesDiv = document.getElementById('messages');
    const userMessages = messagesDiv.querySelectorAll('.message-user');
    if (userMessages.length === 0) {
        alert('对话内容为空，请先进行对话后再导出');
        return;
    }

    try {
        const response = await fetch(`/api/export/${sessionId}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            if (!data.document || data.document.trim().length < 50) {
                alert('对话内容太少，请进行更多对话后再导出');
                return;
            }
            const blob = new Blob([data.document], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${MODULE_INFO.name}_分析报告.md`;
            a.click();
            URL.revokeObjectURL(url);
        } else {
            alert('导出失败: ' + data.error);
        }
    } catch (error) {
        alert('导出错误: ' + error.message);
    }
}

/**
 * 新建对话
 */
function newSession() {
    // 如果正在加载，提示用户等待
    if (isLoading) {
        showToast('请等待 AI 回复完成后再开始新对话', 'info');
        return;
    }

    // 检查是否有用户发送的消息，没有则不需要确认
    const messagesDiv = document.getElementById('messages');
    const userMessages = messagesDiv ? messagesDiv.querySelectorAll('.message-user') : [];

    if (userMessages.length > 0) {
        if (!confirm('确定要开始新的对话吗？当前对话将被清除。')) {
            return;
        }
    }

    // 移除快捷回复按钮
    const quickReplies = document.querySelector('.quick-replies');
    if (quickReplies) quickReplies.remove();

    document.getElementById('messages').innerHTML = '';
    initChat(MODULE);
}

/**
 * 处理键盘事件
 */
function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

/**
 * 自动调整textarea高度
 */
function autoResizeTextarea(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
}

/**
 * 更新字符计数显示
 */
function updateCharCount() {
    const input = document.getElementById('message-input');
    const charCount = document.getElementById('charCount');
    if (input && charCount) {
        const len = input.value.length;
        charCount.textContent = `${len}/5000`;
        // 超过 4000 字符时显示警告色
        if (len > 4000) {
            charCount.style.color = '#ef4444';
            charCount.style.display = 'block';
        } else if (len > 0) {
            charCount.style.color = '#9ca3af';
            charCount.style.display = 'block';
        } else {
            charCount.style.display = 'none';
        }
    }
}

// 监听输入框变化
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('message-input');
    if (input) {
        input.addEventListener('input', () => {
            autoResizeTextarea(input);
            updateCharCount();
        });
        // 初始化时也更新一次字符计数（处理页面刷新后输入框有内容的情况）
        updateCharCount();
    }
});

/**
 * 显示登录提示
 */
function showLoginRequired() {
    // 保存当前输入到 localStorage，登录后可恢复
    const input = document.getElementById('message-input');
    if (input && input.value.trim()) {
        localStorage.setItem('pending_message', input.value);
        localStorage.setItem('pending_message_module', typeof MODULE !== 'undefined' ? MODULE : '');
    }

    const container = document.getElementById('messages');

    const msgDiv = document.createElement('div');
    msgDiv.className = 'message message-system';
    msgDiv.innerHTML = `
        <div class="message-content system-notice">
            <div class="notice-icon">🔐</div>
            <div class="notice-text">
                <h4>登录已过期</h4>
                <p>请重新登录后继续对话，您的输入内容已保存</p>
                <a href="/?redirect=${encodeURIComponent(window.location.pathname)}" class="notice-btn">重新登录</a>
            </div>
        </div>
    `;

    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
}

/**
 * 显示积分不足提示
 */
function showCreditsExhausted(adminWechat) {
    const container = document.getElementById('messages');

    const msgDiv = document.createElement('div');
    msgDiv.className = 'message message-system';
    msgDiv.innerHTML = `
        <div class="message-content credits-notice">
            <div class="notice-icon">💎</div>
            <div class="notice-text">
                <h4>积分已用完</h4>
                <p>您的免费提问次数已用完</p>
                <p>如需继续使用，请添加管理员微信充值：</p>
                <div class="wechat-id">
                    <span class="wechat-icon">💬</span>
                    <strong>${adminWechat}</strong>
                </div>
            </div>
        </div>
    `;

    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
}

/**
 * 更新积分显示
 */
function updateCreditsDisplay(credits) {
    const creditsEl = document.getElementById('credits-display');
    if (creditsEl) {
        creditsEl.textContent = credits;
    }
}

/**
 * 快捷回复按钮配置
 */
const QUICK_REPLIES = [
    { text: '继续', icon: '▶️' },
    { text: '详细解释', icon: '📝' },
    { text: '举例说明', icon: '💡' },
    { text: '帮我总结', icon: '📋' }
];

/**
 * 创建快捷回复按钮
 */
function createQuickReplyButtons(messageDiv) {
    // 移除之前的快捷按钮（如果有）
    const existingBtns = document.querySelector('.quick-replies');
    if (existingBtns) {
        existingBtns.remove();
    }

    const quickRepliesDiv = document.createElement('div');
    quickRepliesDiv.className = 'quick-replies';

    QUICK_REPLIES.forEach(reply => {
        const btn = document.createElement('button');
        btn.className = 'quick-reply-btn';
        btn.innerHTML = `<span class="quick-reply-icon">${reply.icon}</span>${reply.text}`;
        btn.onclick = () => sendQuickReply(reply.text);
        quickRepliesDiv.appendChild(btn);
    });

    // 添加到消息容器底部
    const container = document.getElementById('messages');
    container.appendChild(quickRepliesDiv);
    container.scrollTop = container.scrollHeight;
}

/**
 * 发送快捷回复
 */
function sendQuickReply(text) {
    // 立即移除快捷按钮（防止重复点击）
    const quickReplies = document.querySelector('.quick-replies');
    if (quickReplies) {
        quickReplies.remove();
    }

    const input = document.getElementById('message-input');
    input.value = text;
    sendMessage();
}

/**
 * 为消息内容中的表格添加复制按钮
 */
function addTableCopyButtons(contentDiv) {
    const tables = contentDiv.querySelectorAll('table');
    tables.forEach((table, index) => {
        // 检查是否已经包装过
        if (table.parentElement.classList.contains('table-wrapper')) {
            return;
        }

        // 创建包装容器
        const wrapper = document.createElement('div');
        wrapper.className = 'table-wrapper';

        // 创建复制按钮
        const copyBtn = document.createElement('button');
        copyBtn.className = 'table-copy-btn';
        copyBtn.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            复制表格
        `;
        copyBtn.onclick = () => copyTableToClipboard(table, copyBtn);

        // 包装表格
        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(copyBtn);
        wrapper.appendChild(table);
    });
}

/**
 * 复制表格内容到剪贴板
 */
async function copyTableToClipboard(table, btn) {
    try {
        // 获取表格数据
        const rows = table.querySelectorAll('tr');
        const data = [];

        rows.forEach(row => {
            const cells = row.querySelectorAll('th, td');
            const rowData = [];
            cells.forEach(cell => {
                rowData.push(cell.textContent.trim());
            });
            data.push(rowData.join('\t'));
        });

        const text = data.join('\n');

        // 复制到剪贴板
        await navigator.clipboard.writeText(text);

        // 显示成功状态
        btn.classList.add('copied');
        btn.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            已复制
        `;

        // 2秒后恢复
        setTimeout(() => {
            btn.classList.remove('copied');
            btn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                </svg>
                复制表格
            `;
        }, 2000);
    } catch (e) {
        console.error('复制失败:', e);
        alert('复制失败，请手动选择复制');
    }
}
