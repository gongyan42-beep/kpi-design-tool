"""
猫课电商管理落地班核心工具 - Flask主应用
"""
import os
import json
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, jsonify, send_file, session, Response
from config import Config
from database import db
from modules.ai_service import ai_service
from modules.prompts import get_system_prompt, get_welcome_message
from modules.auth_service import auth_service
from modules.memory_service import memory_service
from modules.prompt_service import prompt_service
from modules.infographic_service import infographic_service
from modules.redeem_service import redeem_service


# ========================================
# 日志配置
# ========================================
def setup_logging():
    """配置日志系统"""
    # 确保日志目录存在
    os.makedirs('logs', exist_ok=True)

    # 配置根日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            RotatingFileHandler(
                'logs/app.log',
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            ),
            logging.StreamHandler()
        ]
    )

    # 减少第三方库日志
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

setup_logging()
logger = logging.getLogger(__name__)


app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
# 限制文件上传大小为 50MB，防止内存耗尽攻击
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024


# ========================================
# 页面路由
# ========================================

@app.route('/')
def index():
    """首页 - 动态加载模块卡片导航"""
    # 优先从 Supabase 获取模块，失败则用本地配置
    modules_list = prompt_service.get_all_modules()

    # 转换为字典格式供模板使用
    modules = {}
    for m in modules_list:
        modules[m['id']] = {
            'name': m.get('name', ''),
            'icon': m.get('icon', '📋'),
            'color': m.get('color', '#6b7280'),
            'description': m.get('description', ''),
            'subtitle': m.get('subtitle', '')
        }

    # 如果没有获取到模块，使用本地配置
    if not modules:
        modules = Config.MODULES

    return render_template('index.html', modules=modules)


@app.route('/chat/<module>')
def chat(module):
    """对话页面"""
    # 优先从 Supabase 获取模块信息
    module_info = prompt_service.get_module(module)

    if not module_info:
        # 回退到本地配置
        if module not in Config.MODULES:
            return "模块不存在", 404
        module_info = Config.MODULES[module]
    else:
        # 转换格式
        module_info = {
            'name': module_info.get('name', ''),
            'icon': module_info.get('icon', '📋'),
            'color': module_info.get('color', '#6b7280'),
            'description': module_info.get('description', ''),
            'subtitle': module_info.get('subtitle', '')
        }

    models = ai_service.get_available_models()

    # 动态获取所有模块名称映射（用于历史侧边栏显示）
    modules_list = prompt_service.get_all_modules()
    if modules_list:
        module_names = {m['id']: m['name'] for m in modules_list}
    else:
        module_names = {k: v['name'] for k, v in Config.MODULES.items()}

    # 获取所有模块（用于侧边栏智能体显示）
    all_modules = modules_list if modules_list else [
        {'id': k, **v} for k, v in Config.MODULES.items()
    ]

    return render_template(
        'chat.html',
        module=module,
        module_info=module_info,
        models=models,
        module_names=module_names,
        all_modules=all_modules
    )


# ========================================
# API路由
# ========================================

@app.route('/api/modules', methods=['GET'])
def get_modules():
    """获取所有可用模块（公开接口）"""
    modules_list = prompt_service.get_all_modules()
    if modules_list:
        # 只返回必要的字段
        modules = [
            {
                'id': m.get('id'),
                'name': m.get('name'),
                'icon': m.get('icon', '📊'),
                'color': m.get('color', '#6b7280'),
                'description': m.get('description', '')
            }
            for m in modules_list
        ]
    else:
        # 回退到本地配置
        modules = [
            {'id': k, **{key: v.get(key) for key in ['name', 'icon', 'color', 'description']}}
            for k, v in Config.MODULES.items()
        ]
    return jsonify({'success': True, 'modules': modules})


