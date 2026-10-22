"""System manager policy + voice assistant routing. Nothing here ends real processes or powers off."""
import os

import pytest

from app.core.system_manager import SystemManager
from app.voice.assistant import VoiceAssistant


@pytest.fixture
def local_sm(monkeypatch):
    sm = SystemManager(hosted=False)
    monkeypatch.setattr("app.core.system_manager.IS_WINDOWS", True)
    calls = []
    monkeypatch.setattr(SystemManager, "_run", staticmethod(lambda argv: (calls.append(argv) or (True, ""))))
    sm.calls = calls
    return sm


def test_read_only_views_work_everywhere():
    sm = SystemManager(hosted=True)
    assert sm.info()["Environment"].startswith("Cloud")
    assert sm.processes() and sm.partitions() and "interfaces" in sm.network()
    assert sm.health()["ok"] and 0 <= sm.health()["score"] <= 100
    assert sm.top("mem_mb", 3)


def test_hosted_blocks_every_control():
    sm = SystemManager(hosted=True)
    assert not sm.check_terminate(os.getpid()).allowed
    assert sm.check_power("shutdown").risk == "BLOCKED"
    assert not sm.media_key("mute")[0] and not sm.open_settings("display")[0]


def test_protects_self_parent_and_critical(local_sm):
    assert not local_sm.check_terminate(os.getpid()).allowed
    assert not local_sm.check_terminate(os.getppid()).allowed
    assert not local_sm.check_terminate(4).allowed
    assert not local_sm.check_terminate(99999999).allowed  # no such process


def test_power_uses_fixed_argv_without_shell(local_sm):
    assert local_sm.check_power("shutdown").risk == "HIGH"
    assert local_sm.check_power("format c:").risk == "BLOCKED"
    ok, _ = local_sm.power("restart")
    assert ok and local_sm.calls[-1][:4] == ["shutdown", "/r", "/t", "60"]
    local_sm.power("cancel")
    assert local_sm.calls[-1] == ["shutdown", "/a"]


def test_settings_allowlist(local_sm):
    assert not local_sm.open_settings("regedit")[0]


@pytest.mark.parametrize("text,kind", [
    ("hello", "answer"), ("what's the time", "answer"), ("system status", "answer"), ("cpu usage", "answer"),
    ("top processes", "answer"), ("battery", "answer"), ("go to history", "navigate"),
    ("open the files page", "navigate"), ("stop", "stop"), ("open notepad", "agent"),
    ("organize my downloads by type", "agent"), ("hey agent, how much memory", "answer"),
])
def test_voice_routing(text, kind):
    r = VoiceAssistant(SystemManager(hosted=True)).handle(text)
    assert r.kind == kind, (text, r)


def test_voice_never_kills_or_powers_off_directly(local_sm):
    va = VoiceAssistant(local_sm)
    r = va.handle("shut down the computer")
    assert r.kind == "confirm" and r.data["action"] == "shutdown" and not local_sm.calls
    r = va.handle("kill process python")  # the agent's own interpreter is protected
    assert r.kind != "confirm" or r.data["pid"] != os.getpid()


def test_voice_power_refused_when_hosted():
    r = VoiceAssistant(SystemManager(hosted=True)).handle("restart the pc")
    assert r.kind == "answer" and "can't" in r.say


def test_tts_and_stt_helpers(tmp_path):
    from app.voice import stt, tts
    assert not stt.model_ready(tmp_path)
    assert tts._clean("a\x00  b") == "a b"
    with pytest.raises(RuntimeError):
        stt.transcribe(b"", tmp_path)
