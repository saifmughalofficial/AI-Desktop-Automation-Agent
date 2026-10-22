"""Whole-system management: processes, disks, network, services, startup items,
Windows settings shortcuts, media/volume keys and power actions.

Safety model (same rules as the file/app agent):
* Read-only views work everywhere (on the hosted website they show the cloud container).
* Anything that changes the PC runs only locally on Windows, is checked by
  ``check_*`` policy functions here (never by the UI or the voice model), needs an
  explicit confirmation in the UI, and is recorded in the SQLite history.
* Commands are fixed argument lists run without a shell; no text from speech or
  a model is ever executed.
* Critical system processes, other users' processes and the agent itself are never ended.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.runtime import IS_WINDOWS

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is in requirements
    psutil = None

PROTECTED = {
    "system", "system idle process", "idle", "registry", "memory compression", "secure system", "smss.exe",
    "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "lsaiso.exe", "svchost.exe",
    "dwm.exe", "fontdrvhost.exe", "explorer.exe", "spoolsv.exe", "msmpeng.exe", "nissrv.exe",
    "securityhealthservice.exe", "securityhealthsystray.exe", "sihost.exe", "ctfmon.exe", "audiodg.exe",
    "conhost.exe", "taskhostw.exe", "runtimebroker.exe", "searchindexer.exe", "wudfhost.exe", "dllhost.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe", "textinputhost.exe", "lsm.exe", "wlanext.exe",
    "init", "systemd", "launchd", "kthreadd", "kernel_task",
}

POWER_LABELS = {"lock": "Lock the screen", "shutdown": "Shut down in 60 seconds",
                "restart": "Restart in 60 seconds", "cancel": "Cancel a scheduled shutdown/restart"}
POWER_RISK = {"lock": "LOW", "cancel": "LOW", "shutdown": "HIGH", "restart": "HIGH"}
_SHUTDOWN_NOTE = "Scheduled by AI Desktop Automation Agent. Use Cancel in the System page or run: shutdown /a"

# Fixed allowlist of Windows Settings pages (ms-settings: URIs).
SETTINGS_PAGES = {
    "display": "ms-settings:display", "sound": "ms-settings:sound", "bluetooth": "ms-settings:bluetooth",
    "wi-fi": "ms-settings:network-wifi", "network": "ms-settings:network-status", "windows update": "ms-settings:windowsupdate",
    "apps": "ms-settings:appsfeatures", "storage": "ms-settings:storagesense", "power": "ms-settings:powersleep",
    "battery": "ms-settings:batterysaver", "notifications": "ms-settings:notifications", "privacy": "ms-settings:privacy",
    "date and time": "ms-settings:dateandtime", "personalization": "ms-settings:personalization",
    "mouse": "ms-settings:mousetouchpad", "keyboard": "ms-settings:keyboard", "about": "ms-settings:about",
}

# Virtual-key codes for media keys (simulated key presses — no drivers, no elevation).
MEDIA_KEYS = {"volume up": 0xAF, "volume down": 0xAE, "mute": 0xAD, "play/pause": 0xB3,
              "next track": 0xB0, "previous track": 0xB1}


@dataclass
class Decision:
    allowed: bool
    risk: str
    reason: str


def _size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in {"B", "KB"} else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class SystemManager:
    def __init__(self, hosted: bool, db=None):
        self.hosted = hosted
        self.db = db
        self._me = os.getpid()
        self._protected_pids = {0, 4, self._me}
        if psutil:
            try:
                self._protected_pids |= {p.pid for p in psutil.Process(self._me).parents()}
            except Exception:
                pass
            for p in psutil.process_iter():  # prime per-process CPU counters
                try:
                    p.cpu_percent(None)
                except Exception:
                    pass

    # ------------------------------------------------------------------ capabilities
    @property
    def can_control(self) -> bool:
        """True only for a local Windows session — the website never changes anyone's PC."""
        return IS_WINDOWS and not self.hosted and psutil is not None

    def control_reason(self) -> str:
        if self.hosted:
            return "The hosted website runs in a cloud container and cannot control your PC. Run locally (run.bat)."
        if not IS_WINDOWS:
            return "System control actions are implemented for Windows."
        return "" if psutil else "psutil is not installed."

    # ------------------------------------------------------------------ read-only views
    def info(self) -> dict:
        d = {"Computer": platform.node(), "OS": f"{platform.system()} {platform.release()} ({platform.version()})",
             "Architecture": platform.machine(), "Processor": platform.processor() or platform.machine(),
             "Python": sys.version.split()[0], "Environment": "Cloud container (hosted)" if self.hosted else "Local PC"}
        if psutil:
            vm = psutil.virtual_memory()
            boot = datetime.fromtimestamp(psutil.boot_time())
            d.update({"CPU cores": f"{psutil.cpu_count(logical=False) or '?'} physical / {psutil.cpu_count()} logical",
                      "Memory": f"{_size(vm.total)} total, {_size(vm.available)} available",
                      "Boot time": boot.strftime("%Y-%m-%d %H:%M"), "Uptime": self.uptime_text(),
                      "Processes": str(len(psutil.pids()))})
            try:
                f = psutil.cpu_freq()
                if f:
                    d["CPU frequency"] = f"{f.current:.0f} MHz (max {f.max:.0f})"
            except Exception:
                pass
        return d

    def uptime_text(self) -> str:
        if not psutil:
            return "unknown"
        secs = int(time.time() - psutil.boot_time())
        h, m = divmod(secs // 60, 60)
        d, h = divmod(h, 24)
        return (f"{d} day(s) " if d else "") + f"{h} h {m} min"

    def battery(self) -> dict | None:
        try:
            b = psutil.sensors_battery() if psutil else None
        except Exception:
            b = None
        if b is None:
            return None
        left = None
        if b.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) and b.secsleft > 0:
            left = f"{b.secsleft // 3600} h {(b.secsleft % 3600) // 60} min"
        return {"percent": b.percent, "plugged": bool(b.power_plugged), "left": left}

    def per_core(self) -> list[float]:
        return psutil.cpu_percent(percpu=True, interval=None) if psutil else []

    def processes(self) -> list[dict]:
        if not psutil:
            return []
        rows = []
        cores = psutil.cpu_count() or 1
        for p in psutil.process_iter(["pid", "name", "username", "memory_info", "status", "create_time"]):
            try:
                i = p.info
                mem = i["memory_info"].rss if i["memory_info"] else 0
                rows.append({"pid": i["pid"], "name": i["name"] or "?", "cpu": round(p.cpu_percent(None) / cores, 1),
                             "mem_mb": round(mem / 1048576, 1), "status": i["status"] or "",
                             "user": (i["username"] or "").split("\\")[-1],
                             "started": datetime.fromtimestamp(i["create_time"]).strftime("%H:%M:%S")
                             if i["create_time"] else ""})
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, ValueError):
                continue
        return rows

    def top(self, by: str = "cpu", n: int = 5) -> list[dict]:
        rows = [r for r in self.processes() if r["name"].lower() not in {"system idle process", "idle"}]
        return sorted(rows, key=lambda r: r[by], reverse=True)[:n]

    def find(self, name: str) -> list[dict]:
        q = name.strip().lower().removesuffix(".exe")
        return [r for r in self.processes() if r["name"].lower().removesuffix(".exe") == q] or \
               [r for r in self.processes() if q and q in r["name"].lower()]

    def partitions(self) -> list[dict]:
        rows = []
        if not psutil:
            return rows
        for part in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(part.mountpoint)
            except (OSError, PermissionError):
                continue
            rows.append({"drive": part.device or part.mountpoint, "mount": part.mountpoint, "fs": part.fstype,
                         "total": _size(u.total), "used": _size(u.used), "free": _size(u.free), "used_pct": u.percent})
        return rows

    def network(self) -> dict:
        if not psutil:
            return {"interfaces": [], "connections": {}}
        stats, io = psutil.net_if_stats(), psutil.net_io_counters(pernic=True)
        ifs = []
        for name, addrs in psutil.net_if_addrs().items():
            ipv4 = next((a.address for a in addrs if getattr(a.family, "name", "") == "AF_INET"), "")
            st_ = stats.get(name)
            c = io.get(name)
            ifs.append({"interface": name, "up": bool(st_ and st_.isup), "ipv4": ipv4,
                        "speed_mbps": st_.speed if st_ else 0, "sent": _size(c.bytes_sent) if c else "-",
                        "received": _size(c.bytes_recv) if c else "-"})
        conns: dict[str, int] = {}
        try:
            for c in psutil.net_connections(kind="inet"):
                conns[c.status] = conns.get(c.status, 0) + 1
        except (psutil.AccessDenied, OSError):
            conns = {"(needs admin to list)": 0}
        return {"interfaces": sorted(ifs, key=lambda r: (not r["up"], r["interface"])), "connections": conns}

    def services(self) -> list[dict]:
        if not (psutil and IS_WINDOWS and hasattr(psutil, "win_service_iter")):
            return []
        rows = []
        for s in psutil.win_service_iter():
            try:
                d = s.as_dict()
                rows.append({"name": d["name"], "display_name": d["display_name"], "status": d["status"],
                             "start_type": d["start_type"]})
            except Exception:
                continue
        return rows

    def startup_items(self) -> list[dict]:
        rows: list[dict] = []
        if not IS_WINDOWS:
            return rows
        import winreg
        for hive, hname in ((winreg.HKEY_CURRENT_USER, "Current user"), (winreg.HKEY_LOCAL_MACHINE, "All users")):
            try:
                with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                    for i in range(winreg.QueryInfoKey(k)[1]):
                        n, v, _ = winreg.EnumValue(k, i)
                        rows.append({"name": n, "scope": hname, "source": "Registry Run key", "command": str(v)[:180]})
            except OSError:
                continue
        folder = Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"
        if folder.is_dir():
            rows += [{"name": f.stem, "scope": "Current user", "source": "Startup folder", "command": f.name}
                     for f in folder.iterdir() if f.name.lower() != "desktop.ini"]
        return rows

    def temp_usage(self, limit: int = 20000) -> dict:
        root = Path(tempfile.gettempdir())
        total = count = 0
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                try:
                    total += os.stat(os.path.join(dirpath, f)).st_size
                except OSError:
                    continue
                count += 1
                if count >= limit:
                    return {"path": str(root), "size": _size(total), "files": f"{count}+"}
        return {"path": str(root), "size": _size(total), "files": str(count)}

    def health(self) -> dict:
        """One-shot summary used by the voice assistant and the health score."""
        if not psutil:
            return {"ok": False}
        cpu = psutil.cpu_percent(interval=0.3)
        vm = psutil.virtual_memory()
        try:
            disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\" if IS_WINDOWS else "/").percent
        except OSError:
            disk = psutil.disk_usage("/").percent
        score = max(0, round(100 - max(0, cpu - 50) * .6 - max(0, vm.percent - 60) * .8 - max(0, disk - 75) * 1.2))
        return {"ok": True, "cpu": cpu, "mem": vm.percent, "disk": disk, "score": score,
                "mem_free": _size(vm.available), "battery": self.battery(), "uptime": self.uptime_text()}

    # ------------------------------------------------------------------ policy
    def check_terminate(self, pid: int) -> Decision:
        if not self.can_control:
            return Decision(False, "BLOCKED", self.control_reason())
        if pid in self._protected_pids:
            return Decision(False, "BLOCKED", "The agent will not end itself, its parent, or a core kernel process.")
        try:
            p = psutil.Process(pid)
            name = (p.name() or "").lower()
            user = p.username() or ""
        except psutil.NoSuchProcess:
            return Decision(False, "BLOCKED", f"No process with PID {pid} is running.")
        except psutil.AccessDenied:
            return Decision(False, "BLOCKED", "Access denied — it belongs to the system or an administrator. "
                                              "The agent never elevates its privileges.")
        if name in PROTECTED:
            return Decision(False, "BLOCKED", f"{name} is a protected Windows process; ending it could crash or "
                                              "lock the PC.")
        me = psutil.Process(self._me).username() or ""
        if user and me and user.lower() != me.lower():
            return Decision(False, "BLOCKED", f"{name} runs under another account ({user}).")
        return Decision(True, "MEDIUM", f"Ending {name} closes it immediately — unsaved work in it will be lost.")

    def check_power(self, action: str) -> Decision:
        if action not in POWER_LABELS:
            return Decision(False, "BLOCKED", f"Unknown power action '{action}'.")
        if not self.can_control:
            return Decision(False, "BLOCKED", self.control_reason())
        risk = POWER_RISK[action]
        why = {"lock": "Locks Windows; sign in again to continue.",
               "cancel": "Aborts a pending shutdown or restart.",
               "shutdown": "Windows shows a 60-second warning; save your work. You can cancel it here.",
               "restart": "Windows shows a 60-second warning; save your work. You can cancel it here."}[action]
        return Decision(True, risk, why)

    def check_simple(self) -> Decision:
        if not self.can_control:
            return Decision(False, "BLOCKED", self.control_reason())
        return Decision(True, "LOW", "Harmless, reversible control.")

    # ------------------------------------------------------------------ actions (call only after check + confirm)
    def _record(self, request: str, risk: str, ok: bool, msg: str) -> None:
        if self.db is not None:
            tid = self.db.create_task(request=request, summary=msg, engine="system", risk=risk,
                                      status="completed" if ok else "failed", approval="approved", dry_run=False,
                                      step_count=1)
            self.db.add_action(tid, step_index=0, action_type="system", target=request, risk=risk,
                               status="success" if ok else "failed", verified=ok, message=msg)

    @staticmethod
    def _run(argv: list[str]) -> tuple[bool, str]:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            r = subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=15, creationflags=flags)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)
        return r.returncode == 0, (r.stderr or r.stdout or "").strip()

    def terminate(self, pid: int, force: bool = False) -> tuple[bool, str]:
        d = self.check_terminate(pid)
        if not d.allowed:
            return False, d.reason
        p = psutil.Process(pid)
        name = p.name()
        try:
            p.kill() if force else p.terminate()
            _gone, alive = psutil.wait_procs([p], timeout=5)
        except psutil.NoSuchProcess:
            alive = []
        except psutil.AccessDenied:
            return False, "Access denied by Windows."
        ok = not alive
        msg = (f"{'Force-ended' if force else 'Ended'} {name} (PID {pid}) — verified it is no longer running."
               if ok else f"{name} (PID {pid}) is still running. You can try Force end.")
        self._record(f"End process {name} (PID {pid}){' [force]' if force else ''}", "HIGH" if force else "MEDIUM", ok, msg)
        return ok, msg

    def power(self, action: str) -> tuple[bool, str]:
        d = self.check_power(action)
        if not d.allowed:
            return False, d.reason
        argv = {"lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
                "shutdown": ["shutdown", "/s", "/t", "60", "/c", _SHUTDOWN_NOTE],
                "restart": ["shutdown", "/r", "/t", "60", "/c", _SHUTDOWN_NOTE],
                "cancel": ["shutdown", "/a"]}[action]
        ok, out = self._run(argv)
        msg = f"{POWER_LABELS[action]}: {'done' if ok else 'failed'}" + (f" ({out})" if out and not ok else "")
        if action == "cancel" and not ok:
            msg = "No shutdown or restart was scheduled."
        self._record(f"Power: {POWER_LABELS[action]}", d.risk, ok, msg)
        return ok, msg

    def media_key(self, name: str, times: int = 1) -> tuple[bool, str]:
        d = self.check_simple()
        if not d.allowed:
            return False, d.reason
        vk = MEDIA_KEYS.get(name)
        if vk is None:
            return False, f"Unknown media control '{name}'."
        import ctypes
        for _ in range(max(1, min(times, 25))):
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
        return True, f"{name.capitalize()}" + (f" ×{times}" if times > 1 else "") + "."

    def open_settings(self, page: str) -> tuple[bool, str]:
        d = self.check_simple()
        if not d.allowed:
            return False, d.reason
        uri = SETTINGS_PAGES.get(page.lower())
        if not uri:
            return False, f"'{page}' is not in the Windows Settings allowlist."
        try:
            os.startfile(uri)  # type: ignore[attr-defined]
        except OSError as exc:
            return False, f"Could not open Settings: {exc}"
        return True, f"Opened Windows Settings → {page.title()}."
