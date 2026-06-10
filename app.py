# -*- coding: utf-8 -*-
import os, logging, threading, time, hashlib
import eventlet
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, session, redirect, url_for, make_response
from flask_socketio import SocketIO
from config import HOST, PORT, DEBUG, SECRET_KEY, CPU_THRESHOLD, MEM_THRESHOLD, DISK_THRESHOLD, load_aes_key, DEFAULT_ADMIN_PASSWORD
from models import init_db, list_groups, add_group, delete_group, list_servers, add_server, delete_server, add_inspection_task, list_inspection_tasks, get_inspection_task, update_inspection_task, delete_inspection_task, toggle_task_schedule, update_task_last_run, migrate_inspection_tasks_schema, add_user, get_user, list_users, delete_user, update_user
from crypto_utils import aes_gcm_encrypt, aes_gcm_decrypt
from inspection import inspect_server, test_proxy
from report_excel import generate_excel_report

# ---------------- Logging ----------------
from config import LOG_DIR
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "app.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ops-app")

# ---------------- Flask/SIO ----------------
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['JSON_AS_ASCII'] = False
app.config['SESSION_TYPE'] = 'filesystem'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# 角色定义
ROLES = {
    'admin': '超级管理员',
    'operator': '系统操作员',
    'viewer': '报告查看员'
}

class CurrentUser:
    """当前用户上下文"""
    def __init__(self):
        self.username = '未登录'
        self.display_name = None
        self.role = 'viewer'
        self.role_text = '报告查看员'
        self.is_authenticated = False
    
    def from_session(self):
        """从session加载用户信息"""
        if 'username' in session and 'role' in session:
            self.username = session['username']
            self.role = session['role']
            self.role_text = ROLES.get(self.role, self.role)
            self.is_authenticated = True
            
            try:
                user_info = get_user(self.username)
                if user_info:
                    self.display_name = user_info.get('display_name')
            except Exception as e:
                logger.error(f'获取用户信息失败: {str(e)}')
        return self

def hash_password(password):
    """密码哈希"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_default_admin():
    """初始化默认管理员用户"""
    admin_user = get_user('admin')
    if not admin_user:
        # 创建默认admin用户
        hashed_pwd = hash_password(DEFAULT_ADMIN_PASSWORD)
        add_user('admin', hashed_pwd, display_name='admin', role='admin', is_default=1)
        logger.info("默认管理员用户已创建")

def no_cache(f):
    """禁止浏览器缓存装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        response = make_response(f(*args, **kwargs))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    return decorated_function

