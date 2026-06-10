# -*- coding: utf-8 -*-
"""
Global configuration for the Ops Inspection System.
All paths, ports, and thresholds are configurable here.
"""
import os

# ---------------------- Server ----------------------
HOST = os.environ.get("OPS_HOST", "0.0.0.0")
PORT = int(os.environ.get("OPS_PORT", "1999"))
DEBUG = os.environ.get("OPS_DEBUG", "1") == "1"
SECRET_KEY = os.environ.get("OPS_SECRET_KEY", "change-me")
DEFAULT_ADMIN_PASSWORD = os.environ.get("OPS_ADMIN_PASSWORD", "Admin@123")  # 默认admin密码，可通过环境变量覆盖

# ---------------------- Paths -----------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
REPORT_DIR = os.path.join(BASE_DIR, "reports")

# Uploaded/Provided Word template path (absolute fallback)
# If you want to override via env var, set OPS_WORD_TEMPLATE
# WORD_TEMPLATE = os.environ.get(
#     "OPS_WORD_TEMPLATE",
#     os.path.join(BASE_DIR, "templates", "word", "日巡检记录模版.docx")
# )

# ---------------------- AES-GCM ---------------------
# The AES key can be provided via environment variable or read from a file.
# 32 bytes (256-bit) recommended.
AES_KEY_ENV = os.environ.get("OPS_AES_KEY")  # base64 or hex is allowed
AES_KEY_FILE = os.environ.get("OPS_AES_KEY_FILE")  # if set, read raw bytes from file

def load_aes_key() -> bytes:
    """
    Load AES key from env or file. If neither provided, a static dev key is used.
    For production, set OPS_AES_KEY or OPS_AES_KEY_FILE.
    """
    if AES_KEY_FILE and os.path.exists(AES_KEY_FILE):
        with open(AES_KEY_FILE, "rb") as f:
            return f.read()
    if AES_KEY_ENV:
        # try base64 first
        try:
            import base64
            return base64.b64decode(AES_KEY_ENV)
        except Exception:
            pass
        # then try hex
        try:
            return bytes.fromhex(AES_KEY_ENV)
        except Exception:
            pass
    # DEV ONLY fallback key (DO NOT use in production)
    return b"0123456789abcdef0123456789abcdef"  # 32 bytes

# ---------------------- Thresholds ------------------
CPU_THRESHOLD = float(os.environ.get("OPS_CPU_THRESHOLD", "80"))
MEM_THRESHOLD = float(os.environ.get("OPS_MEM_THRESHOLD", "80"))
DISK_THRESHOLD = float(os.environ.get("OPS_DISK_THRESHOLD", "80"))

# ---------------------- Database --------------------
SQLITE_PATH = os.path.join(DATA_DIR, "ops.db")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)