@app.route('/api/session/new', methods=['POST'])
def create_session():
    """创建新会话"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '无效的请求数据'}), 400

    module = data.get('module')

    # 验证模块是否有效（本地或动态模块）
    module_info = prompt_service.get_module(module)
    if not module_info and module not in Config.MODULES:
        return jsonify({'success': False, 'error': '无效的模块'}), 400

    # 获取当前登录用户信息
    user_id = session.get('user_id')
    user_email = session.get('email')

    # 创建会话（关联用户）
    session_id = db.create_session(module, user_id, user_email)

    # 获取欢迎语
    welcome_message = get_welcome_message(module)

    # 保存AI的欢迎消息
    db.add_message(session_id, 'assistant', welcome_message)

    return jsonify({
        'success': True,
        'session_id': session_id,
        'welcome_message': welcome_message
    })


@app.route('/api/session/<session_id>', methods=['GET'])
def get_session(session_id):
    """获取会话详情"""
    session = db.get_session(session_id)

    if not session:
        return jsonify({'success': False, 'error': '会话不存在'}), 404

    return jsonify({
        'success': True,
        'session': session
    })


@app.route('/api/chat', methods=['POST'])
def chat_api():
    """发送消息并获取AI回复"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '无效的请求数据'}), 400

    session_id = data.get('session_id')
    message = data.get('message', '').strip()
    model = data.get('model', 'flash')

    if not session_id or not message:
        return jsonify({'success': False, 'error': '缺少必要参数'}), 400

    chat_session = db.get_session(session_id)
    if not chat_session:
        return jsonify({'success': False, 'error': '会话不存在'}), 404

    # 检查用户登录和积分
    user_id = session.get('user_id')
    credits_cost = auth_service.CREDITS_PER_CHAT  # 每次对话消耗积分（配置值）

    # 必须登录才能使用
    if not user_id:
        return jsonify({
            'success': False,
            'error': '请先登录后再使用',
            'need_login': True
        }), 401

    # 验证会话所有权（会话必须属于当前用户）
    if chat_session.get('user_id') and chat_session.get('user_id') != user_id:
        return jsonify({'success': False, 'error': '无权访问此会话'}), 403

    # 获取当前积分
    current_credits = auth_service.get_credits(user_id)
    # 检查积分是否足够
    if current_credits < credits_cost:
        return jsonify({
            'success': False,
            'error': f'积分不足！当前积分: {current_credits}，需要: {credits_cost}。请联系微信 huohuo1616 进行充值。',
            'credits_exhausted': True,
            'admin_wechat': 'huohuo1616'
        }), 402

    # 保存用户消息
    db.add_message(session_id, 'user', message)

    # 获取对话历史
    messages = db.get_messages_for_api(session_id)

    # 获取用户记忆上下文（跨模块）
    user_memory_context = None
    if user_id:
        user_memory_context = memory_service.get_memory_context(user_id)

    # 获取知识库上下文
    knowledge_context = prompt_service.get_knowledge_context(chat_session['module'])

    # 合并记忆和知识库上下文
    combined_context = ""
    if user_memory_context:
        combined_context += user_memory_context
    if knowledge_context:
        combined_context += knowledge_context

    # 获取系统提示词（注入记忆和知识库）
    system_prompt = get_system_prompt(
        chat_session['module'],
        chat_session['collected_data'],
        combined_context if combined_context else None
    )

    try:
        # 调用AI
        response = ai_service.chat(
            messages=messages,
            system_prompt=system_prompt,
            model=model
        )

        # 保存AI回复
        db.add_message(session_id, 'assistant', response)

        # 扣除积分（AI调用成功后）
        success, msg, remaining_credits = auth_service.use_credits(
            user_id, credits_cost, f"AI对话 - {chat_session['module']}"
        )

        return jsonify({
            'success': True,
            'response': response,
            'model': model,
            'credits_used': credits_cost,
            'remaining_credits': remaining_credits
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/chat/stream', methods=['POST'])
def chat_stream_api():
    """流式对话 - 逐字返回（打字机效果）- 支持图片"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '无效的请求数据'}), 400

    session_id = data.get('session_id')
    message = data.get('message', '').strip()
    model = data.get('model', 'flash')
    images = data.get('images', [])  # 图片列表（Base64 格式）

    # 必须有文字或图片
    if not session_id or (not message and not images):
        return jsonify({'success': False, 'error': '缺少必要参数'}), 400

    chat_session = db.get_session(session_id)
    if not chat_session:
        return jsonify({'success': False, 'error': '会话不存在'}), 404

    # 检查用户登录
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({
            'success': False,
            'error': '请先登录后再使用',
            'need_login': True
        }), 401

    # 验证会话所有权（会话必须属于当前用户）
    if chat_session.get('user_id') and chat_session.get('user_id') != user_id:
        return jsonify({'success': False, 'error': '无权访问此会话'}), 403

    # 检查积分是否足够
    credits_cost = auth_service.CREDITS_PER_CHAT
    current_credits = auth_service.get_credits(user_id)
    if current_credits < credits_cost:
        return jsonify({
            'success': False,
            'error': f'积分不足！当前积分: {current_credits}，需要: {credits_cost}。请联系微信 huohuo1616 进行充值。',
            'credits_exhausted': True,
            'admin_wechat': 'huohuo1616'
        }), 402

    # 保存用户消息（如果有图片，附带标记）
    display_message = message if message else '[图片]'
    if message and images:
        display_message = f"{message} [附图{len(images)}张]"
    db.add_message(session_id, 'user', display_message)

    # 获取对话历史
    messages = db.get_messages_for_api(session_id)

    # 获取用户记忆上下文
    user_memory_context = memory_service.get_memory_context(user_id) if user_id else None

    # 获取知识库上下文
    knowledge_context = prompt_service.get_knowledge_context(chat_session['module'])

    # 合并上下文
    combined_context = ""
    if user_memory_context:
        combined_context += user_memory_context
    if knowledge_context:
        combined_context += knowledge_context

    # 获取系统提示词
    system_prompt = get_system_prompt(
        chat_session['module'],
        chat_session['collected_data'],
        combined_context if combined_context else None
    )

    def generate():
        """生成器：流式返回 AI 响应"""
        full_response = []

        try:
            for chunk in ai_service.chat_stream(
                messages=messages,
                system_prompt=system_prompt,
                model=model,
                images=images  # 传递图片
            ):
                if chunk.startswith('[ERROR]'):
                    # 发送错误
                    yield f"data: {json.dumps({'error': chunk[7:]})}\n\n"
                    return
                else:
                    full_response.append(chunk)
                    yield f"data: {json.dumps({'content': chunk})}\n\n"

            # 流结束，保存完整响应
            complete_response = ''.join(full_response)
            db.add_message(session_id, 'assistant', complete_response)

            # 扣除积分
            credits_cost = auth_service.CREDITS_PER_CHAT
            success, msg, remaining_credits = auth_service.use_credits(
                user_id, credits_cost, f"AI对话 - {chat_session['module']}"
            )

            # 发送完成信号
            yield f"data: {json.dumps({'done': True, 'credits_used': credits_cost, 'remaining_credits': remaining_credits})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'  # 禁用 Nginx 缓冲
        }
    )


@app.route('/api/export/<session_id>', methods=['POST'])
def export_document(session_id):
    """导出文档"""
    # 验证用户登录
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': '请先登录'}), 401

    chat_session = db.get_session(session_id)

    if not chat_session:
        return jsonify({'success': False, 'error': '会话不存在'}), 404

    # 验证会话所有权
    if chat_session.get('user_id') and chat_session.get('user_id') != user_id:
        return jsonify({'success': False, 'error': '无权访问此会话'}), 403

    # 生成文档内容
    module_info = Config.MODULES.get(chat_session['module'], {})
    document = f"# {module_info.get('name', '未知模块')}分析报告\n\n"
    document += f"生成时间: {chat_session['updated_at']}\n\n"
    document += "---\n\n"

    # 添加对话历史
    document += "## 对话记录\n\n"
    for msg in chat_session['messages']:
        role = "**AI**" if msg['role'] == 'assistant' else "**用户**"
        document += f"{role}: {msg['content']}\n\n"

    # 保存文档
    db.save_output_document(session_id, document)

    return jsonify({
        'success': True,
        'document': document
    })


@app.route('/api/infographic/<session_id>', methods=['POST'])
def generate_infographic(session_id):
    """生成信息图"""
    # 验证用户登录
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': '请先登录'}), 401

    chat_session = db.get_session(session_id)

    if not chat_session:
        return jsonify({'success': False, 'error': '会话不存在'}), 404

    # 验证会话所有权
    if chat_session.get('user_id') and chat_session.get('user_id') != user_id:
        return jsonify({'success': False, 'error': '无权访问此会话'}), 403

    # 获取模块信息
    module = chat_session['module']

    # 优先从 Supabase 获取模块信息
    module_info = prompt_service.get_module(module)
    if not module_info:
        module_info = Config.MODULES.get(module, {
            'name': module,
            'icon': '📊',
            'color': '#1a56db'
        })

    # 获取聊天记录
    messages = chat_session.get('messages', [])

    if not messages:
        return jsonify({'success': False, 'error': '没有聊天记录'}), 400

    # 生成信息图
    result = infographic_service.generate_infographic(
        messages=messages,
        module_name=module,
        module_info=module_info
    )

    if result['success']:
        return jsonify({
            'success': True,
            'html': result['html'],
            'title': result['title'],
            'summary': result['summary']
        })
    else:
        return jsonify({
            'success': False,
            'error': result.get('error', '生成失败')
        }), 500


@app.route('/api/models', methods=['GET'])
def get_models():
    """获取可用模型列表"""
    return jsonify({
        'success': True,
        'models': ai_service.get_available_models()
    })


# ========================================
# 用户对话历史 API
# ========================================

@app.route('/api/sessions', methods=['GET'])
def get_user_sessions():
    """获取当前用户的对话历史"""
    user_id = session.get('user_id')

    if not user_id:
        return jsonify({'success': False, 'error': '未登录'}), 401

    sessions = db.get_user_sessions(user_id, limit=20)

    return jsonify({
        'success': True,
        'sessions': sessions
    })


@app.route('/api/session/<session_id>/resume', methods=['POST'])
def resume_session(session_id):
    """恢复已有对话"""
    user_id = session.get('user_id')

    if not user_id:
        return jsonify({'success': False, 'error': '未登录'}), 401

    chat_session = db.get_session(session_id)

    if not chat_session:
        return jsonify({'success': False, 'error': '会话不存在'}), 404

    # 验证会话属于当前用户
    if chat_session.get('user_id') != user_id:
        return jsonify({'success': False, 'error': '无权访问此会话'}), 403

    return jsonify({
        'success': True,
        'session_id': session_id,
        'module': chat_session['module'],
        'messages': chat_session['messages'],
        'collected_data': chat_session.get('collected_data', {})
    })


# ========================================
# 用户认证 API
# ========================================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    company = data.get('company', '').strip()
    position = data.get('position', '').strip()
    user_type = data.get('user_type', 'normal')  # 'business_school' 或 'normal'
    cat_coins = data.get('cat_coins', 0)  # 猫币数量

    if not username or not password:
        return jsonify({'success': False, 'error': '请填写姓名和密码'}), 400

    if len(password) < 6:
        return jsonify({'success': False, 'error': '密码至少6位'}), 400

    # 验证用户类型
    if user_type not in ['business_school', 'normal']:
        user_type = 'normal'

    # 普通用户如果没有猫币，仍可注册但只得到默认积分
    if user_type == 'normal' and cat_coins:
        try:
            cat_coins = int(cat_coins)
            if cat_coins < 0:
                cat_coins = 0
        except (ValueError, TypeError):
            cat_coins = 0

    success, message, user_data = auth_service.register(
        username, password, company, position,
        user_type=user_type,
        cat_coins=cat_coins if user_type == 'normal' else 0
    )

    if success:
        return jsonify({'success': True, 'message': message, 'data': user_data})
    else:
        return jsonify({'success': False, 'error': message}), 400


@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'success': False, 'error': '请填写姓名和密码'}), 400

    success, message, user_data = auth_service.login(username, password)

    if success:
        # 保存到 session
        session['user_id'] = user_data['user_id']
        session['username'] = user_data['username']
        session['email'] = user_data.get('email')  # 保留兼容
        session['access_token'] = user_data.get('access_token')

        return jsonify({
            'success': True,
            'message': message,
            'data': {
                'user_id': user_data['user_id'],
                'username': user_data['username'],
                'email': user_data.get('email'),
                'profile': user_data.get('profile')
            }
        })
    else:
        return jsonify({'success': False, 'error': message}), 401


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """用户登出"""
    auth_service.logout()
    session.clear()
    return jsonify({'success': True, 'message': '已登出'})


@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    """获取当前登录用户"""
    user_id = session.get('user_id')

    if not user_id:
        return jsonify({'success': False, 'error': '未登录'}), 401

    profile = auth_service.get_profile(user_id)

    return jsonify({
        'success': True,
        'data': {
            'user_id': user_id,
            'username': session.get('username') or (profile.get('nickname') if profile else None),
            'email': session.get('email'),
            'profile': profile
        }
    })


# ========================================
# 积分系统 API
# ========================================

@app.route('/api/credits', methods=['GET'])
def get_credits():
    """获取积分余额"""
    user_id = session.get('user_id')

    if not user_id:
        return jsonify({'success': False, 'error': '未登录'}), 401

    credits = auth_service.get_credits(user_id)

    return jsonify({
        'success': True,
        'credits': credits
    })


@app.route('/api/credits/logs', methods=['GET'])
def get_credit_logs():
    """获取积分变动记录"""
    user_id = session.get('user_id')

    if not user_id:
        return jsonify({'success': False, 'error': '未登录'}), 401

    logs = auth_service.get_credit_logs(user_id)

    return jsonify({
        'success': True,
        'logs': logs
    })


# ========================================
# 兑换码 API
# ========================================

@app.route('/api/redeem', methods=['POST'])
def redeem_code():
    """用户兑换积分码"""
    user_id = session.get('user_id')

    if not user_id:
        return jsonify({'success': False, 'error': '请先登录后再兑换'}), 401

    data = request.get_json()
    code = data.get('code', '').strip()

    if not code:
        return jsonify({'success': False, 'error': '请输入兑换码'}), 400

    success, message, credits = redeem_service.redeem_code(code, user_id)

    if success:
        # 获取最新积分
        new_balance = auth_service.get_credits(user_id)
        return jsonify({
            'success': True,
            'message': message,
            'credits_added': credits,
            'new_balance': new_balance
        })
    else:
        return jsonify({'success': False, 'error': message}), 400


# ========================================
# 管理后台
# ========================================

@app.route('/admin')
def admin_page():
    """管理后台页面"""
    return render_template('admin.html')


@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    """管理员登录"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '无效的请求数据'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')

    # 从环境变量读取管理员账号（格式：user1:pass1,user2:pass2）
    admin_users_str = os.getenv('ADMIN_USERS', '')
    admin_users = {}
    for pair in admin_users_str.split(','):
        if ':' in pair:
            u, p = pair.split(':', 1)
            admin_users[u.strip()] = p.strip()

    if username in admin_users and admin_users[username] == password:
        session['is_admin'] = True
        session['admin_username'] = username
        return jsonify({'success': True, 'message': '登录成功'})
    else:
        return jsonify({'success': False, 'error': '用户名或密码错误'}), 401


@app.route('/api/admin/sessions', methods=['GET'])
def admin_get_sessions():
    """获取所有用户会话（包含用户详细信息）"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    try:
        sessions_data = db.get_all_sessions_for_admin(limit=100)
        logger.info(f"获取到 {len(sessions_data)} 条会话记录")
    except Exception as e:
        logger.error(f"获取会话失败: {e}")
        return jsonify({'success': False, 'error': f'获取会话失败: {str(e)}'}), 500

    # 获取所有用户信息用于合并（带超时处理）
    profiles_map = {}
    try:
        from modules.supabase_client import get_client
        client = get_client()
        # 尝试获取所有字段（包括可能不存在的 company/position）
        try:
            profiles_response = client.table('profiles').select('id,email,nickname,company,position').execute()
        except Exception:
            # 如果字段不存在，只获取基本字段
            profiles_response = client.table('profiles').select('id,email,nickname').execute()

        # 用 id 和 email 双重映射
        for p in profiles_response.data or []:
            if p.get('email'):
                profiles_map[p['email']] = p
            if p.get('id'):
                profiles_map[p['id']] = p
        logger.info(f"获取到 {len(profiles_response.data or [])} 个用户资料")
    except Exception as e:
        logger.warning(f"获取用户信息失败（不影响会话列表）: {e}")

    # 合并用户信息到会话数据
    for s in sessions_data:
        user_email = s.get('user_email')
        user_id = s.get('user_id')
        profile = profiles_map.get(user_email) or profiles_map.get(user_id) or {}
        s['user_company'] = profile.get('company', '')
        s['user_position'] = profile.get('position', '')
        s['user_nickname'] = profile.get('nickname', '')

    return jsonify({
        'success': True,
        'sessions': sessions_data
    })


@app.route('/api/admin/users', methods=['GET'])
def admin_get_users():
    """获取所有用户（从 Supabase 或本地会话推断）"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    try:
        # 从 Supabase 获取用户列表
        from modules.supabase_client import get_client
        client = get_client()
        response = client.table('profiles').select('*').order('created_at', desc=True).execute()

        users = response.data if response.data else []

        # 如果 Supabase profiles 为空（可能是 RLS 限制），从本地会话推断用户
        if not users:
            # 获取所有会话中的唯一用户
            sessions_data = db.get_all_sessions_for_admin(limit=500)
            user_emails = set()
            user_map = {}

            for s in sessions_data:
                email = s.get('user_email')
                if email and email not in user_map:
                    user_map[email] = {
                        'email': email,
                        'nickname': email.split('@')[0] if '@' in email else email,
                        'company': '',
                        'position': '',
                        'credits': 0,
                        'created_at': s.get('created_at', '')
                    }

            users = list(user_map.values())

        return jsonify({
            'success': True,
            'users': users
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ========================================
# 提示词管理 API
# ========================================

@app.route('/api/admin/modules', methods=['GET'])
def admin_get_modules():
    """获取所有模块配置"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    modules = prompt_service.get_all_modules()
    return jsonify({'success': True, 'modules': modules})


@app.route('/api/admin/modules/<module_id>/prompt', methods=['GET'])
def admin_get_prompt(module_id):
    """获取模块的提示词"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    prompt = prompt_service.get_prompt(module_id)
    return jsonify({'success': True, 'prompt': prompt})


@app.route('/api/admin/modules/<module_id>/prompt', methods=['PUT'])
def admin_save_prompt(module_id):
    """保存模块的提示词"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    data = request.get_json()
    prompt = data.get('prompt', '')

    success = prompt_service.save_prompt(module_id, prompt)

    if success:
        # 记录管理员操作日志
        try:
            from modules.admin_log_service import admin_log_service
            admin_name = session.get('admin_username', 'admin')
            module = prompt_service.get_module(module_id)
            module_name = module.get('name', module_id) if module else module_id
            admin_log_service.log_prompt_update(admin_name, module_name, prompt[:200])
        except Exception as log_err:
            print(f"记录日志失败: {log_err}")
        return jsonify({'success': True, 'message': '保存成功'})
    else:
        return jsonify({'success': False, 'error': '保存失败，请检查 Supabase 配置'}), 500


@app.route('/api/admin/modules', methods=['POST'])
def admin_create_module():
    """创建新模块"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    data = request.get_json()

    required_fields = ['id', 'name']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400

    success = prompt_service.create_module(data)

    if success:
        # 记录管理员操作日志
        try:
            from modules.admin_log_service import admin_log_service
            admin_name = session.get('admin_username', 'admin')
            admin_log_service.log_module_create(admin_name, data.get('id'), data.get('name'))
        except Exception as log_err:
            print(f"记录日志失败: {log_err}")
        return jsonify({'success': True, 'message': '模块创建成功'})
    else:
        return jsonify({'success': False, 'error': '创建失败，请检查 Supabase 配置'}), 500


@app.route('/api/admin/modules/<module_id>', methods=['PUT'])
def admin_update_module(module_id):
    """更新模块配置"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    data = request.get_json()
    success = prompt_service.update_module(module_id, data)

    if success:
        return jsonify({'success': True, 'message': '更新成功'})
    else:
        return jsonify({'success': False, 'error': '更新失败'}), 500


@app.route('/api/admin/modules/<module_id>', methods=['DELETE'])
def admin_delete_module(module_id):
    """删除模块（软删除）"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    # 先获取模块名称用于日志
    module = prompt_service.get_module(module_id)
    module_name = module.get('name', module_id) if module else module_id

    success = prompt_service.delete_module(module_id)

    if success:
        # 记录管理员操作日志
        try:
            from modules.admin_log_service import admin_log_service
            admin_name = session.get('admin_username', 'admin')
            admin_log_service.log_module_delete(admin_name, module_id, module_name)
        except Exception as log_err:
            print(f"记录日志失败: {log_err}")
        return jsonify({'success': True, 'message': '模块已删除'})
    else:
        return jsonify({'success': False, 'error': '删除失败'}), 500


@app.route('/api/admin/modules/<module_id>/knowledge', methods=['GET'])
def admin_get_knowledge(module_id):
    """获取模块的知识库文件"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    files = prompt_service.get_knowledge_files(module_id)
    return jsonify({'success': True, 'files': files})


@app.route('/api/admin/modules/<module_id>/knowledge', methods=['POST'])
def admin_upload_knowledge(module_id):
    """上传知识库文件"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有上传文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '没有选择文件'}), 400

    # 获取文件类型
    filename = file.filename
    file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    if file_ext not in ['txt', 'md', 'pdf', 'docx']:
        return jsonify({'success': False, 'error': '不支持的文件格式，请上传 TXT、MD、PDF 或 DOCX 文件'}), 400

    try:
        # 读取文件内容
        content = ''

        if file_ext in ['txt', 'md']:
            content = file.read().decode('utf-8')
        elif file_ext == 'pdf':
            # 使用 PyPDF2 解析 PDF
            try:
                import PyPDF2
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    content += page.extract_text() + '\n'
            except ImportError:
                return jsonify({'success': False, 'error': '服务器未安装 PDF 解析库'}), 500
        elif file_ext == 'docx':
            # 使用 python-docx 解析 DOCX
            try:
                from docx import Document
                doc = Document(file)
                for para in doc.paragraphs:
                    content += para.text + '\n'
            except ImportError:
                return jsonify({'success': False, 'error': '服务器未安装 DOCX 解析库'}), 500

        # 保存到数据库
        success = prompt_service.add_knowledge_file(module_id, filename, content, file_ext)

        if success:
            return jsonify({'success': True, 'message': '上传成功'})
        else:
            return jsonify({'success': False, 'error': '保存失败'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': f'处理文件失败: {str(e)}'}), 500


@app.route('/api/admin/knowledge/<file_id>', methods=['DELETE'])
def admin_delete_knowledge(file_id):
    """删除知识库文件"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    success = prompt_service.delete_knowledge_file(file_id)

    if success:
        return jsonify({'success': True, 'message': '删除成功'})
    else:
        return jsonify({'success': False, 'error': '删除失败'}), 500


# ========================================
# 兑换码管理 API（管理后台）
# ========================================

@app.route('/api/admin/redeem/codes', methods=['GET'])
def admin_get_redeem_codes():
    """获取所有兑换码"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    codes = redeem_service.get_all_codes()
    return jsonify({'success': True, 'codes': codes})


@app.route('/api/admin/redeem/create', methods=['POST'])
def admin_create_redeem_code():
    """创建兑换码（支持商学院用户和猫币兑换两种模式）"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    data = request.get_json()
    target_name = data.get('target_name', '').strip()
    user_type = data.get('user_type', 'cat_coins')  # 'business_school' 或 'cat_coins'
    cat_coins = data.get('cat_coins', 0)
    credits = data.get('credits', 0)  # 商学院用户直接指定积分
    note = data.get('note', '').strip()

    if not target_name:
        return jsonify({'success': False, 'error': '请输入目标用户姓名'}), 400

    created_by = session.get('admin_username', 'admin')

    if user_type == 'business_school':
        # 商学院用户：直接赠送2000积分
        credits = 2000
        success, message, code_data = redeem_service.create_code_with_credits(
            target_name=target_name,
            credits=credits,
            created_by=created_by,
            note=note or '商学院学员'
        )
    else:
        # 猫币兑换模式
        try:
            cat_coins = int(cat_coins)
        except (ValueError, TypeError):
            cat_coins = 0

        if not cat_coins or cat_coins <= 0:
            return jsonify({'success': False, 'error': '猫币数量必须大于0'}), 400

        success, message, code_data = redeem_service.create_code(
            target_name=target_name,
            cat_coins=cat_coins,
            created_by=created_by,
            note=note
        )

    if success:
        return jsonify({'success': True, 'message': message, 'code': code_data})
    else:
        return jsonify({'success': False, 'error': message}), 400


@app.route('/api/admin/redeem/<code_id>', methods=['DELETE'])
def admin_delete_redeem_code(code_id):
    """删除未使用的兑换码"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    success, message = redeem_service.delete_code(code_id)

    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'error': message}), 400


# ========================================
# 健康检查 & 错误处理
# ========================================

@app.route('/health')
def health_check():
    """健康检查端点"""
    checks = {
        'status': 'healthy',
        'database': 'ok',
        'ai_service': 'ok'
    }

    # 检查数据库
    try:
        db.list_sessions(limit=1)
    except Exception as e:
        checks['database'] = f'error: {str(e)}'
        checks['status'] = 'unhealthy'

    # 检查 AI 配置
    if not Config.CLOSEAI_API_KEY:
        checks['ai_service'] = 'error: API key not configured'
        checks['status'] = 'unhealthy'

    return jsonify(checks)


@app.errorhandler(404)
def not_found_error(error):
    """404 错误处理"""
    logger.warning(f"404 错误: {request.url}")
    return jsonify({'success': False, 'error': '请求的资源不存在'}), 404


@app.errorhandler(500)
def internal_error(error):
    """500 错误处理"""
    logger.error(f"500 错误: {error}", exc_info=True)
    return jsonify({'success': False, 'error': '服务器内部错误'}), 500


# ========================================
# 管理员操作日志 API
# ========================================

@app.route('/api/admin/logs', methods=['GET'])
def admin_get_logs():
    """获取管理员操作日志"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'error': '请先登录管理后台'}), 401

    try:
        from modules.admin_log_service import admin_log_service
        log_type = request.args.get('type', 'all')
        limit = int(request.args.get('limit', 100))

        if log_type == 'redeem':
            logs = admin_log_service.get_redeem_logs(limit)
        elif log_type == 'user_redeem':
            logs = admin_log_service.get_user_redeem_logs(limit)
        elif log_type == 'prompt':
            logs = admin_log_service.get_prompt_logs(limit)
        else:
            logs = admin_log_service.get_logs(limit)

        return jsonify({'success': True, 'logs': logs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ========================================
# 启动
# ========================================

if __name__ == '__main__':
    # 确保数据目录存在
    os.makedirs('data', exist_ok=True)

    port = Config.PORT
    print(f"\n🚀 猫课电商管理落地班核心工具")
    print(f"📍 访问地址: http://localhost:{port}")
    print(f"📊 模块数量: {len(Config.MODULES)}")
    print(f"🤖 默认模型: {Config.DEFAULT_MODEL}\n")

    app.run(host='0.0.0.0', port=port, debug=False)