def login_required(f):
    """登录装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(roles):
    """角色权限装饰器"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'role' not in session:
                return redirect(url_for('login_page'))
            user_role = session['role']
            if user_role not in roles:
                return jsonify({'success': False, 'message': '权限不足'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.context_processor
def inject_user():
    """向模板注入当前用户信息"""
    user = CurrentUser().from_session()
    return {'current_user': user}

# 全局变量存储巡检进度
inspection_progress = {}

def load_progress():
    """从文件加载进度"""
    progress_file = os.path.join(LOG_DIR, "progress.json")
    try:
        if os.path.exists(progress_file):
            with open(progress_file, 'r', encoding='utf-8') as f:
                import json
                return json.load(f)
    except Exception as e:
        logger.error(f"加载进度失败: {e}")
    return {}

def save_progress(progress):
    """保存进度到文件"""
    progress_file = os.path.join(LOG_DIR, "progress.json")
    try:
        import json
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存进度失败: {e}")

# 加载保存的进度
inspection_progress = load_progress()

# init db
init_db()
migrate_inspection_tasks_schema()
init_default_admin()

# ---------------- Auth Routes ----------------
@app.route("/login")
def login_page():
    if 'username' in session:
        return redirect(url_for('index'))
    return render_template("login.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'})
    
    user = get_user(username)
    if not user:
        return jsonify({'success': False, 'message': '用户名或密码错误'})
    
    hashed_pwd = hash_password(password)
    if user['password'] != hashed_pwd:
        return jsonify({'success': False, 'message': '用户名或密码错误'})
    
    session['username'] = user['username']
    session['role'] = user['role']
    return jsonify({'success': True, 'message': '登录成功', 'role': user['role']})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({'success': True})

@app.route("/api/update_password", methods=["POST"])
@no_cache
@login_required
def api_update_password():
    data = request.json
    old_password = data.get('oldPassword', '').strip()
    new_password = data.get('newPassword', '').strip()
    
    if not old_password or not new_password:
        return jsonify({'success': False, 'message': '密码不能为空'})
    
    if not (any(c.islower() for c in new_password) and any(c.isupper() for c in new_password)):
        return jsonify({'success': False, 'message': '密码必须包含大小写字母组合'})
    
    username = session.get('username')
    user = get_user(username)
    
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'})
    
    hashed_old_pwd = hash_password(old_password)
    if user['password'] != hashed_old_pwd:
        return jsonify({'success': False, 'message': '原密码不正确'})
    
    hashed_new_pwd = hash_password(new_password)
    from models import update_user_password
    success = update_user_password(username, hashed_new_pwd)
    
    if success:
        return jsonify({'success': True, 'message': '密码修改成功'})
    else:
        return jsonify({'success': False, 'message': '修改失败'})

@app.route("/profile")
@no_cache
@login_required
def profile_page():
    return render_template("profile.html")

@app.route("/users")
@no_cache
@login_required
@role_required(['admin'])
def users_page():
    return render_template("users.html")

# ---------------- User Management APIs ----------------
@app.route("/api/users", methods=["GET", "POST"])
@no_cache
@login_required
def api_users():
    if request.method == "GET":
        if session.get('role') != 'admin':
            return jsonify([])
        users = list_users()
        # 移除密码字段
        for user in users:
            user.pop('password', None)
        return jsonify(users)
    
    elif request.method == "POST":
        if session.get('role') != 'admin':
            return jsonify({'success': False, 'message': '权限不足'}), 403
        
        data = request.json
        username = data.get('username', '').strip()
        display_name = data.get('display_name', '').strip()
        password = data.get('password', '').strip()
        contact = data.get('contact', '').strip()
        role = data.get('role', '').strip()
        
        if not username:
            return jsonify({'success': False, 'message': '用户名称不能为空'})
        if not password:
            return jsonify({'success': False, 'message': '密码不能为空'})
        if not role:
            return jsonify({'success': False, 'message': '权限角色不能为空'})
        
        # 验证密码格式（必须包含大小写字母）
        if not (any(c.islower() for c in password) and any(c.isupper() for c in password)):
            return jsonify({'success': False, 'message': '密码必须包含大小写字母组合'})
        
        if role not in ROLES:
            return jsonify({'success': False, 'message': '无效的权限角色'})
        
        hashed_pwd = hash_password(password)
        try:
            user_id = add_user(username, hashed_pwd, display_name, contact, role, 0)
            
            if user_id:
                return jsonify({'success': True, 'message': '用户创建成功'})
            else:
                return jsonify({'success': False, 'message': '用户名已存在'})
        except Exception as e:
            logger.error(f'创建用户失败: {str(e)}')
            return jsonify({'success': False, 'message': f'服务器错误: {str(e)}'}), 500

@app.route("/api/users/<int:user_id>", methods=["PUT", "DELETE"])
@no_cache
@login_required
@role_required(['admin'])
def api_user_detail(user_id):
    if request.method == "PUT":
        data = request.json
        username = data.get('username', '').strip()
        display_name = data.get('display_name', '').strip()
        password = data.get('password', '').strip()
        contact = data.get('contact', '').strip()
        role = data.get('role', '').strip()
        
        if not username:
            return jsonify({'success': False, 'message': '用户名不能为空'})
        
        if not role:
            return jsonify({'success': False, 'message': '角色不能为空'})
        
        if password and len(password) < 6:
            return jsonify({'success': False, 'message': '密码至少需要6位'})
        
        try:
            update_user(user_id, username, password if password else None, contact, role, display_name)
            return jsonify({'success': True, 'message': '更新成功'})
        except sqlite3.IntegrityError:
            return jsonify({'success': False, 'message': '用户名已存在'})
    
    elif request.method == "DELETE":
        success = delete_user(user_id)
        if success:
            return jsonify({'success': True, 'message': '删除成功'})
        else:
            return jsonify({'success': False, 'message': '无法删除系统默认用户或用户不存在'})

# ---------------- Page Routes ----------------
@app.route("/")
@no_cache
@login_required
def index():
    return render_template("index.html")

@app.route("/inspect")
@no_cache
@login_required
@role_required(['admin', 'operator'])
def inspect_page():
    groups = list_groups()
    return render_template("inspect.html", groups=groups, cpu=CPU_THRESHOLD, mem=MEM_THRESHOLD, disk=DISK_THRESHOLD)

@app.route("/server_inspect")
@no_cache
@login_required
@role_required(['admin', 'operator'])
def server_inspect_page():
    tasks = list_inspection_tasks()
    return render_template("server_inspect.html", tasks=tasks)

@app.route("/servers")
@no_cache
@login_required
@role_required(['admin', 'operator'])
def servers_page():
    groups = list_groups()
    servers = list_servers()
    return render_template("servers.html", groups=groups, servers=servers)

@app.route("/test_button")
@no_cache
@login_required
@role_required(['admin', 'operator'])
def test_button():
    return render_template("test_button.html")

@app.route("/reports")
@no_cache
@login_required
def reports_page():
    return render_template("reports.html")

# --------- APIs: groups & servers ----------
@app.route("/api/groups", methods=["GET", "POST", "DELETE"])
def api_groups():
    if request.method == "GET":
        return jsonify(list_groups())
    elif request.method == "POST":
        data = request.json
        name = data.get("name","").strip()
        if not name:
            return jsonify({"ok": False, "msg": "name required"}), 400
        add_group(name)
        return jsonify({"ok": True})
    elif request.method == "DELETE":
        gid = int(request.args.get("id"))
        delete_group(gid)
        return jsonify({"ok": True})

@app.route("/api/servers", methods=["GET", "POST", "DELETE"])
def api_servers():
    if request.method == "GET":
        gid = request.args.get("group_id")
        gid = int(gid) if gid else None
        return jsonify(list_servers(gid))
    elif request.method == "POST":
        data = request.json
        ip = data["ip"]
        port = int(data.get("port", 22))
        username = data["username"]
        password = data["password"]  # plain from UI
        group_ids = data.get("group_ids", [])  # 支持多分组
        notes = data.get("notes","")
        key = load_aes_key()
        enc = aes_gcm_encrypt(key, password)
        add_server(ip, port, username, enc, group_ids, notes)
        return jsonify({"ok": True})
    elif request.method == "DELETE":
        sid = int(request.args.get("id"))
        delete_server(sid)
        return jsonify({"ok": True})

# ------------- Reports -------------
@app.route("/api/reports", methods=["GET"])
def api_list_reports():
    """获取报告列表"""
    reports = []
    report_dir = os.path.join(os.path.dirname(__file__), 'reports')
    
    if os.path.exists(report_dir):
        for filename in os.listdir(report_dir):
            if filename.endswith('.xlsx') or filename.endswith('.pdf'):
                filepath = os.path.join(report_dir, filename)
                mtime = os.path.getmtime(filepath)
                mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                reports.append({
                    'filename': filename,
                    'mtime': mtime_str
                })
    
    # 按时间倒序排列
    reports.sort(key=lambda x: x['mtime'], reverse=True)
    return jsonify(reports)

@app.route("/api/reports/<path:filename>", methods=["DELETE"])
def api_delete_report(filename):
    """删除报告"""
    report_dir = os.path.join(os.path.dirname(__file__), 'reports')
    filepath = os.path.join(report_dir, filename)
    
    # 安全检查：防止路径遍历
    if not os.path.abspath(filepath).startswith(os.path.abspath(report_dir)):
        return jsonify({'message': '非法路径'}), 400
    
    if not os.path.exists(filepath):
        return jsonify({'message': '文件不存在'}), 404
    
    try:
        os.remove(filepath)
        logger.info(f"报告已删除: {filename}")
        return jsonify({'message': '删除成功'}), 200
    except Exception as e:
        logger.error(f"删除报告失败: {e}")
        return jsonify({'message': f'删除失败: {str(e)}'}), 500

@app.route("/api/proxy-test", methods=["POST"])
def api_proxy_test():
    """网关代理检测"""
    try:
        data = request.json
        group_id = data.get('group_id', '')
        curl_cmd = data.get('curl_cmd', '')
        success_keyword = data.get('success_keyword', '成功')
        
        if not curl_cmd.strip():
            return jsonify({'success': False, 'message': '请输入CURL命令'}), 400
        
        # 获取服务器列表
        servers = list_servers(group_id) if group_id else list_servers()
        
        if not servers:
            return jsonify({'success': False, 'message': '没有找到服务器'}), 404
        
        results = []
        for server in servers:
            password = aes_gcm_decrypt(server.password, aes_key)
            res = test_proxy(
                server.ip,
                server.port,
                server.username,
                password,
                curl_cmd,
                success_keyword
            )
            results.append(res)
        
        return jsonify({
            'success': True,
            'message': '检测完成',
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"网关代理检测失败: {e}")
        return jsonify({'success': False, 'message': f'检测失败: {str(e)}'}), 500

@app.route("/download/<path:filename>")
def download_report(filename):
    """下载报告文件"""
    report_dir = os.path.join(os.path.dirname(__file__), 'reports')
    filepath = os.path.join(report_dir, filename)
    
    if not os.path.exists(filepath):
        return jsonify({"error": "文件不存在"}), 404
    
    # 安全检查：防止路径遍历
    if '..' in filename or filename.startswith('/'):
        return jsonify({"error": "非法路径"}), 403
    
    return send_from_directory(report_dir, filename, as_attachment=True)

@app.route("/api/preview_report/<path:filename>")
def preview_report(filename):
    """在线预览报告文件"""
    report_dir = os.path.join(os.path.dirname(__file__), 'reports')
    filepath = os.path.join(report_dir, filename)
    
    if not os.path.exists(filepath):
        return jsonify({"error": "文件不存在"}), 404
    
    if '..' in filename or filename.startswith('/'):
        return jsonify({"error": "非法路径"}), 403
    
    ext = filename.split('.')[-1].lower()
    if ext == 'pdf':
        return send_from_directory(report_dir, filename, mimetype='application/pdf')
    elif ext == 'xlsx':
        return send_from_directory(report_dir, filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        return send_from_directory(report_dir, filename)

# ------------- Inspection Tasks -------------
@app.route("/api/save_task", methods=["POST"])
def api_save_task():
    data = request.json or {}
    task_name = data.get("task_name", "")
    project_name = data.get("project_name", "")
    inspector = data.get("inspector", "")
    report_format = data.get("report_format", "excel")
    resource_group_id = data.get("resource_group_id")
    check_cpu = data.get("check_cpu", True)
    check_mem = data.get("check_mem", True)
    check_disk = data.get("check_disk", True)
    enable_proxy = data.get("enable_proxy", False)
    proxy_rules = data.get("proxy_rules", [])
    enable_schedule = data.get("enable_schedule", False)
    schedule_time = data.get("schedule_time", "")
    
    if not task_name:
        return jsonify({"ok": False, "msg": "请输入任务名称"}), 400
    if not project_name:
        return jsonify({"ok": False, "msg": "请输入项目名称"}), 400
    if not inspector:
        return jsonify({"ok": False, "msg": "请输入巡检人"}), 400
    
    add_inspection_task(
        name=task_name,
        project_name=project_name,
        inspector=inspector,
        report_format=report_format,
        resource_group_id=resource_group_id,
        check_cpu=check_cpu,
        check_mem=check_mem,
        check_disk=check_disk,
        enable_proxy=enable_proxy,
        proxy_rules=proxy_rules,
        enable_schedule=enable_schedule,
        schedule_time=schedule_time
    )
    
    return jsonify({"ok": True, "msg": "任务保存成功"})


@app.route("/api/task", methods=["GET"])
def api_get_task():
    task_id = request.args.get("id")
    if not task_id:
        return jsonify({"ok": False, "msg": "缺少任务ID"}), 400
    
    task = get_inspection_task(task_id)
    if not task:
        return jsonify({"ok": False, "msg": "任务不存在"}), 404
    
    return jsonify(task)


@app.route("/api/update_task", methods=["POST"])
def api_update_task():
    data = request.json or {}
    task_id = data.get("id")
    task_name = data.get("task_name", "")
    project_name = data.get("project_name", "")
    inspector = data.get("inspector", "")
    report_format = data.get("report_format", "excel")
    resource_group_id = data.get("resource_group_id")
    check_cpu = data.get("check_cpu", True)
    check_mem = data.get("check_mem", True)
    check_disk = data.get("check_disk", True)
    enable_proxy = data.get("enable_proxy", False)
    proxy_rules = data.get("proxy_rules", [])
    enable_schedule = data.get("enable_schedule", False)
    schedule_time = data.get("schedule_time", "")
    
    if not task_id:
        return jsonify({"ok": False, "msg": "缺少任务ID"}), 400
    if not task_name:
        return jsonify({"ok": False, "msg": "请输入任务名称"}), 400
    if not project_name:
        return jsonify({"ok": False, "msg": "请输入项目名称"}), 400
    if not inspector:
        return jsonify({"ok": False, "msg": "请输入巡检人"}), 400
    
    task = get_inspection_task(task_id)
    if not task:
        return jsonify({"ok": False, "msg": "任务不存在"}), 404
    
    update_inspection_task(
        task_id=task_id,
        name=task_name,
        project_name=project_name,
        inspector=inspector,
        report_format=report_format,
        resource_group_id=resource_group_id,
        check_cpu=check_cpu,
        check_mem=check_mem,
        check_disk=check_disk,
        enable_proxy=enable_proxy,
        proxy_rules=proxy_rules,
        enable_schedule=enable_schedule,
        schedule_time=schedule_time
    )
    
    return jsonify({"ok": True, "msg": "任务更新成功"})


@app.route("/api/toggle_schedule", methods=["POST"])
def api_toggle_schedule():
    data = request.json or {}
    task_id = data.get("id")
    
    if not task_id:
        return jsonify({"ok": False, "msg": "缺少任务ID"}), 400
    
    task = get_inspection_task(task_id)
    if not task:
        return jsonify({"ok": False, "msg": "任务不存在"}), 404
    
    toggle_task_schedule(task_id)
    return jsonify({"ok": True, "msg": "定时状态已切换"})

@app.route("/api/run_task", methods=["POST"])
def api_run_task():
    data = request.json or {}
    task_id = data.get("task_id")
    
    task = get_inspection_task(task_id)
    if not task:
        return jsonify({"ok": False, "msg": "任务不存在"}), 404
    
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    thread = threading.Thread(target=run_inspection, args=(
        run_id,
        task["project_name"],
        task["inspector"],
        task["report_format"],
        task["resource_group_id"],
        task["check_cpu"],
        task["check_mem"],
        task["check_disk"],
        task["enable_proxy"],
        task["proxy_rules"],
        task_id
    ))
    thread.daemon = True
    thread.start()
    
    return jsonify({"ok": True, "run_id": run_id})

@app.route("/api/delete_task", methods=["POST"])
def api_delete_task():
    data = request.json or {}
    task_id = data.get("task_id")
    
    task = get_inspection_task(task_id)
    if not task:
        return jsonify({"ok": False, "msg": "任务不存在"}), 404
    
    delete_inspection_task(task_id)
    return jsonify({"ok": True, "msg": "任务删除成功"})

# ------------- Start Inspection -------------
@app.route("/api/start_inspection", methods=["POST"])
def api_start_inspection():
    data = request.json or {}
    project_name = data.get("project_name","")
    inspector = data.get("inspector","")
    report_format = data.get("report_format", "excel")
    
    # 资源巡检参数
    resource_group_id = data.get("resource_group_id")
    check_cpu = data.get("check_cpu", True)
    check_mem = data.get("check_mem", True)
    check_disk = data.get("check_disk", True)
    
    # 网关代理检测参数 - 支持多条规则
    enable_proxy = data.get("enable_proxy", False)
    proxy_rules = data.get("proxy_rules", [])
    
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    thread = threading.Thread(target=run_inspection, args=(run_id, project_name, inspector, report_format, resource_group_id, check_cpu, check_mem, check_disk, enable_proxy, proxy_rules))
    thread.daemon = True
    thread.start()
    return jsonify({"ok": True, "run_id": run_id})

def update_progress(run_id, message, percent, report_path=None):
    """更新巡检进度"""
    inspection_progress[run_id] = {
        "message": message,
        "percent": percent,
        "report_path": report_path
    }
    # 保存进度到文件，防止服务器重启丢失
    save_progress(inspection_progress)

def get_servers_by_group_param(group_param):
    """根据分组参数获取服务器列表"""
    if group_param == "" or group_param is None:
        return list_servers(None)
    elif group_param.isdigit():
        return list_servers(int(group_param))
    else:
        return list_servers(None)

def run_inspection(run_id: str, project_name: str, inspector: str, report_format: str = "excel", 
                   resource_group_id=None, check_cpu=True, check_mem=True, check_disk=True,
                   enable_proxy=False, proxy_rules=None, task_id=None):
    key = load_aes_key()
    proxy_rules = proxy_rules or []
    
    # 记录开始时间，用于更新 last_run
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 资源巡检使用的分组
    resource_servers = get_servers_by_group_param(resource_group_id)
    resource_total = len(resource_servers)
    rows = []
    proxy_results = []
    
    # 是否执行网关代理检测
    do_proxy_test = enable_proxy and len(proxy_rules) > 0
    
    # 计算总步骤数（服务器巡检 + 网关代理检测）
    total_steps = resource_total
    if do_proxy_test:
        # 每个规则的服务器数量总和
        for rule in proxy_rules:
            servers = get_servers_by_group_param(rule.get('group_id'))
            total_steps += len(servers)
    
    # 初始化进度
    update_progress(run_id, "开始资源巡检...", 0)
    
    current_step = 0
    
    # 服务器资源巡检
    for idx, s in enumerate(resource_servers, start=1):
        try:
            msg = f"连接 {s['ip']}... ({idx}/{resource_total})"
            update_progress(run_id, msg, int(current_step/max(total_steps,1)*100))
            socketio.emit("progress", {
                "run_id": run_id,
                "message": msg,
                "percent": int(current_step/max(total_steps,1)*100)
            })
            
            password = aes_gcm_decrypt(key, s["enc_password"])
            res = inspect_server(s["ip"], s["port"], s["username"], password, check_cpu, check_mem, check_disk)
            rows.append(res)
            
            current_step += 1
            
            # 根据选择的巡检项显示结果
            result_parts = []
            if check_cpu:
                result_parts.append(f"CPU:{res['cpu']}%")
            if check_mem:
                result_parts.append(f"MEM:{res['mem']}%")
            if check_disk:
                result_parts.append(f"DISK:{res['disk']}%")
            
            msg = f"完成 {s['ip']}  {', '.join(result_parts)}"
            update_progress(run_id, msg, int(current_step/max(total_steps,1)*100))
            socketio.emit("progress", {
                "run_id": run_id,
                "message": msg,
                "percent": int(current_step/max(total_steps,1)*100)
            })
        except Exception as e:
            rows.append({"ip": s["ip"], "ok": False, "error": str(e), "uptime":"", "cpu":0, "mem":0, "disk":0})
            current_step += 1
            
            msg = f"失败 {s['ip']}: {e}"
            update_progress(run_id, msg, int(current_step/max(total_steps,1)*100))
            socketio.emit("progress", {
                "run_id": run_id,
                "message": msg,
                "percent": int(current_step/max(total_steps,1)*100)
            })
        time.sleep(0.2)

    # 网关代理检测 - 支持多条规则
    if do_proxy_test:
        update_progress(run_id, "开始网关代理检测...", int(current_step/max(total_steps,1)*100))
        socketio.emit("progress", {
            "run_id": run_id,
            "message": "开始网关代理检测...",
            "percent": int(current_step/max(total_steps,1)*100)
        })
        
        rule_index = 0
        for rule in proxy_rules:
            rule_index += 1
            rule_group_id = rule.get('group_id')
            curl_command = rule.get('curl_command', '')
            success_keyword = rule.get('success_keyword', '成功')
            
            proxy_servers = get_servers_by_group_param(rule_group_id)
            proxy_total = len(proxy_servers)
            
            for idx, s in enumerate(proxy_servers, start=1):
                try:
                    msg = f"检测代理 [{rule_index}] {s['ip']}... ({idx}/{proxy_total})"
                    update_progress(run_id, msg, int(current_step/max(total_steps,1)*100))
                    socketio.emit("progress", {
                        "run_id": run_id,
                        "message": msg,
                        "percent": int(current_step/max(total_steps,1)*100)
                    })
                    
                    password = aes_gcm_decrypt(key, s["enc_password"])
                    res = test_proxy(s["ip"], s["port"], s["username"], password, curl_command, success_keyword)
                    proxy_results.append(res)
                    
                    current_step += 1
                    status = "正常" if res["success"] else ("连接失败" if res["error"] else "异常")
                    msg = f"代理检测 [{rule_index}] {s['ip']}: {status}"
                    update_progress(run_id, msg, int(current_step/max(total_steps,1)*100))
                    socketio.emit("progress", {
                        "run_id": run_id,
                        "message": msg,
                        "percent": int(current_step/max(total_steps,1)*100)
                    })
                except Exception as e:
                    proxy_results.append({"ip": s["ip"], "success": False, "output": "", "error": str(e)})
                    current_step += 1
                    
                    msg = f"代理检测失败 [{rule_index}] {s['ip']}: {e}"
                    update_progress(run_id, msg, int(current_step/max(total_steps,1)*100))
                    socketio.emit("progress", {
                        "run_id": run_id,
                        "message": msg,
                        "percent": int(current_step/max(total_steps,1)*100)
                    })
                time.sleep(0.2)

    # 根据格式生成报告
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        if report_format == "pdf":
            # 延迟导入 PDF 生成模块
            from report_pdf import generate_pdf_report
            report_path = generate_pdf_report(project_name, inspector, date_str, rows, proxy_results, check_cpu, check_mem, check_disk)
        else:
            report_path = generate_excel_report(project_name, inspector, date_str, rows, proxy_results, check_cpu, check_mem, check_disk)
        
        msg = f"报告已生成: {os.path.basename(report_path)}"
        update_progress(run_id, msg, 100, report_path)
        socketio.emit("progress", {
            "run_id": run_id,
            "message": msg,
            "percent": 100,
            "report_path": report_path
        })
    except ImportError as e:
        msg = f"PDF报告生成失败: 需要安装 reportlab 库"
        update_progress(run_id, msg, 100)
        socketio.emit("progress", {
            "run_id": run_id,
            "message": msg,
            "percent": 100
        })
        logger.error(f"报告生成失败: {e}")
    except Exception as e:
        msg = f"报告生成失败: {str(e)}"
        update_progress(run_id, msg, 100)
        socketio.emit("progress", {
            "run_id": run_id,
            "message": msg,
            "percent": 100
        })
        logger.error(f"报告生成失败: {e}")
    
    # 更新任务最后执行时间
    if task_id:
        update_task_last_run(task_id)

@app.route("/api/inspection_progress")
def api_inspection_progress():
    run_id = request.args.get("run_id")
    if run_id and run_id in inspection_progress:
        return jsonify(inspection_progress[run_id])
    return jsonify({"message": "", "percent": 0})

@app.route("/api/download_report")
def api_download_report():
    path = request.args.get("path")
    if not path or not os.path.exists(path):
        return "Not Found", 404
    return send_file(path, as_attachment=True)

# ---------------- Scheduler ----------------
def run_scheduled_tasks():
    """定时任务调度器"""
    logger.info("调度器线程启动")
    while True:
        try:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            
            # 获取所有启用定时的任务
            tasks = list_inspection_tasks()
            
            for task in tasks:
                if task.get("enable_schedule") and task.get("schedule_time"):
                    schedule_time = task["schedule_time"]
                    
                    # 检查是否到了执行时间（每分钟检查一次）
                    if schedule_time == current_time:
                        logger.info(f"[调度器] 执行定时任务: {task['name']}")
                        run_id = now.strftime("%Y%m%d%H%M%S")
                        # 使用协程执行巡检任务，避免线程数限制
                        try:
                            eventlet.spawn(run_inspection,
                                run_id,
                                task["project_name"],
                                task["inspector"],
                                task["report_format"],
                                task["resource_group_id"],
                                task["check_cpu"],
                                task["check_mem"],
                                task["check_disk"],
                                task["enable_proxy"],
                                task["proxy_rules"],
                                task["id"]
                            )
                            logger.info(f"[调度器] 任务 {task['name']} 已启动（协程模式）")
                        except RuntimeError as e:
                            logger.warning(f"协程启动失败，尝试线程模式: {e}")
                            try:
                                thread = threading.Thread(target=run_inspection, args=(
                                    run_id,
                                    task["project_name"],
                                    task["inspector"],
                                    task["report_format"],
                                    task["resource_group_id"],
                                    task["check_cpu"],
                                    task["check_mem"],
                                    task["check_disk"],
                                    task["enable_proxy"],
                                    task["proxy_rules"],
                                    task["id"]
                                ))
                                thread.daemon = True
                                thread.start()
                            except RuntimeError as e2:
                                logger.error(f"线程启动也失败: {e2}")
                        
        except Exception as e:
            logger.error(f"定时任务调度器错误: {e}")
        
        # 每分钟检查一次
        time.sleep(60)

def start_scheduler():
    """启动定时任务调度器（使用协程避免线程数限制）"""
    try:
        eventlet.spawn(run_scheduled_tasks)
        logger.info("定时任务调度器已启动（协程模式）")
    except RuntimeError as e:
        logger.warning(f"协程启动失败，尝试线程模式: {e}")
        try:
            scheduler_thread = threading.Thread(target=run_scheduled_tasks)
            scheduler_thread.daemon = True
            scheduler_thread.start()
            logger.info("定时任务调度器已启动（线程模式）")
        except RuntimeError as e2:
            logger.error(f"线程启动也失败: {e2}")

def main():
    logger.info("Starting Ops Inspection System...")
    # 启动定时任务调度器（只在主进程中启动，避免DEBUG模式重启时重复启动）
    # Werkzeug在DEBUG模式下会fork一个子进程，子进程会设置WERKZEUG_RUN_MAIN环境变量
    # 使用全局DEBUG变量而不是app.debug，因为app.debug此时可能还未设置
    is_first_process = os.environ.get('WERKZEUG_RUN_MAIN') is None
    if DEBUG:
        # DEBUG模式：只有重启后的子进程才启动调度器
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            start_scheduler()
    else:
        # 非DEBUG模式：直接启动调度器
        start_scheduler()
    socketio.run(app, host=HOST, port=PORT, debug=DEBUG, allow_unsafe_werkzeug=True)

if __name__ == "__main__":
    main()
