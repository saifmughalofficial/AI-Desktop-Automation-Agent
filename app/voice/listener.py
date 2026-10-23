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
UNDO = re.compile(r"^(?:please\s+)?(?:undo|revert|roll ?back)(?:\s+(?:the|my))?(?:\s+(?:last|previous|latest))?"
                  r"(?:\s+(?:run|task|change|changes|action|actions|operation))?$", re.I)
STOP = re.compile(r"^(?:(?:emergency )?stop|abort|halt)(?: (?:it|now|everything|the run))?$", re.I)

# Frequent recognition slips for command words (spoken form -> intended word).
FIXES = [(r"\bnote ?pad\b|\bnot pad\b|\bnode pad\b", "notepad"), (r"\byou ?tube\b|\byou too\b", "youtube"),
         (r"\bg ?mail\b|\bgee mail\b", "gmail"), (r"\bwhat'?s ?app\b|\bwhats up\b", "whatsapp"),
         (r"\bcalculate (?:her|or)\b|\bcalculator\b", "calculator"), (r"\bfire ?fox\b", "firefox"),
         (r"\bgit ?hub\b", "github"), (r"\bscreen ?shot\b|\bscreens shot\b", "screenshot"),
         (r"\bmini ?mize\b", "minimize"), (r"\bmaxi ?mize\b", "maximize"), (r"\bdot com\b", ".com"),
         (r"\bopen up\b", "open"), (r"\bface ?book\b", "facebook"), (r"\binsta ?gram\b", "instagram"),
         (r"\blinked ?in\b", "linkedin"), (r"\bvs code\b|\bv s code\b|\bvisual studio code\b", "vs code"),
         (r"\bchrome browser\b", "chrome"), (r"\bmicro soft\b", "microsoft"), (r"\bdown loads\b", "downloads"),
         (r"\b(?:c ?p ?u|cp you|cb you|c b u|c p you|see p you|sea p you)\b", "cpu"),
         (r"\b(?:a )?(?:lo ?fi|low ?fi|lo-fi|low-fi|low-fee|low fee|lo fee|low v|lo vi|lo ve)\b", "lofi"),
         (r"\b(?:get ?hub|git ?hub|get the hub|good hub)\b", "github"), (r"^opens\b", "open"),
         (r"\bram\b|\bram usage\b", "ram"), (r"\bwi ?fi\b|\bwhy fi\b", "wifi"), (r"\bscreen shot\b", "screenshot"),
         (r"\bzoom in\b", "zoom in"), (r"\bdeep seek\b", "deepseek"), (r"\bchat gpt\b|\bchat g p t\b", "chatgpt"),
         (r"\b(go|switch|navigate|take me|bring me|move|copy|send it) (?:two|too)\b", r"\1 to"),
         (r"\btic ?tok\b|\btik ?tok\b", "tiktok"), (r"\bnet flicks\b|\bnet flix\b", "netflix")]


def normalize(text: str) -> str:
    t = " ".join((text or "").lower().split())
    for pat, rep in FIXES:
        t = re.sub(pat, rep, t)
    return re.sub(r"\s+\.com\b", ".com", t).strip()


# Words the command grammar always knows (the second, command-only recogniser).
BASE_VOCAB = """open launch start run close quit exit minimize maximize restore switch to focus show list find search look up
google bing youtube wikipedia amazon github maps images news web internet online for on in into from the a an my me
this that it these those all files file folder folders directory documents downloads desktop pictures photos music
videos projects demo reports create make new named called copy move rename delete remove zip compress organize sort
by type duplicates text note notes write draft compose email mail gmail outlook whatsapp message saying about subject
type inspect window windows tab tabs next previous reload refresh page website site browser chrome edge firefox
take screenshot screen capture what what's is are time date day today system status health cpu memory ram disk space
storage battery uptime network wifi internet processes top running volume up down mute unmute play pause track song
lock shutdown shut restart cancel stop yes no okay ok confirm help hello hi thanks thank you undo last preview
settings display sound bluetooth update notepad calculator paint wordpad character map explorer word excel powerpoint
code visual studio vs dot com org net in pk please now go history manual command center apps automation voice and then
one two three four five six seven eight nine ten twenty""".split()


