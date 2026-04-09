#!/usr/bin/env python3
"""syscheck: a small, read-only system health snapshot tool.

It collects a few common checks support teams repeatedly do by hand
(disk, memory, load, uptime, basic network) and prints them in one place.

- Standard library only
- Linux/macOS first, Windows best-effort
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def run_cmd(cmd: List[str], timeout: int = 5) -> Tuple[int, str]:
    """Run a command and return (returncode, output). Best-effort."""
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        return p.returncode, (p.stdout or "").strip()
    except Exception as e:
        return 127, f"{type(e).__name__}: {e}"


def bytes_to_gb(n: int) -> float:
    return round(n / (1024**3), 2)


def read_first_line(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.readline().strip()
    except Exception:
        return None


def get_uptime_seconds() -> Optional[int]:
    system = platform.system().lower()

    # Linux: /proc/uptime
    if system == "linux":
        try:
            with open("/proc/uptime", "r", encoding="utf-8") as f:
                secs = float(f.read().split()[0])
            return int(secs)
        except Exception:
            return None

    # macOS: sysctl kern.boottime
    if system == "darwin":
        rc, out = run_cmd(["sysctl", "-n", "kern.boottime"], timeout=5)
        if rc == 0 and out:
            # Example: { sec = 1700000000, usec = 0 } Wed Nov ...
            try:
                sec_part = out.split("sec =", 1)[1].split(",", 1)[0].strip()
                boot = int(sec_part)
                return int(time.time() - boot)
            except Exception:
                return None
        return None

    # Windows: best-effort via net statistics workstation
    if system == "windows":
        rc, out = run_cmd(["cmd", "/c", "net statistics workstation"], timeout=5)
        if rc == 0 and out:
            # Parse line starting with "Statistics since" (locale dependent).
            for line in out.splitlines():
                if "since" in line.lower():
                    # If parsing fails, return None.
                    try:
                        # Example: Statistics since 1/19/2026 10:23:45 AM
                        ts = line.split("since", 1)[1].strip()
                        # Try a couple common formats.
                        for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S"):
                            try:
                                dt = datetime.strptime(ts, fmt)
                                return int(time.time() - dt.replace(tzinfo=None).timestamp())
                            except Exception:
                                pass
                    except Exception:
                        return None
        return None

    return None


def get_loadavg() -> Optional[Tuple[float, float, float]]:
    try:
        return os.getloadavg()
    except Exception:
        return None


def get_memory_info() -> Dict[str, Any]:
    """Return memory usage with best-effort OS-specific methods."""
    system = platform.system().lower()

    if system == "linux":
        info: Dict[str, int] = {}
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(":")
                        val_kb = int(parts[1])
                        info[key] = val_kb
            total_kb = info.get("MemTotal", 0)
            avail_kb = info.get("MemAvailable", info.get("MemFree", 0))
            used_kb = max(total_kb - avail_kb, 0)
            return {
                "total_gb": round(total_kb / (1024**2), 2),
                "used_gb": round(used_kb / (1024**2), 2),
                "available_gb": round(avail_kb / (1024**2), 2),
            }
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    if system == "darwin":
        # vm_stat returns pages; page size usually 4096.
        rc, out = run_cmd(["vm_stat"], timeout=5)
        if rc != 0:
            return {"error": out}
        page_size = 4096
        for line in out.splitlines():
            if "page size of" in line.lower():
                try:
                    page_size = int(line.split("page size of", 1)[1].split("bytes", 1)[0].strip())
                except Exception:
                    pass
        stats: Dict[str, int] = {}
        for line in out.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                v = v.strip().rstrip(".")
                try:
                    stats[k.strip()] = int(v)
                except Exception:
                    pass
        # Approximate: used = active + wired + compressed; free = free
        used_pages = stats.get("Pages active", 0) + stats.get("Pages wired down", 0) + stats.get("Pages occupied by compressor", 0)
        free_pages = stats.get("Pages free", 0)
        # Total is hard to infer accurately from vm_stat; use sysctl hw.memsize
        rc2, out2 = run_cmd(["sysctl", "-n", "hw.memsize"], timeout=5)
        if rc2 == 0 and out2.isdigit():
            total_bytes = int(out2)
            return {
                "total_gb": bytes_to_gb(total_bytes),
                "used_gb": round((used_pages * page_size) / (1024**3), 2),
                "available_gb": round((free_pages * page_size) / (1024**3), 2),
            }
        return {
            "used_gb": round((used_pages * page_size) / (1024**3), 2),
            "available_gb": round((free_pages * page_size) / (1024**3), 2),
        }

    if system == "windows":
        # WMIC may be deprecated but still available on many systems.
        rc, out = run_cmd(["cmd", "/c", "wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /value"], timeout=5)
        if rc != 0:
            return {"error": out}
        vals: Dict[str, int] = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                if v.strip().isdigit():
                    vals[k.strip()] = int(v.strip())
        total_kb = vals.get("TotalVisibleMemorySize", 0)
        free_kb = vals.get("FreePhysicalMemory", 0)
        used_kb = max(total_kb - free_kb, 0)
        return {
            "total_gb": round(total_kb / (1024**2), 2),
            "used_gb": round(used_kb / (1024**2), 2),
            "available_gb": round(free_kb / (1024**2), 2),
        }

    return {}


def get_disk_info(paths: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in paths:
        try:
            usage = shutil.disk_usage(p)
            out.append({
                "path": p,
                "total_gb": bytes_to_gb(usage.total),
                "used_gb": bytes_to_gb(usage.used),
                "free_gb": bytes_to_gb(usage.free),
                "percent_used": round((usage.used / usage.total) * 100, 1) if usage.total else None,
            })
        except Exception as e:
            out.append({"path": p, "error": f"{type(e).__name__}: {e}"})
    return out


def get_dns_check(hostname: str) -> Dict[str, Any]:
    try:
        ip = socket.gethostbyname(hostname)
        return {"hostname": hostname, "resolved_ip": ip}
    except Exception as e:
        return {"hostname": hostname, "error": f"{type(e).__name__}: {e}"}


def get_ping_check(target: str) -> Dict[str, Any]:
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "1", target]
    else:
        cmd = ["ping", "-c", "1", target]
    rc, out = run_cmd(cmd, timeout=5)
    return {"target": target, "ok": rc == 0, "output": out.splitlines()[-1] if out else ""}


def get_top_processes() -> Dict[str, Any]:
    system = platform.system().lower()
    if system == "linux":
        cmd = ["bash", "-lc", "ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -n 6"]
    elif system == "darwin":
        cmd = ["bash", "-lc", "ps -Arc -o pid,comm,%cpu,%mem | head -n 6"]
    else:
        return {"note": "top process snapshot not supported on this OS"}

    rc, out = run_cmd(cmd, timeout=5)
    if rc != 0:
        return {"error": out}
    return {"lines": out.splitlines()}


def build_report(dns_host: str, ping_target: str, disk_paths: List[str]) -> Dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "uptime_seconds": get_uptime_seconds(),
        "loadavg": get_loadavg(),
        "memory": get_memory_info(),
        "disks": get_disk_info(disk_paths),
        "network": {
            "dns": get_dns_check(dns_host),
            "ping": get_ping_check(ping_target),
        },
        "top_processes": get_top_processes(),
    }


def format_text(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    p = report.get("platform", {})
    lines.append(f"syscheck @ {report.get('timestamp')}")
    lines.append(f"OS: {p.get('system')} {p.get('release')} ({p.get('machine')})")
    lines.append(f"Python: {p.get('python')}")

    up = report.get("uptime_seconds")
    if isinstance(up, int):
        hours = up // 3600
        minutes = (up % 3600) // 60
        lines.append(f"Uptime: {hours}h {minutes}m")

    la = report.get("loadavg")
    if la:
        lines.append(f"Loadavg (1/5/15): {la[0]:.2f} {la[1]:.2f} {la[2]:.2f}")

    mem = report.get("memory", {})
    if mem:
        if "error" in mem:
            lines.append(f"Memory: ERROR - {mem['error']}")
        else:
            lines.append(f"Memory (GB): total {mem.get('total_gb')} | used {mem.get('used_gb')} | avail {mem.get('available_gb')}")

    lines.append("Disk:")
    for d in report.get("disks", []):
        if "error" in d:
            lines.append(f"  {d['path']}: ERROR - {d['error']}")
        else:
            lines.append(f"  {d['path']}: {d['used_gb']}/{d['total_gb']} GB used ({d.get('percent_used')}%)")

    net = report.get("network", {})
    dns = net.get("dns", {})
    ping = net.get("ping", {})
    if "error" in dns:
        lines.append(f"DNS: {dns.get('hostname')} -> ERROR - {dns.get('error')}")
    else:
        lines.append(f"DNS: {dns.get('hostname')} -> {dns.get('resolved_ip')}")
    lines.append(f"Ping: {ping.get('target')} -> {'OK' if ping.get('ok') else 'FAIL'}")

    tp = report.get("top_processes", {})
    if "lines" in tp:
        lines.append("Top processes (CPU):")
        lines.extend([f"  {ln}" for ln in tp["lines"]])

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Quick system health snapshot")
    ap.add_argument("--dns", default="one.one.one.one", help="Hostname to resolve (default: one.one.one.one)")
    ap.add_argument("--ping", default="1.1.1.1", help="Ping target (default: 1.1.1.1)")
    ap.add_argument(
        "--disk",
        action="append",
        default=None,
        help="Disk path to check (repeatable). Default is OS root.",
    )
    ap.add_argument("--json", default=None, help="Write full report as JSON to this file")
    return ap.parse_args()


def main() -> int:
    args = parse_args()

    if args.disk:
        disk_paths = args.disk
    else:
        disk_paths = ["C:\\"] if platform.system().lower() == "windows" else ["/"]

    report = build_report(args.dns, args.ping, disk_paths)
    print(format_text(report))

    if args.json:
        try:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
        except Exception as e:
            print(f"\nERROR: could not write JSON report: {type(e).__name__}: {e}", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
