"""Always-on, hands-free voice mode (local PC only, pure Python).

The PC microphone is read with ``sounddevice`` and recognised offline by Vosk —
no browser, no clicks, no audio leaves the machine. Each finished phrase is:

* matched against the assistant's system intents (status, volume, time, …), or
* planned by the normal agent planner and checked by the policy engine.

The *policy engine* still decides risk: LOW-risk plans run immediately; MEDIUM
plans are read out and run only after you say "yes"; HIGH-risk plans (deletes,
shutdown …) are never run by voice — approve them on screen. Replies are spoken
through the PC speakers (the mic is muted while the agent talks)."""
from __future__ import annotations

import json
import queue
import re
import threading
import time
from collections import deque
from datetime import datetime

from app.core.action_schema import Risk
from app.llm.rules_fallback import UNKNOWN_MSG
from app.runtime import IS_WINDOWS
from app.voice import i18n, stt, tts
from app.voice.assistant import VoiceAssistant

try:
    import sounddevice as sd
except Exception:  # pragma: no cover - optional / no PortAudio on servers
    sd = None

YES = re.compile(r"^(?:yes|yeah|yep|yup|ok|okay|sure|confirm|confirmed|do it|go ahead|proceed|run it|haan|han|ji|jee|"
                 r"ہاں|جی|हाँ|हां|जी|oui|sí|si|ja|да|evet|نعم|是)\b", re.I)
NO = re.compile(r"^(?:no|nope|cancel|stop|don'?t|do not|never ?mind|nahi|nahin|نہیں|नहीं|non|nein|нет|hayır|لا|不)\b", re.I)
STOP = re.compile(r"^(?:(?:emergency )?stop|abort|halt)(?: (?:it|now|everything|the run))?$", re.I)

# Frequent recognition slips for command words (spoken form -> intended word).
FIXES = [(r"\bnote ?pad\b|\bnot pad\b|\bnode pad\b", "notepad"), (r"\byou ?tube\b|\byou too\b", "youtube"),
         (r"\bg ?mail\b|\bgee mail\b", "gmail"), (r"\bwhat'?s ?app\b|\bwhats up\b", "whatsapp"),
         (r"\bcalculate (?:her|or)\b|\bcalculator\b", "calculator"), (r"\bfire ?fox\b", "firefox"),
         (r"\bgit ?hub\b", "github"), (r"\bscreen ?shot\b|\bscreens shot\b", "screenshot"),
         (r"\bmini ?mize\b", "minimize"), (r"\bmaxi ?mize\b", "maximize"), (r"\bdot com\b", ".com"),
         (r"\bopen up\b", "open"), (r"\bface ?book\b", "facebook"), (r"\binsta ?gram\b", "instagram"),
         (r"\blinked ?in\b", "linkedin"), (r"\bvs code\b|\bv s code\b|\bvisual studio code\b", "vs code"),
         (r"\bchrome browser\b", "chrome"), (r"\bmicro soft\b", "microsoft"), (r"\bdown loads\b", "downloads")]


def normalize(text: str) -> str:
    t = " ".join((text or "").lower().split())
    for pat, rep in FIXES:
        t = re.sub(pat, rep, t)
    return re.sub(r"\s+\.com\b", ".com", t).strip()


def available() -> tuple[bool, str]:
    if sd is None:
        return False, "The 'sounddevice' package is not installed (pip install sounddevice)."
    if not stt.engine_available():
        return False, "The offline speech engine (vosk) is not installed."
    try:
        sd.query_devices(kind="input")
    except Exception:
        return False, "No microphone was found on this PC."
    return True, "ok"


