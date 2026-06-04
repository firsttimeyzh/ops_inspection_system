# -*- coding: utf-8 -*-
import os, logging, threading, time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from flask_socketio import SocketIO
from config import HOST, PORT, DEBUG, SECRET_KEY, CPU_THRESHOLD, MEM_THRESHOLD, DISK_THRESHOLD, load_aes_key
from models import init_db, list_groups, add_group, delete_group, list_servers, add_server, delete_server
from crypto_utils import aes_gcm_encrypt, aes_gcm_decrypt
from inspection import inspect_server
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
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

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

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/inspect")
def inspect_page():
    groups = list_groups()
    return render_template("inspect.html", groups=groups, cpu=CPU_THRESHOLD, mem=MEM_THRESHOLD, disk=DISK_THRESHOLD)

@app.route("/servers")
def servers_page():
    groups = list_groups()
    servers = list_servers()
    return render_template("servers.html", groups=groups, servers=servers)

@app.route("/test_button")
def test_button():
    return render_template("test_button.html")

@app.route("/reports")
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

# ------------- Start Inspection -------------
@app.route("/api/start_inspection", methods=["POST"])
def api_start_inspection():
    data = request.json or {}
    group_id = data.get("group_id")
    group_id = int(group_id) if group_id not in (None, "", "null") else None
    project_name = data.get("project_name","")
    inspector = data.get("inspector","")
    report_format = data.get("report_format", "excel")
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    thread = threading.Thread(target=run_inspection, args=(run_id, group_id, project_name, inspector, report_format))
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

def run_inspection(run_id: str, group_id, project_name: str, inspector: str, report_format: str = "excel"):
    key = load_aes_key()
    servers = list_servers(group_id)
    total = len(servers)
    rows = []
    
    # 初始化进度
    update_progress(run_id, "开始巡检...", 0)
    
    for idx, s in enumerate(servers, start=1):
        try:
            msg = f"连接 {s['ip']}... ({idx}/{total})"
            update_progress(run_id, msg, int((idx-1)/max(total,1)*100))
            socketio.emit("progress", {
                "run_id": run_id,
                "message": msg,
                "percent": int((idx-1)/max(total,1)*100)
            })
            
            password = aes_gcm_decrypt(key, s["enc_password"])
            res = inspect_server(s["ip"], s["port"], s["username"], password)
            rows.append(res)
            
            msg = f"完成 {s['ip']}  CPU:{res['cpu']}% MEM:{res['mem']}% DISK:{res['disk']}%"
            update_progress(run_id, msg, int(idx/max(total,1)*100))
            socketio.emit("progress", {
                "run_id": run_id,
                "message": msg,
                "percent": int(idx/max(total,1)*100)
            })
        except Exception as e:
            rows.append({"ip": s["ip"], "ok": False, "error": str(e), "uptime":"", "cpu":0, "mem":0, "disk":0})
            
            msg = f"失败 {s['ip']}: {e}"
            update_progress(run_id, msg, int(idx/max(total,1)*100))
            socketio.emit("progress", {
                "run_id": run_id,
                "message": msg,
                "percent": int(idx/max(total,1)*100)
            })
        time.sleep(0.2)

    # 根据格式生成报告
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        if report_format == "pdf":
            # 延迟导入 PDF 生成模块
            from report_pdf import generate_pdf_report
            report_path = generate_pdf_report(project_name, inspector, date_str, rows)
        else:
            report_path = generate_excel_report(project_name, inspector, date_str, rows)
        
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

def main():
    logger.info("Starting Ops Inspection System...")
    socketio.run(app, host=HOST, port=PORT, debug=DEBUG, allow_unsafe_werkzeug=True)

if __name__ == "__main__":
    main()
