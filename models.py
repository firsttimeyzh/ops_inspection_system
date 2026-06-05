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
    notes TEXT
);
CREATE TABLE IF NOT EXISTS server_group_memberships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE,
    FOREIGN KEY(group_id) REFERENCES server_groups(id) ON DELETE CASCADE,
    UNIQUE(server_id, group_id)
);
CREATE TABLE IF NOT EXISTS inspection_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    project_name TEXT NOT NULL,
    inspector TEXT NOT NULL,
    report_format TEXT DEFAULT 'excel',
    resource_group_id TEXT,
    check_cpu INTEGER DEFAULT 1,
    check_mem INTEGER DEFAULT 1,
    check_disk INTEGER DEFAULT 1,
    enable_proxy INTEGER DEFAULT 0,
    proxy_rules TEXT,
    enable_schedule INTEGER DEFAULT 0,
    schedule_time TEXT,
    last_run TEXT,
    created_at TEXT NOT NULL
);
"""

def get_conn():
    os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
    conn.execute("PRAGMA encoding='UTF-8'")
    conn.execute("PRAGMA foreign_keys=ON")
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
    cur.execute("DELETE FROM server_groups WHERE id=?", (group_id,))
    conn.commit()
    conn.close()

def list_servers(group_id: Optional[int] = None):
    conn = get_conn()
    conn.row_factory = row_to_dict
    cur = conn.cursor()
    
    if group_id is None:
        # 获取所有服务器及其分组信息
        cur.execute("SELECT * FROM servers ORDER BY ip")
        servers = cur.fetchall()
        
        # 为每个服务器获取所属分组
        for server in servers:
            cur.execute("""
                SELECT g.* FROM server_groups g 
                INNER JOIN server_group_memberships m ON g.id = m.group_id
                WHERE m.server_id = ?
            """, (server['id'],))
            server['groups'] = cur.fetchall()
            server['group_names'] = ', '.join([g['name'] for g in server['groups']]) if server['groups'] else '无'
        conn.close()
        return servers
    else:
        # 获取指定分组的服务器
        cur.execute("""
            SELECT s.* FROM servers s
            INNER JOIN server_group_memberships m ON s.id = m.server_id
            WHERE m.group_id = ?
            ORDER BY s.ip
        """, (group_id,))
        servers = cur.fetchall()
        
        # 为每个服务器获取所属分组
        for server in servers:
            cur.execute("""
                SELECT g.* FROM server_groups g 
                INNER JOIN server_group_memberships m ON g.id = m.group_id
                WHERE m.server_id = ?
            """, (server['id'],))
            server['groups'] = cur.fetchall()
            server['group_names'] = ', '.join([g['name'] for g in server['groups']]) if server['groups'] else '无'
        conn.close()
        return servers

def get_server_group_ids(server_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT group_id FROM server_group_memberships WHERE server_id = ?", (server_id,))
    group_ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return group_ids

def add_server(ip: str, port: int, username: str, enc_password: str, 
               group_ids: Optional[List[int]] = None, notes: str=""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO servers(ip, port, username, enc_password, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (ip, port, username, enc_password, notes))
    server_id = cur.lastrowid
    
    # 添加分组关联
    if group_ids:
        for group_id in group_ids:
            try:
                cur.execute("""
                    INSERT OR IGNORE INTO server_group_memberships(server_id, group_id)
                    VALUES (?, ?)
                """, (server_id, group_id))
            except sqlite3.IntegrityError:
                pass  # 已存在，忽略
    
    conn.commit()
    conn.close()

def update_server_groups(server_id: int, group_ids: List[int]):
    conn = get_conn()
    cur = conn.cursor()
    
    # 删除旧的关联
    cur.execute("DELETE FROM server_group_memberships WHERE server_id = ?", (server_id,))
    
    # 添加新的关联
    for group_id in group_ids:
        try:
            cur.execute("""
                INSERT OR IGNORE INTO server_group_memberships(server_id, group_id)
                VALUES (?, ?)
            """, (server_id, group_id))
        except sqlite3.IntegrityError:
            pass  # 已存在，忽略
    
    conn.commit()
    conn.close()

def delete_server(server_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM servers WHERE id=?", (server_id,))
    conn.commit()
    conn.close()

def migrate_from_old_schema():
    """从旧的单分组模式迁移数据到新的多分组模式"""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # 检查是否有旧的 group_id 列
        cur.execute("PRAGMA table_info(servers)")
        columns = [row[1] for row in cur.fetchall()]
        
        if 'group_id' in columns:
            print("检测到旧数据格式，开始迁移...")
            # 迁移旧数据
            cur.execute("SELECT id, group_id FROM servers WHERE group_id IS NOT NULL")
            old_data = cur.fetchall()
            
            for server_id, group_id in old_data:
                try:
                    cur.execute("""
                        INSERT OR IGNORE INTO server_group_memberships(server_id, group_id)
                        VALUES (?, ?)
                    """, (server_id, group_id))
                except sqlite3.Error:
                    pass
            
            # 删除旧列
            cur.execute("CREATE TABLE servers_new (id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 22, username TEXT NOT NULL, enc_password TEXT NOT NULL, notes TEXT)")
            cur.execute("INSERT INTO servers_new (id, ip, port, username, enc_password, notes) SELECT id, ip, port, username, enc_password, notes FROM servers")
            cur.execute("DROP TABLE servers")
            cur.execute("ALTER TABLE servers_new RENAME TO servers")
            
            conn.commit()
            print("数据迁移成功！")
    except sqlite3.Error as e:
        print(f"迁移出错: {e}")
    finally:
        conn.close()


def migrate_inspection_tasks_schema():
    """迁移巡检任务表，添加新列"""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # 检查 inspection_tasks 表的列
        cur.execute("PRAGMA table_info(inspection_tasks)")
        columns = [row[1] for row in cur.fetchall()]
        
        # 添加缺失的列
        if 'enable_schedule' not in columns:
            print("添加 enable_schedule 列...")
            cur.execute("ALTER TABLE inspection_tasks ADD COLUMN enable_schedule INTEGER DEFAULT 0")
        
        if 'schedule_time' not in columns:
            print("添加 schedule_time 列...")
            cur.execute("ALTER TABLE inspection_tasks ADD COLUMN schedule_time TEXT")
        
        if 'last_run' not in columns:
            print("添加 last_run 列...")
            cur.execute("ALTER TABLE inspection_tasks ADD COLUMN last_run TEXT")
        
        conn.commit()
        print("巡检任务表迁移完成")
    except sqlite3.Error as e:
        print(f"巡检任务表迁移失败: {e}")
    finally:
        conn.close()


# 巡检任务相关操作
def add_inspection_task(name: str, project_name: str, inspector: str, report_format: str = "excel",
                        resource_group_id=None, check_cpu=True, check_mem=True, check_disk=True,
                        enable_proxy=False, proxy_rules=None, enable_schedule=False, schedule_time=None):
    """添加巡检任务"""
    conn = get_conn()
    cur = conn.cursor()
    proxy_rules_json = json.dumps(proxy_rules or [])
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cur.execute("""
        INSERT INTO inspection_tasks(name, project_name, inspector, report_format, 
                                    resource_group_id, check_cpu, check_mem, check_disk,
                                    enable_proxy, proxy_rules, enable_schedule, schedule_time, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, project_name, inspector, report_format, 
          resource_group_id, 1 if check_cpu else 0, 1 if check_mem else 0, 1 if check_disk else 0,
          1 if enable_proxy else 0, proxy_rules_json, 1 if enable_schedule else 0, schedule_time, created_at))
    
    conn.commit()
    conn.close()

