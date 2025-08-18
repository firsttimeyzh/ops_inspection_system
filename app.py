# -*- coding: utf-8 -*-
import os, logging, threading, time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
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
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

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
        group_id = data.get("group_id")
        group_id = int(group_id) if group_id not in (None, "", "null") else None
        notes = data.get("notes","")
        key = load_aes_key()
        enc = aes_gcm_encrypt(key, password)
        add_server(ip, port, username, enc, group_id, notes)
        return jsonify({"ok": True})
    elif request.method == "DELETE":
        sid = int(request.args.get("id"))
        delete_server(sid)
        return jsonify({"ok": True})

# ------------- Start Inspection -------------
@app.route("/api/start_inspection", methods=["POST"])
def api_start_inspection():
    data = request.json or {}
    group_id = data.get("group_id")
    group_id = int(group_id) if group_id not in (None, "", "null") else None
    project_name = data.get("project_name","")
    inspector = data.get("inspector","")
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    thread = threading.Thread(target=run_inspection, args=(run_id, group_id, project_name, inspector))
    thread.daemon = True
    thread.start()
    return jsonify({"ok": True, "run_id": run_id})

def run_inspection(run_id: str, group_id, project_name: str, inspector: str):
    key = load_aes_key()
    servers = list_servers(group_id)
    total = len(servers)
    rows = []
    for idx, s in enumerate(servers, start=1):
        try:
            socketio.emit("progress", {
                "run_id": run_id,
                "message": f"连接 {s['ip']}... ({idx}/{total})",
                "percent": int((idx-1)/max(total,1)*100)
            })
            password = aes_gcm_decrypt(key, s["enc_password"])
            res = inspect_server(s["ip"], s["port"], s["username"], password)
            rows.append(res)
            socketio.emit("progress", {
                "run_id": run_id,
                "message": f"完成 {s['ip']}  CPU:{res['cpu']}% MEM:{res['mem']}% DISK:{res['disk']}%",
                "percent": int(idx/max(total,1)*100)
            })
        except Exception as e:
            rows.append({"ip": s["ip"], "ok": False, "error": str(e), "uptime":"", "cpu":0, "mem":0, "disk":0})
            socketio.emit("progress", {
                "run_id": run_id,
                "message": f"失败 {s['ip']}: {e}",
                "percent": int(idx/max(total,1)*100)
            })
        time.sleep(0.2)

    # 用完整时间戳写入 Excel 报告
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_path = generate_excel_report(project_name, inspector, date_str, rows)

    socketio.emit("progress", {
        "run_id": run_id,
        "message": f"报告已生成: {os.path.basename(report_path)}",
        "percent": 100,
        "report_path": report_path
    })

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