class VoiceListener:
    def __init__(self):
        self.svc = None
        self.lang = "en"
        self.state = "off"  # off | listening | thinking | speaking | waiting_yes | error
        self.error = ""
        self.partial = ""
        self.level = 0.0
        self.log: deque = deque(maxlen=60)
        self.pending = None  # (plan, deadline) awaiting a spoken yes/no
        self.current_run = None
        self.nav_request: str | None = None
        self._stop = threading.Event()
        self._mic: queue.Queue = queue.Queue(maxsize=200)
        self._jobs: queue.Queue = queue.Queue()
        self._speaking = threading.Event()
        self._threads: list[threading.Thread] = []

    # ------------------------------------------------------------------ lifecycle
    @property
    def running(self) -> bool:
        return any(t.is_alive() for t in self._threads)

    def start(self, svc, lang: str) -> tuple[bool, str]:
        ok, why = available()
        if not ok:
            return False, why
        if not stt.model_ready(svc.voice_dir, lang):
            return False, f"Download the {i18n.lang_info(lang)['name']} speech model first (Voice Assistant page)."
        if self.running and self.lang == lang and self.svc is svc:
            return True, "already listening"
        self.stop()
        self.svc, self.lang, self.error = svc, lang, ""
        self._stop.clear()
        self._threads = [threading.Thread(target=self._mic_loop, name="voice-mic", daemon=True),
                         threading.Thread(target=self._job_loop, name="voice-jobs", daemon=True)]
        for t in self._threads:
            t.start()
        self._say_log("system", f"Hands-free voice on ({i18n.lang_info(lang)['name']}). Just speak a command.")
        return True, "listening"

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=2)
        self._threads = []
        self.state, self.partial, self.level, self.pending = "off", "", 0.0, None

    # ------------------------------------------------------------------ helpers
    def _say_log(self, who: str, text: str) -> None:
        self.log.append({"t": datetime.now().strftime("%H:%M:%S"), "who": who, "text": text})

    def speak(self, text: str) -> None:
        self._say_log("agent", text)
        settings = self.svc.settings if self.svc else None
        if settings is not None and not settings.voice_speak:
            return
        audio = tts.synthesize(text, 1, self.lang)
        if not audio or not IS_WINDOWS:
            return
        import winsound
        prev, self.state = self.state, "speaking"
        self._speaking.set()
        try:
            winsound.PlaySound(audio, winsound.SND_MEMORY)
        except Exception:
            pass
        finally:
            time.sleep(0.25)
            with self._mic.mutex:  # drop anything the mic heard while we were talking
                self._mic.queue.clear()
            self._speaking.clear()
            self.state = prev if prev != "speaking" else "listening"

    # ------------------------------------------------------------------ microphone + recognition
    def _mic_loop(self) -> None:
        try:
            import vosk
            model = stt._load(self.svc.voice_dir, self.lang)
            rate = 16000
            try:
                sd.check_input_settings(samplerate=rate, channels=1, dtype="int16")
            except Exception:
                rate = int(sd.query_devices(kind="input")["default_samplerate"])
            rec = vosk.KaldiRecognizer(model, rate)
            rec.SetMaxAlternatives(5)
            rec.SetWords(False)

            def callback(indata, frames, _time, status):
                if not self._speaking.is_set():
                    try:
                        self._mic.put_nowait(bytes(indata))
                    except queue.Full:
                        pass

            with sd.RawInputStream(samplerate=rate, blocksize=rate // 4, dtype="int16", channels=1, callback=callback):
                self.state = "listening"
                while not self._stop.is_set():
                    try:
                        data = self._mic.get(timeout=0.3)
                    except queue.Empty:
                        continue
                    self._update_level(data)
                    if rec.AcceptWaveform(data):
                        self._final(json.loads(rec.Result()))
                    else:
                        self.partial = json.loads(rec.PartialResult()).get("partial", "")
        except Exception as exc:  # report, never crash the app
            self.state, self.error = "error", f"{exc.__class__.__name__}: {exc}"
            self._say_log("system", f"Voice listener stopped: {self.error}")

    def _update_level(self, data: bytes) -> None:
        try:
            import numpy as np
            a = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            self.level = float(min(1.0, (np.sqrt(np.mean(a * a)) / 6000.0))) if a.size else 0.0
        except Exception:
            pass

    def _final(self, result: dict) -> None:
        self.partial = ""
        alts = [a.get("text", "") for a in result.get("alternatives", [])] or [result.get("text", "")]
        alts = [a.strip() for a in alts if a and a.strip()]
        if not alts:
            return
        if self.lang == "ur":
            alts = [i18n.deva_to_urdu(a) for a in alts]
        if self.lang in {"zh", "ja"}:
            alts = [a.replace(" ", "") for a in alts]
        top = normalize(alts[0])
        if STOP.match(top):  # handled right here so it can interrupt a running task
            self._emergency_stop()
            return
        self._jobs.put(alts)

    def _emergency_stop(self) -> None:
        self._say_log("you", "stop")
        run = self.current_run
        if run is not None and not run.done:
            self.svc.orchestrator.stop(run)
            self.speak("Stopped.")
        elif self.pending:
            self.pending = None
            self.speak("Cancelled.")

    # ------------------------------------------------------------------ understanding + acting
    def _job_loop(self) -> None:
        while not self._stop.is_set():
            try:
                alts = self._jobs.get(timeout=0.4)
            except queue.Empty:
                if self.pending and time.monotonic() > self.pending[1]:
                    self.pending = None
                    self._say_log("system", "Confirmation timed out — nothing was run.")
                continue
            try:
                self.state = "thinking"
                self.handle(alts)
            except Exception as exc:
                self._say_log("system", f"Error: {exc.__class__.__name__}: {exc}")
            finally:
                if self.state == "thinking":
                    self.state = "waiting_yes" if self.pending else "listening"

    def _choose(self, alts: list[str]):
        """Pick the recognition alternative that forms a valid command (big accuracy win for short commands)."""
        va = VoiceAssistant(self.svc.system, self.lang)
        best = None
        for raw in alts:
            text = normalize(raw) if self.lang.startswith("en") else raw
            reply = va.handle(text)
            if reply.kind != "agent":
                return text, reply, None
            plan = self.svc.planner.plan(reply.target or text)
            if plan.executable or plan.blocked_reason:
                return text, reply, plan
            if best is None or (plan.clarification and plan.clarification != UNKNOWN_MSG and best[2].clarification == UNKNOWN_MSG):
                best = (text, reply, plan)
        return best

    def handle(self, alts: list[str]) -> None:
        if isinstance(alts, str):
            alts = [alts]
        top = normalize(alts[0]) if self.lang.startswith("en") else alts[0]
        if self.pending:
            plan, _ = self.pending
            if YES.match(top):
                self.pending = None
                self._say_log("you", top)
                self._run(plan)
                return
            if NO.match(top):
                self.pending = None
                self._say_log("you", top)
                self.speak("Okay, cancelled.")
                return
        chosen = self._choose(alts)
        if chosen is None:
            return
        text, reply, plan = chosen
        if plan is None:  # assistant intent (status, time, volume, …)
            self._say_log("you", text)
            if reply.kind == "confirm":
                self.speak(reply.say.split(" Press Confirm")[0] + " For safety, please confirm this on screen.")
            elif reply.kind == "stop":
                self._emergency_stop()
            elif reply.kind == "navigate":
                self.speak(reply.say)
                self.nav_request = reply.target
            else:
                self.speak(reply.say)
            return
        if plan.clarification == UNKNOWN_MSG and not plan.steps:
            self._say_log("ignored", text)  # background chatter — don't interrupt with errors
            return
        self._say_log("you", text)
        if plan.blocked_reason:
            self.speak(plan.blocked_reason)
        elif plan.clarification:
            self.speak(plan.clarification)
        elif not plan.executable:
            self.speak(plan.violations[0] if plan.violations else "I can't do that.")
        elif plan.risk == Risk.LOW and not plan.requires_approval:
            self._run(plan, announce=True)
        elif plan.risk == Risk.MEDIUM and self.svc.settings.voice_confirm_by_voice:
            self.pending = (plan, time.monotonic() + 30)
            what = plan.steps[0].description if len(plan.steps) == 1 else plan.summary
            self.speak(f"{what}. Should I do it? Say yes or no.")
            self.state = "waiting_yes"
        else:
            self.speak(f"That is a {plan.risk.value}-risk task: {plan.summary}. Please approve it on screen in the "
                       "Command Center.")

    def _run(self, plan, announce: bool = False) -> None:
        if announce:
            first = plan.steps[0].description
            self.speak(first if len(plan.steps) == 1 else f"{first}, and {len(plan.steps) - 1} more step(s).")
        state = self.svc.orchestrator.submit(plan, approved=True, background=True)
        self.current_run = state
        while not state.done and not self._stop.is_set():
            time.sleep(0.2)
        failed = [s for s in state.steps if s.status.value == "failed"]
        if failed:
            self.speak(f"That didn't work: {failed[0].message}")
        elif plan.steps and plan.steps[-1].action.action in {"list_files", "list_windows", "find_duplicates"}:
            self.speak(state.steps[-1].message)
        elif not announce:
            self.speak("Done.")


LISTENER = VoiceListener()