def list_inspection_tasks():
    """获取所有巡检任务"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM inspection_tasks ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    
    tasks = []
    for row in rows:
        resource_checks = []
        if row[6]:
            resource_checks.append("CPU")
        if row[7]:
            resource_checks.append("内存")
        if row[8]:
            resource_checks.append("磁盘")
        
        tasks.append({
            "id": row[0],
            "name": row[1],
            "project_name": row[2],
            "inspector": row[3],
            "report_format": row[4],
            "resource_group_id": row[5],
            "check_cpu": bool(row[6]),
            "check_mem": bool(row[7]),
            "check_disk": bool(row[8]),
            "enable_proxy": bool(row[9]),
            "proxy_rules": json.loads(row[10]) if row[10] else [],
            "created_at": row[11],
            "enable_schedule": bool(row[12]) if len(row) > 12 else False,
            "schedule_time": row[13] if len(row) > 13 else None,
            "last_run": row[14] if len(row) > 14 else None,
            "resource_checks": ", ".join(resource_checks)
        })
    return tasks

def get_inspection_task(task_id: int):
    """获取单个巡检任务"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM inspection_tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row[0],
            "name": row[1],
            "project_name": row[2],
            "inspector": row[3],
            "report_format": row[4],
            "resource_group_id": row[5],
            "check_cpu": bool(row[6]),
            "check_mem": bool(row[7]),
            "check_disk": bool(row[8]),
            "enable_proxy": bool(row[9]),
            "proxy_rules": json.loads(row[10]) if row[10] else [],
            "created_at": row[11],
            "enable_schedule": bool(row[12]) if len(row) > 12 else False,
            "schedule_time": row[13] if len(row) > 13 else None,
            "last_run": row[14] if len(row) > 14 else None
        }
    return None

def update_inspection_task(task_id: int, name: str, project_name: str, inspector: str, report_format: str = "excel",
                          resource_group_id=None, check_cpu=True, check_mem=True, check_disk=True,
                          enable_proxy=False, proxy_rules=None, enable_schedule=False, schedule_time=None):
    """更新巡检任务"""
    conn = get_conn()
    cur = conn.cursor()
    proxy_rules_json = json.dumps(proxy_rules or [])
    
    cur.execute("""
        UPDATE inspection_tasks SET name=?, project_name=?, inspector=?, report_format=?,
                                   resource_group_id=?, check_cpu=?, check_mem=?, check_disk=?,
                                   enable_proxy=?, proxy_rules=?, enable_schedule=?, schedule_time=?
        WHERE id=?
    """, (name, project_name, inspector, report_format,
          resource_group_id, 1 if check_cpu else 0, 1 if check_mem else 0, 1 if check_disk else 0,
          1 if enable_proxy else 0, proxy_rules_json, 1 if enable_schedule else 0, schedule_time, task_id))
    
    conn.commit()
    conn.close()

def toggle_task_schedule(task_id: int):
    """切换任务定时状态"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT enable_schedule FROM inspection_tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    if row:
        new_state = 0 if row[0] else 1
        cur.execute("UPDATE inspection_tasks SET enable_schedule = ? WHERE id = ?", (new_state, task_id))
        conn.commit()
    conn.close()

def update_task_last_run(task_id: int):
    """更新任务最后运行时间"""
    conn = get_conn()
    cur = conn.cursor()
    last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("UPDATE inspection_tasks SET last_run = ? WHERE id = ?", (last_run, task_id))
    conn.commit()
    conn.close()

def delete_inspection_task(task_id: int):
    """删除巡检任务"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM inspection_tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate_from_old_schema()
