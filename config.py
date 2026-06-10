# -*- coding: utf-8 -*-
"""
Global configuration for the Ops Inspection System.
"""
import os

HOST = os.environ.get("OPS_HOST", "0.0.0.0")
PORT = int(os.environ.get("OPS_PORT", "1999"))
DEBUG = os.environ.get("OPS_DEBUG", "1") == "1"
SECRET_KEY = os.environ.get("OPS_SECRET_KEY", "change-me")
DEFAULT_ADMIN_PASSWORD = os.environ.get("OPS_ADMIN_PASSWORD", "Admin@123")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
REPORT_DIR = os.path.join(BASE_DIR, "reports")

AES_KEY_ENV = os.environ.get("OPS_AES_KEY")
AES_KEY_FILE = os.environ.get("OPS_AES_KEY_FILE")

def load_aes_key():
    if AES_KEY_FILE and os.path.exists(AES_KEY_FILE):
        with open(AES_KEY_FILE, "rb") as f:
            return f.read()
    if AES_KEY_ENV:
        try:
            import base64
            return base64.b64decode(AES_KEY_ENV)
        except Exception:
            pass
        try:
            return bytes.fromhex(AES_KEY_ENV)
        except Exception:
            pass
    return b"0123456789abcdef0123456789abcdef"

CPU_THRESHOLD = float(os.environ.get("OPS_CPU_THRESHOLD", "80"))
MEM_THRESHOLD = float(os.environ.get("OPS_MEM_THRESHOLD", "80"))
DISK_THRESHOLD = float(os.environ.get("OPS_DISK_THRESHOLD", "80"))

SQLITE_PATH = os.path.join(DATA_DIR, "ops.db")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)
