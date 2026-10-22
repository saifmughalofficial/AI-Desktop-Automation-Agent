"""Offline text-to-speech to WAV bytes (played with st.audio).

* English on Windows: the built-in SAPI voices (comtypes, falling back to pyttsx3).
* Every language (and Linux/Cloud): the bundled espeak-ng library from the
  ``espeakng-loader`` wheel, driven through ctypes — no system install needed.
* Last resort on Linux: an ``espeak-ng`` binary called with a fixed argument list."""
from __future__ import annotations

import ctypes
import hashlib
import io
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

from app.runtime import IS_WINDOWS
from app.voice.i18n import lang_info

_lock = threading.Lock()
_cache: dict[str, bytes] = {}
_espeak = {"lib": None, "rate": 22050, "tried": False}


def _clean(text: str) -> str:
    return " ".join(text.replace("\x00", " ").split())[:600]


# ---------------------------------------------------------------- Windows SAPI (English voices)
def _sapi(text: str, out: Path, rate: int) -> bool:
    try:
        import comtypes
        import comtypes.client
        comtypes.CoInitialize()
        try:
            voice = comtypes.client.CreateObject("SAPI.SpVoice")
            stream = comtypes.client.CreateObject("SAPI.SpFileStream")
            stream.Open(str(out), 3)  # SSFMCreateForWrite
            voice.AudioOutputStream = stream
            voice.Rate = max(-10, min(10, rate))
            voice.Speak(text, 0)
            stream.Close()
        finally:
            comtypes.CoUninitialize()
        return out.exists() and out.stat().st_size > 100
    except Exception:
        pass
    try:
        import pyttsx3
        eng = pyttsx3.init()
        eng.save_to_file(text, str(out))
        eng.runAndWait()
        return out.exists() and out.stat().st_size > 100
    except Exception:
        return False


# ---------------------------------------------------------------- bundled espeak-ng (all languages)
_CB = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)
_samples: list[bytes] = []


@_CB
def _collect(wav, n, _events):
    if n > 0 and wav:
        _samples.append(ctypes.string_at(wav, n * 2))
    return 0


def _espeak_lib():
    if _espeak["tried"]:
        return _espeak["lib"]
    _espeak["tried"] = True
    try:
        import espeakng_loader
        lib = ctypes.cdll.LoadLibrary(espeakng_loader.get_library_path())
        data = str(Path(espeakng_loader.get_data_path()).parent)
        lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        rate = lib.espeak_Initialize(2, 0, data.encode(), 0)  # AUDIO_OUTPUT_SYNCHRONOUS
        if rate <= 0:
            return None
        lib.espeak_SetSynthCallback(_collect)
        lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
        lib.espeak_Synth.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint, ctypes.c_int, ctypes.c_uint,
                                     ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        _espeak.update(lib=lib, rate=rate)
    except Exception:
        _espeak["lib"] = None
    return _espeak["lib"]


def _espeak_wav(text: str, voice: str, rate: int) -> bytes | None:
    lib = _espeak_lib()
    if lib is None:
        return None
    if lib.espeak_SetVoiceByName(voice.encode()) != 0 and lib.espeak_SetVoiceByName(voice.split("-")[0].encode()) != 0:
        return None
    lib.espeak_SetParameter(1, 165 + rate * 12, 0)  # espeakRATE (words per minute)
    _samples.clear()
    raw = text.encode("utf-8")
    lib.espeak_Synth(raw, len(raw) + 1, 0, 1, 0, 1, None, None)  # POS_CHARACTER, espeakCHARS_UTF8
    lib.espeak_Synchronize()
    pcm = b"".join(_samples)
    if len(pcm) < 200:
        return None
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_espeak["rate"])
        w.writeframes(pcm)
    return buf.getvalue()


def _espeak_bin(text: str, voice: str, out: Path, rate: int) -> bool:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        return False
    try:
        subprocess.run([exe, "-v", voice, "-s", str(165 + rate * 12), "-w", str(out), "--", text], shell=False,
                       capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.exists() and out.stat().st_size > 100


def available(lang: str = "en") -> bool:
    if IS_WINDOWS and lang.startswith("en"):
        return True
    return _espeak_lib() is not None or bool(shutil.which("espeak-ng") or shutil.which("espeak"))


def synthesize(text: str, rate: int = 1, lang: str = "en") -> bytes | None:
    """Return WAV bytes for ``text`` in ``lang`` or None if no offline voice is available."""
    text = _clean(text)
    if not text:
        return None
    key = hashlib.sha1(f"{lang}|{rate}|{text}".encode()).hexdigest()
    if key in _cache:
        return _cache[key]
    voice = lang_info(lang)["voice"]
    data = None
    with _lock:
        if IS_WINDOWS and lang.startswith("en"):
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "say.wav"
                if _sapi(text, out, rate):
                    data = out.read_bytes()
        if data is None:
            data = _espeak_wav(text, voice, rate)
        if data is None and not IS_WINDOWS:
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "say.wav"
                if _espeak_bin(text, voice, out, rate):
                    data = out.read_bytes()
    if data is None:
        return None
    if len(_cache) > 64:
        _cache.clear()
    _cache[key] = data
    return data
