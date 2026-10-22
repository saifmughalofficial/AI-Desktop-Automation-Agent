"""Live system metrics for the HUD (CPU, memory, disk, network) via psutil."""
from __future__ import annotations

import time
from collections import deque
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is in requirements
    psutil = None


class SystemMonitor:
    def __init__(self, history: int = 40):
        self.cpu: deque[float] = deque(maxlen=history)
        self.mem: deque[float] = deque(maxlen=history)
        self.net: deque[float] = deque(maxlen=history)  # KB/s
        self._last: dict | None = None
        self._cache: tuple[float, dict] | None = None
        if psutil:
            psutil.cpu_percent(interval=None)  # prime the counter

    @property
    def available(self) -> bool:
        return psutil is not None

    def sample(self, disk_path: Path | str, min_interval: float = 0.9) -> dict:
        now = time.monotonic()
        if self._cache and now - self._cache[0] < min_interval:
            return self._cache[1]
        if not psutil:
            data = {"ok": False}
            self._cache = (now, data)
            return data
        cpu = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        try:
            du = psutil.disk_usage(str(disk_path))
        except OSError:
            du = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        try:
            dio = psutil.disk_io_counters()
        except Exception:  # some containers expose no disk counters
            dio = None
        cur = {"t": now, "net": (net.bytes_sent + net.bytes_recv) if net else 0,
               "r": dio.read_bytes if dio else 0, "w": dio.write_bytes if dio else 0}
        rate_net = rate_r = rate_w = 0.0
        if self._last:
            dt = max(cur["t"] - self._last["t"], 1e-3)
            rate_net = max(cur["net"] - self._last["net"], 0) / dt / 1024
            rate_r = max(cur["r"] - self._last["r"], 0) / dt
            rate_w = max(cur["w"] - self._last["w"], 0) / dt
        self._last = cur
        self.cpu.append(cpu)
        self.mem.append(vm.percent)
        self.net.append(rate_net)
        data = {
            "ok": True, "cpu": cpu, "mem": vm.percent, "mem_used": vm.used, "mem_total": vm.total,
            "disk": du.percent, "disk_used": du.used, "disk_total": du.total, "net_kbs": rate_net,
            "read_bs": rate_r, "write_bs": rate_w, "cores": psutil.cpu_count(logical=True) or 1,
            "procs": len(psutil.pids()), "uptime_h": (time.time() - psutil.boot_time()) / 3600,
        }
        self._cache = (now, data)
        return data
