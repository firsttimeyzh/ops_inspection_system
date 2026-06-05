# -*- coding: utf-8 -*-
import paramiko, re, time
from typing import Dict, Any

def run_cmd(ssh, cmd: str, timeout: int = 15) -> str:
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "ignore").strip()
    err = stderr.read().decode("utf-8", "ignore").strip()
    return out or err

def parse_cpu(output: str) -> float:
    # Try to match "Cpu(s): 12.3%us,  3.4%sy, ..." from top -bn1
    m = re.search(r"Cpu\(s\).*?(\d+\.?\d*)\%id", output)
    if m:
        idle = float(m.group(1))
        return round(100.0 - idle, 2)
    m2 = re.search(r"(\d+\.?\d*)\%us", output)
    if m2:
        # crude fallback: user% as proxy
        return float(m2.group(1))
    return 0.0

def parse_mem(output: str) -> float:
    # from `free -m`: Mem:  16095  1024  345 ...
    lines = output.splitlines()
    for line in lines:
        if line.lower().startswith("mem:"):
            parts = [p for p in line.split() if p]
            if len(parts) >= 3:
                total = float(parts[1])
                used = float(parts[2])
                return round(used / total * 100.0, 2)
    return 0.0

def parse_disk(output: str) -> float:
    # from `df -P /` : Use% in the 5th column
    lines = output.splitlines()
    for line in lines[1:]:
        parts = [p for p in line.split() if p]
        if len(parts) >= 5 and parts[5] in ("/", "/root", "/home"):
            usep = parts[4]
            if usep.endswith("%"):
                return float(usep[:-1])
    # fallback: take the max percentage
    maxp = 0.0
    for line in lines[1:]:
        parts = [p for p in line.split() if p]
        if len(parts) >= 5 and parts[4].endswith("%"):
            try:
                maxp = max(maxp, float(parts[4][:-1]))
            except:
                pass
    return maxp

def inspect_server(ip: str, port: int, username: str, password: str, timeout: int = 10, check_cpu: bool = True, check_mem: bool = True, check_disk: bool = True) -> Dict[str, Any]:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    res = {
        "ip": ip,
        "uptime": "",
        "cpu": 0.0,
        "mem": 0.0,
        "disk": 0.0,
        "ok": False,
        "error": ""
    }
    try:
        ssh.connect(ip, port=port, username=username, password=password, timeout=timeout)
        # uptime - 仅保留前2块
        uptime = run_cmd(ssh, "uptime -p || cat /proc/uptime")
        uptime_str = uptime.replace("\n", " ").strip()
        # 解析 uptime -p 格式 (如 "up 2 days, 3 hours, 45 minutes")
        if uptime_str.startswith("up "):
            parts = uptime_str[3:].split(", ")
            if len(parts) >= 2:
                uptime_str = ", ".join(parts[:2])
            elif len(parts) == 1:
                uptime_str = parts[0]
        res["uptime"] = uptime_str

        # cpu
        if check_cpu:
            cpu_out = run_cmd(ssh, "LANG=C top -bn1 | grep Cpu || mpstat | grep all || sar -u 1 1 | grep Average")
            res["cpu"] = parse_cpu(cpu_out)

        # mem
        if check_mem:
            mem_out = run_cmd(ssh, "free -m")
            res["mem"] = parse_mem(mem_out)

        # disk (root mount)
        if check_disk:
            disk_out = run_cmd(ssh, "df -P /")
            res["disk"] = parse_disk(disk_out)

        res["ok"] = True
    except Exception as e:
        res["error"] = str(e)
    finally:
        try:
            ssh.close()
        except Exception:
            pass
    return res

def test_proxy(ip: str, port: int, username: str, password: str, curl_cmd: str, success_keyword: str, timeout: int = 30) -> Dict[str, Any]:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    res = {
        "ip": ip,
        "success": False,
        "output": "",
        "error": ""
    }
    try:
        ssh.connect(ip, port=port, username=username, password=password, timeout=timeout)
        output = run_cmd(ssh, curl_cmd, timeout=timeout)
        res["output"] = output
        
        if success_keyword in output:
            res["success"] = True
        
    except Exception as e:
        res["error"] = str(e)
    finally:
        try:
            ssh.close()
        except Exception:
            pass
    return res
