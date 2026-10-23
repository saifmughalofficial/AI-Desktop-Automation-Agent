"""Hands-free voice decisions (no microphone needed: recognised phrases are fed in directly)."""
import pytest

from app.voice.listener import VoiceListener, normalize


@pytest.fixture
def lis(svc):
    new = svc.settings.model_copy(deep=True)
    new.voice_speak = False
    svc.apply_settings(new, save=False)
    v = VoiceListener()
    v.svc, v.lang = svc, "en"
    return v


def said(v):
    return [m["text"] for m in v.log if m["who"] == "agent"]


def test_normalize_common_slips():
    assert normalize("Open Note Pad") == "open notepad"
    assert normalize("search you tube for music") == "search youtube for music"
    assert normalize("open github dot com") == "open github.com"


def test_low_risk_runs_immediately_without_clicks(lis, svc):
    lis.handle(["open notepad"])
    assert lis.current_run is not None and lis.current_run.status == "completed"
    assert svc.orchestrator.virtual.latest("notepad")


def test_picks_the_alternative_that_is_a_valid_command(lis):
    lis.handle(["open note bad", "open notepad"])
    assert lis.current_run and lis.current_run.status == "completed"


def test_medium_risk_waits_for_spoken_yes(lis, svc):
    lis.handle(["create a text file named todo in Projects with text 'hi'"])
    assert lis.pending and lis.current_run is None and "yes or no" in said(lis)[-1]
    lis.handle(["yes"])
    assert lis.pending is None and lis.current_run.status == "completed"


def test_medium_risk_cancelled_by_no(lis):
    lis.handle(["create a text file named todo2 in Projects with text 'hi'"])
    lis.handle(["no"])
    assert lis.pending is None and lis.current_run is None


def test_high_risk_never_runs_by_voice(lis):
    lis.handle(["delete notes.txt in Downloads"])
    assert lis.current_run is None and lis.pending is None and "on screen" in said(lis)[-1]


def test_background_chatter_is_ignored_silently(lis):
    lis.handle(["the weather was lovely yesterday at the beach"])
    assert lis.current_run is None and not said(lis)
    assert any(m["who"] == "ignored" for m in lis.log)


def test_system_question_answered(lis):
    lis.handle(["what time is it"])
    assert said(lis) and said(lis)[-1].startswith("It's")


def test_refusals_spoken(lis):
    lis.handle(["sign in to my facebook"])
    assert "never signs in" in said(lis)[-1]