def build_vocab(svc) -> list[str]:
    words = set(BASE_VOCAB)
    from app.actions import pc_control
    names = [a.name for a in svc.settings.apps] + list(pc_control.SITES)
    try:
        if svc.policy.desktop_available:
            names += pc_control.program_names()
        from app.core.workspace_index import WorkspaceIndex
        idx = WorkspaceIndex(svc.perms, max_entries=3000)
        names += [d.name for d in idx.dirs] + [f.name.rsplit(".", 1)[0] for f in idx.files] + svc.settings.root_aliases()
    except Exception:
        pass
    for n in names:
        words.update(w for w in re.split(r"[^a-z]+", n.lower()) if w)
    return sorted(words) + ["[unk]"]


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
        self._grammar = ""
        self._vocab: set[str] = set()
        self._peak = 0.0  # recent speech loudness, for automatic gain

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
        self.set_vocab(build_vocab(svc) if lang.startswith("en") else [])
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
            self._model, self._rate = model, rate
            utt = bytearray()

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
                    data = self._agc(data)
                    utt += data
                    if rec.AcceptWaveform(data):
                        result = json.loads(rec.Result())
                        result["grammar"] = self._grammar_decode(bytes(utt))
                        utt = bytearray()
                        self._final(result)
                    else:
                        self.partial = json.loads(rec.PartialResult()).get("partial", "")
                        if not self.partial and len(utt) > rate * 2 * 3:
                            utt = utt[-rate * 2:]  # keep the buffer short during silence
        except Exception as exc:  # report, never crash the app
            self.state, self.error = "error", f"{exc.__class__.__name__}: {exc}"
            self._say_log("system", f"Voice listener stopped: {self.error}")

    def set_vocab(self, words: list[str]) -> None:
        self._vocab = set(words)
        self._grammar = json.dumps(words) if words else ""

    def _agc(self, data: bytes) -> bytes:
        """Automatic gain: quiet laptop microphones are boosted (up to 8×) so the recogniser hears clear speech."""
        try:
            import numpy as np
            a = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            if not a.size:
                return data
            rms = float(np.sqrt(np.mean(a * a)))
            self._peak = max(rms, self._peak * 0.97)
            gain = min(8.0, max(1.0, 3500.0 / max(self._peak, 250.0)))
            out = np.clip(a * gain, -32768, 32767)
            self.level = float(min(1.0, rms * gain / 6000.0))
            return out.astype(np.int16).tobytes()
        except Exception:
            return data

    def _grammar_decode(self, pcm: bytes) -> str:
        """Second pass over the same utterance with a command-only vocabulary (much more accurate for commands)."""
        if not self._grammar or not pcm:
            return ""
        try:
            import vosk
            g = vosk.KaldiRecognizer(self._model, self._rate, self._grammar)
            g.AcceptWaveform(pcm)
            return json.loads(g.FinalResult()).get("text", "").strip()
        except Exception:
            return ""

    def decode(self, pcm: bytes, rate: int) -> list[str]:
        """Recognise one utterance (used by tests and by clip input): returns ordered candidate texts."""
        import vosk
        self._model, self._rate = stt._load(self.svc.voice_dir, self.lang), rate
        rec = vosk.KaldiRecognizer(self._model, rate)
        rec.SetMaxAlternatives(5)
        rec.AcceptWaveform(pcm)
        result = json.loads(rec.FinalResult())
        result["grammar"] = self._grammar_decode(pcm)
        return self.candidates(result)

    def candidates(self, result: dict) -> list[str]:
        alts = [a.get("text", "") for a in result.get("alternatives", [])] or [result.get("text", "")]
        alts = [a.strip() for a in alts if a and a.strip()]
        g = (result.get("grammar") or "").strip()
        vocab = getattr(self, "_vocab", set())
        free_is_free_text = bool(alts) and any(w not in vocab for w in alts[0].split())
        if g and g != "[unk]":
            if "[unk]" not in g and not free_is_free_text:
                alts.insert(0, g)  # only command words were spoken: the command-only pass is the most reliable
            elif "[unk]" not in g:
                alts.insert(1, g)
            else:
                alts.append(g.replace("[unk]", " ").strip())
        seen, out = set(), []
        for a in alts:
            a = " ".join(a.split())
            if a and a not in seen:
                seen.add(a)
                out.append(a)
        return out

    def _final(self, result: dict) -> None:
        self.partial = ""
        alts = self.candidates(result)
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

    FREE_TEXT = {"open_url", "compose_message", "type_text", "write_text_file", "list_files"}

    def _choose(self, alts: list[str]):
        """Pick the recognition alternative that forms a valid command (big accuracy win for short commands).

        Among valid candidates, one made only of known command/app/folder words wins over one containing an
        unknown word ("minimize crow" loses to "minimize chrome") — unless the command carries free text
        (a search query, a message, typed text), where unknown words are expected."""
        va = VoiceAssistant(self.svc.system, self.lang)
        vocab = self._vocab
        valid, best = [], None
        for raw in alts[:6]:
            text = normalize(raw) if self.lang.startswith("en") else raw
            known = not vocab or all(w in vocab for w in re.findall(r"[a-z]+", text))
            reply = va.handle(text)
            if reply.kind != "agent":
                valid.append((known, True, (text, reply, None)))
                continue
            plan = self.svc.planner.plan(reply.target or text)
            if plan.executable or plan.blocked_reason:
                free = any(s.action.action in self.FREE_TEXT for s in plan.steps)
                valid.append((known, free, (text, reply, plan)))
            elif best is None or (plan.clarification and plan.clarification != UNKNOWN_MSG
                                  and best[2].clarification == UNKNOWN_MSG):
                best = (text, reply, plan)
        if valid:
            for known, free, cand in valid:
                if known or (free and cand is valid[0][2]):
                    return cand
            return valid[0][2]
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
                if plan == "undo":
                    self.speak(self.svc.orchestrator.undo_last().get("message", "Done."))
                else:
                    self._run(plan)
                return
            if NO.match(top):
                self.pending = None
                self._say_log("you", top)
                self.speak("Okay, cancelled.")
                return
        undo = next((normalize(a) for a in alts if UNDO.match(normalize(a))), None)
        if undo:
            self._say_log("you", undo)
            self.pending = ("undo", time.monotonic() + 30)
            self.speak("Undo the last run that changed files? Say yes or no.")
            self.state = "waiting_yes"
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
