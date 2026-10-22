"""Voice/chat assistant intent router (deterministic, offline, multilingual).

It answers system questions itself, runs harmless controls, and turns risky
requests into a *confirmation* the user must click. Everything else is handed
to the normal agent planner, so voice commands get the same policy checks,
approval dialog and audit trail as typed ones. Speech text is only ever
matched with regular expressions / keyword tables — never executed.

Non-English speech is first mapped to a canonical English command with the
native keyword tables in ``i18n``; replies are rendered in the chosen language."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from app.core.system_manager import MEDIA_KEYS, SETTINGS_PAGES, SystemManager
from app.voice import i18n

PAGES = {"command center": "command", "command": "command", "home": "command", "dashboard": "command",
         "files": "files", "file explorer": "files", "explorer": "files", "apps": "apps", "automation": "apps",
         "history": "history", "activity": "history", "settings": "settings", "manual": "manual", "help page": "manual",
         "system": "system", "system manager": "system", "processes": "system", "voice": "voice"}

HELP = ("Try: “system status”, “CPU usage”, “top processes”, “battery”, “disk space”, “volume up”, "
        "“mute”, “open display settings”, “close Notepad process”, “lock the screen”, “go to history”, "
        "or any agent task like “open Notepad” or “organize my Downloads by type”.")


@dataclass
class Reply:
    say: str
    kind: str = "answer"  # answer | agent | navigate | confirm | stop | action
    target: str | None = None
    data: dict = field(default_factory=dict)
    heard: str = ""  # canonical English command the speech was mapped to (non-English input)


class VoiceAssistant:
    def __init__(self, system: SystemManager, lang: str = "en"):
        self.sys = system
        self.lang = lang if lang in i18n.LANGS else "en"

    def _t(self, key: str, **kw) -> str:
        return i18n.t(key, self.lang, help=HELP, **kw)

    def handle(self, text: str) -> Reply:
        raw = (text or "").strip()
        canon = ""
        if not self.lang.startswith("en") and raw:
            canon = i18n.to_command(raw, self.lang) or ""
            if not canon:
                if re.search(r"[a-z]{3}", raw.lower()) and raw.isascii():
                    canon = raw  # an English command spoken/typed while another language is selected
                else:
                    return Reply(self._t("agent_other", text=raw), "agent", target=raw)
        t = " ".join((canon or raw).lower().replace("’", "'").split()).strip(" .!?")
        t = re.sub(r"^(hey |ok |okay )?(agent|assistant|computer)[, ]+", "", t)
        t = re.sub(r"^(please |can you |could you |would you )+", "", t).removesuffix(" please")
        if not t:
            return Reply(self._t("didnt_catch"))
        for fn in (self._smalltalk, self._stop, self._navigate, self._media, self._settings, self._power,
                   self._terminate, self._status):
            r = fn(t)
            if r:
                r.heard = canon if canon != raw else ""
                return r
        target = canon or raw
        return Reply(self._t("agent", text=target) if self.lang.startswith("en") else
                     self._t("agent_other", text=raw), "agent", target=target, heard=canon if canon != raw else "")

    # ------------------------------------------------------------------ intents
    def _smalltalk(self, t: str) -> Reply | None:
        if re.fullmatch(r"(hi|hello|hey|good (morning|afternoon|evening)|salam|assalam ?o ?alaikum)( there)?", t):
            return Reply(self._t("hello"))
        if re.search(r"\b(help|what can you do|commands)\b", t):
            return Reply(HELP if self.lang.startswith("en") else self._t("hello"))
        if re.search(r"\b(who are you|your name)\b", t):
            return Reply(self._t("who"))
        if re.search(r"\bwhat('s| is)? (the )?time\b|^time$", t):
            return Reply(self._t("time", time=datetime.now().strftime("%I:%M %p").lstrip("0")))
        if re.search(r"\b(what('s| is)? (the )?date|today's date|what day)\b", t):
            fmt = "%A, %d %B %Y" if self.lang.startswith("en") else "%d-%m-%Y"
            return Reply(self._t("date", date=datetime.now().strftime(fmt)))
        if re.fullmatch(r"(thanks|thank you|thx)( so much)?", t):
            return Reply(self._t("thanks"))
        return None

    def _stop(self, t: str) -> Reply | None:
        if re.fullmatch(r"(emergency )?stop( the run| everything| now)?|abort( the run)?|cancel (the )?run", t):
            return Reply(self._t("stop"), "stop")
        return None

    def _navigate(self, t: str) -> Reply | None:
        m = re.fullmatch(r"(?:go to|open|show(?: me)?|switch to|navigate to|take me to) (?:the )?(.+?)"
                         r"(?: page| tab| screen| section)", t) or \
            re.fullmatch(r"(?:go to|switch to|navigate to|take me to) (?:the )?(.+)", t)
        if m and m.group(1).strip() in PAGES:
            name = m.group(1).strip()
            return Reply(self._t("navigate", page=name), "navigate", target=PAGES[name])
        return None

    def _media(self, t: str) -> Reply | None:
        m = re.fullmatch(r"(?:turn (?:the )?)?volume (up|down)(?: by (\d+))?|(?:turn )?(up|down) (?:the )?volume|"
                         r"(un)?mute(?: the)?(?: sound| audio| volume)?|(play|pause|resume)(?: the)?(?: music| media)?|"
                         r"(next|previous|last) (?:track|song)", t)
        if not m:
            return None
        if m.group(1) or m.group(3):
            key, n = f"volume {m.group(1) or m.group(3)}", int(m.group(2) or 5)
        elif t.startswith(("mute", "unmute")):
            key, n = "mute", 1
        elif m.group(6):
            key, n = ("next track" if m.group(6) == "next" else "previous track"), 1
        else:
            key, n = "play/pause", 1
        ok, msg = self.sys.media_key(key, n)
        return Reply(self._t("done", msg=msg) if ok else self._t("cant", reason=msg), "action")

    def _settings(self, t: str) -> Reply | None:
        m = re.fullmatch(r"(?:open|show|go to) (?:the )?(?:windows )?(.+?) settings", t)
        if not m:
            return None
        page = {"wifi": "wi-fi", "update": "windows update", "updates": "windows update", "sleep": "power",
                "time": "date and time", "sound and volume": "sound"}.get(m.group(1), m.group(1))
        if page not in SETTINGS_PAGES:
            return Reply(f"I can open these settings pages: {', '.join(sorted(SETTINGS_PAGES))}.")
        ok, msg = self.sys.open_settings(page)
        return Reply(self._t("done", msg=msg) if ok else self._t("cant", reason=msg), "action")

    def _power(self, t: str) -> Reply | None:
        action = None
        if re.search(r"\bcancel (the )?(shut ?down|restart|reboot)\b|\babort shut ?down\b", t):
            action = "cancel"
        elif re.search(r"\block (the |my )?(screen|computer|pc|laptop|windows)\b|^lock$", t):
            action = "lock"
        elif re.search(r"\b(shut ?down|turn off|power off) (the |my )?(computer|pc|laptop|system)\b|^shut ?down$", t):
            action = "shutdown"
        elif re.search(r"\b(restart|reboot)( the| my)?( computer| pc| laptop| system)?$", t):
            action = "restart"
        if not action:
            return None
        d = self.sys.check_power(action)
        if not d.allowed:
            return Reply(self._t("cant", reason=d.reason))
        if action == "cancel":
            ok, msg = self.sys.power("cancel")
            return Reply(self._t("done", msg=msg) if ok else msg, "action")
        return Reply(self._t("confirm_power", reason=d.reason), "confirm",
                     data={"op": "power", "action": action, "risk": d.risk})

    def _terminate(self, t: str) -> Reply | None:
        m = re.fullmatch(r"(?:close|end|kill|terminate|stop|quit|force (?:close|quit|kill))(?: the)?"
                         r"(?: process(?:es)?| app| program| task)? (.+?)(?: process(?:es)?| app| program| task)?", t)
        if not m or t.startswith(("stop the run", "stop everything")):
            return None
        name = m.group(1).strip()
        procs = self.sys.find(name) if name and len(name) > 1 else []
        if not procs:
            return None if not re.search(r"\b(process|task)\b", t) else Reply(self._t("no_proc", name=name))
        p = sorted(procs, key=lambda r: r["mem_mb"], reverse=True)[0]
        d = self.sys.check_terminate(p["pid"])
        if not d.allowed:
            return Reply(self._t("refuse_kill", name=p["name"], reason=d.reason))
        return Reply(self._t("confirm_kill", name=p["name"], pid=p["pid"]), "confirm",
                     data={"op": "terminate", "pid": p["pid"], "name": p["name"], "risk": d.risk,
                           "force": t.startswith("force")})

    def _status(self, t: str) -> Reply | None:
        s = self.sys
        if re.search(r"\b(top|heaviest|biggest) (\d+ )?(process|processes|apps)\b|what('s| is) using (my )?"
                     r"(cpu|memory|ram)|\b(list|show)( running)? processes\b", t):
            by = "mem_mb" if re.search(r"memory|ram", t) else "cpu"
            top = s.top(by, 5)
            if not top:
                return Reply(self._t("cant", reason="Process list unavailable."))
            items = ", ".join(f"{p['name']} {p['mem_mb']:.0f} MB" if by == "mem_mb" else f"{p['name']} {p['cpu']:.0f}%"
                              for p in top)
            return Reply(self._t("top", by="memory" if by == "mem_mb" else "CPU", items=items), data={"top": top})
        h = s.health()
        if not h.get("ok"):
            return None
        if re.search(r"\b(cpu|processor)\b", t):
            return Reply(self._t("cpu", v=f"{h['cpu']:.0f}"))
        if re.search(r"\b(memory|ram)\b", t):
            return Reply(self._t("mem", v=f"{h['mem']:.0f}", free=h["mem_free"]))
        if re.search(r"\b(disk|storage|space|drive)\b", t):
            parts = s.partitions()
            txt = "; ".join(f"{p['drive']} {p['free']} free of {p['total']}" for p in parts[:4]) or f"{h['disk']:.0f}%"
            return Reply(self._t("disk", txt=txt))
        if re.search(r"\bbattery|charge|charging\b", t):
            b = h["battery"]
            if not b:
                return Reply(self._t("no_battery"))
            return Reply(self._t("battery", v=f"{b['percent']:.0f}",
                                 state=self._t("plugged" if b["plugged"] else "on_battery")))
        if re.search(r"\buptime|how long\b.*\b(on|running|up)\b", t):
            return Reply(self._t("uptime", up=h["uptime"]))
        if re.search(r"\b(network|internet|ip address|wi-?fi|connection)\b", t):
            ifs = [i for i in s.network()["interfaces"] if i["up"] and i["ipv4"] and not i["ipv4"].startswith("127.")]
            return Reply(self._t("net", txt=", ".join(f"{i['interface']} {i['ipv4']}" for i in ifs[:3]))
                         if ifs else self._t("no_net"))
        if re.search(r"\b(system|pc|computer|health|status|report|performance)\b", t):
            return Reply(self._t("status", score=h["score"], cpu=f"{h['cpu']:.0f}", mem=f"{h['mem']:.0f}",
                                 disk=f"{h['disk']:.0f}", up=h["uptime"]))
        return None


__all__ = ["Reply", "VoiceAssistant", "PAGES", "HELP", "MEDIA_KEYS"]
