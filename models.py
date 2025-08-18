# -*- coding: utf-8 -*-
from dataclasses import dataclass, field, asdict
from typing import Optional, List
import sqlite3, json, os
from datetime import datetime
from config import SQLITE_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS server_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 22,
    username TEXT NOT NULL,
    enc_password TEXT NOT NULL,
    group_id INTEGER,
    notes TEXT,
    FOREIGN KEY(group_id) REFERENCES server_groups(id)
);
"""

def get_conn():
    os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()

def row_to_dict(cursor, row):
    return {d[0]: row[i] for i, d in enumerate(cursor.description)}

def list_groups():
    conn = get_conn()
    conn.row_factory = row_to_dict
    cur = conn.cursor()
    cur.execute("SELECT * FROM server_groups ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return rows

def add_group(name: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO server_groups(name) VALUES (?)", (name,))
    conn.commit()
    conn.close()

def delete_group(group_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM servers WHERE group_id=?", (group_id,))
    cur.execute("DELETE FROM server_groups WHERE id=?", (group_id,))
    conn.commit()
    conn.close()

def list_servers(group_id: Optional[int] = None):
    conn = get_conn()
    conn.row_factory = row_to_dict
    cur = conn.cursor()
    if group_id is None:
        cur.execute("""
            SELECT s.*, g.name as group_name
            FROM servers s LEFT JOIN server_groups g ON s.group_id=g.id
            ORDER BY s.ip
        """)
    else:
        cur.execute("""
            SELECT s.*, g.name as group_name
            FROM servers s LEFT JOIN server_groups g ON s.group_id=g.id
            WHERE s.group_id=? ORDER BY s.ip
        """, (group_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def add_server(ip: str, port: int, username: str, enc_password: str, group_id: Optional[int], notes: str=""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO servers(ip, port, username, enc_password, group_id, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (ip, port, username, enc_password, group_id, notes))
    conn.commit()
    conn.close()

def delete_server(server_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM servers WHERE id=?", (server_id,))
    conn.commit()
    conn.close()
