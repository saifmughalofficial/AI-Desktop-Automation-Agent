"""Offline speech-to-text with Vosk (free, runs on this machine — no audio leaves it).

Each language's model (30–320 MB) is downloaded once from alphacephei.com into the
agent's data folder, or you can point VOSK_MODEL at an unpacked English model folder.
Urdu uses the Hindi (Hindustani) model and the text is converted to Urdu script."""
from __future__ import annotations

import io
import json
import os
import shutil
import threading
import urllib.request
import wave
import zipfile
from pathlib import Path

from app.voice.i18n import deva_to_urdu, lang_info

MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_BASE = "https://alphacephei.com/vosk/models/"
# Faster mirror (same files) — tried first; the official server is used as the fallback.
MIRRORS = {"vosk-model-en-us-0.22-lgraph": "https://huggingface.co/rhasspy/vosk-models/resolve/main/en/",
           "vosk-model-small-en-us-0.15": "https://huggingface.co/rhasspy/vosk-models/resolve/main/en/"}
_lock = threading.Lock()
_models: dict = {}

try:
    import vosk  # type: ignore
    vosk.SetLogLevel(-1)
except Exception:  # pragma: no cover - optional dependency
    vosk = None


def engine_available() -> bool:
    return vosk is not None


def model_name(lang: str = "en") -> str:
    return lang_info(lang)["model"]


def model_dir(data_dir: Path, lang: str = "en") -> Path:
    env = os.environ.get("VOSK_MODEL")
    if env and lang == "en":
        return Path(env)
    return Path(data_dir) / "models" / model_name(lang)


def model_ready(data_dir: Path, lang: str = "en") -> bool:
    d = model_dir(data_dir, lang)
    return (d / "am").is_dir() or (d / "conf").is_dir()


def download_model(data_dir: Path, progress=None, lang: str = "en") -> Path:
    """One-time download + unpack. Only fixed official model URLs from the language table are fetched."""
    dest = model_dir(data_dir, lang)
    if model_ready(data_dir, lang):
        return dest
    name = model_name(lang)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / (name + ".zip.part")
    bases = [b for b in (MIRRORS.get(name), MODEL_BASE) if b]
    for i, base in enumerate(bases):
        try:
            with urllib.request.urlopen(base + name + ".zip", timeout=60) as r, open(tmp, "wb") as f:  # noqa: S310
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                while chunk := r.read(1 << 16):
                    f.write(chunk)
                    done += len(chunk)
                    if progress and total:
                        progress(done / total)
            break
        except OSError:
            if i == len(bases) - 1:
                raise
    with zipfile.ZipFile(tmp) as z:
        for m in z.namelist():  # zip-slip guard
            if Path(m).is_absolute() or ".." in Path(m).parts:
                raise ValueError("Unsafe path in model archive")
        z.extractall(dest.parent)
    tmp.unlink(missing_ok=True)
    if not model_ready(data_dir, lang):
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError("Model archive did not contain the expected files")
    return dest


def _load(data_dir: Path, lang: str):
    key = str(model_dir(data_dir, lang))
    with _lock:
        if key not in _models:
            _models[key] = vosk.Model(key)
        return _models[key]


def _pcm16_mono(wav_bytes: bytes) -> tuple[bytes, int]:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        frames = w.readframes(w.getnframes())
    if width != 2 or ch != 1:
        import numpy as np
        dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[width]
        a = np.frombuffer(frames, dtype=dtype).astype(np.float32)
        if width == 1:
            a = (a - 128) * 256
        elif width == 4:
            a = a / 65536
        if ch > 1:
            a = a.reshape(-1, ch).mean(axis=1)
        frames = np.clip(a, -32768, 32767).astype(np.int16).tobytes()
    return frames, rate


def transcribe(wav_bytes: bytes, data_dir: Path, lang: str = "en") -> str:
    if vosk is None:
        raise RuntimeError("Vosk is not installed (pip install vosk).")
    if not model_ready(data_dir, lang):
        raise RuntimeError("The offline speech model is not downloaded yet.")
    pcm, rate = _pcm16_mono(wav_bytes)
    rec = vosk.KaldiRecognizer(_load(data_dir, lang), rate)
    for i in range(0, len(pcm), 8000):
        rec.AcceptWaveform(pcm[i:i + 8000])
    text = json.loads(rec.FinalResult()).get("text", "").strip()
    if lang in {"zh", "ja"}:
        text = text.replace(" ", "")
    if lang == "ur":
        text = deva_to_urdu(text)
    return text
