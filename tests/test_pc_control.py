"""Browser/web, drafts, programs, windows, tabs, screenshots and parser accuracy.
Runs in hosted mode (web virtual desktop) — nothing opens on the real desktop."""
import pytest
from pydantic import ValidationError

from app.actions import pc_control
from app.core import action_schema as A
from app.core.system_manager import SystemManager
from app.voice.assistant import VoiceAssistant


def plan(svc, text):
    return svc.planner.plan(text)


def run(svc, text):
    p = plan(svc, text)
    assert p.executable, (text, p.clarification, p.blocked_reason, p.violations)
    return svc.orchestrator.submit(p, approved=True, background=False)


@pytest.mark.parametrize("text,action,check", [
    ("search YouTube for lofi music", "open_url", lambda a: "youtube.com/results?search_query=lofi+music" in a.url),
    ("google weather in Lahore", "open_url", lambda a: "q=weather+in+Lahore" in a.url),
    ("look up python on wikipedia", "open_url", lambda a: "wikipedia" in a.url),
    ("open github.com in Chrome", "open_url", lambda a: a.url == "https://github.com" and a.browser == "chrome"),
    ("go to youtube", "open_url", lambda a: a.url == "https://www.youtube.com"),
    ("visit https://streamlit.io/gallery", "open_url", lambda a: a.url.endswith("/gallery")),
    ("draft a gmail to a@b.com about Meeting saying See you at 5", "compose_message",
     lambda a: a.channel == "gmail" and a.to == "a@b.com" and a.subject == "Meeting" and a.body == "See you at 5"),
    ("draft a whatsapp message to +923001234567 saying hello", "compose_message",
     lambda a: a.channel == "whatsapp" and a.body == "hello"),
    ("minimize chrome", "window_control", lambda a: a.op == "minimize" and a.window == "chrome"),
    ("switch to the notepad window", "window_control", lambda a: a.op == "focus"),
    ("close notepad", "window_control", lambda a: a.op == "close"),
    ("list open windows", "list_windows", lambda a: True),
    ("what's open", "list_windows", lambda a: True),
    ("open a new tab in edge", "browser_tab", lambda a: a.op == "new" and a.browser == "edge"),
    ("close this tab", "browser_tab", lambda a: a.op == "close"),
    ("take a screenshot into Photos", "take_screenshot", lambda a: a.destination.display().endswith("Photos")),
])
def test_new_phrasings(svc, text, action, check):
    p = plan(svc, text)
    assert p.steps and p.steps[0].action.action == action, (text, p.clarification, p.blocked_reason)
    assert check(p.steps[0].action)


def test_typo_and_fuzzy_names(svc):
    p = plan(svc, "opne notpad")
    assert p.steps[0].action.action == "launch_app" and p.steps[0].action.app == "Notepad"
    assert any("opne" in x for x in p.assumptions) and any("notpad" in x for x in p.assumptions)
    p = plan(svc, "lsit files in Downlods")
    assert p.steps[0].action.target.display().endswith("Downloads")
    p = plan(svc, "open roadmapp.txt")
    assert p.clarification and "roadmap.txt" in p.clarification  # did-you-mean, never a silent guess on files


def test_refusals(svc):
    for text in ["sign in to my facebook", "log me into gmail", "send a whatsapp message to Ali", "type my password"]:
        p = plan(svc, text)
        assert p.blocked_reason and not p.steps, text
    assert "draft" in plan(svc, "send an email to boss").blocked_reason.lower()


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///C:/Windows", "https://user:pw@evil.com/",
                                 "https://x.com/setup.exe", "ftp://x.com", "https://exa mple.com"])
def test_url_validation(url):
    with pytest.raises(ValidationError):
        A.OpenUrl(url=url)


def test_compose_validation_and_urls():
    with pytest.raises(ValidationError):
        A.ComposeMessage(channel="gmail", to="not-an-email", body="x")
    with pytest.raises(ValidationError):
        A.ComposeMessage(channel="whatsapp", to="abc", body="x")
    with pytest.raises(ValidationError):
        A.ComposeMessage(channel="email", body="")
    assert pc_control.compose_url("whatsapp", "+92 300 1234567", "", "hi there") == "https://wa.me/923001234567?text=hi%20there"
    assert pc_control.compose_url("email", "a@b.com", "S", "B").startswith("mailto:a@b.com?subject=S")
    assert "mail.google.com" in pc_control.compose_url("gmail", "", "", "x")


def test_hosted_runs_use_web_windows(svc):
    st = run(svc, "search google for streamlit")
    assert st.status == "completed"
    st = run(svc, "draft an outlook email to a@b.com saying hello")
    vd = svc.orchestrator.virtual
    links = [w for w in vd.windows.values() if w["kind"] == "link"]
    assert len(links) == 2 and links[-1]["draft"]["body"] == "hello"
    st = run(svc, "list open windows")
    assert len(st.steps[0].details["rows"]) == 2
    st = run(svc, f"close the {links[0]['title']} window")
    assert st.status == "completed" and len(vd.windows) == 1


def test_hosted_blocks_real_desktop_only_actions(svc):
    for text in ["take a screenshot", "open a new tab", "open vs code"]:
        p = plan(svc, text)
        assert not p.executable, text


def test_find_program_matching():
    names = ["Google Chrome", "Visual Studio Code", "Word", "WordPad", "Microsoft Edge", "Spotify"]
    assert pc_control.find_program("chrome", names)[0] == "Google Chrome"
    assert pc_control.find_program("vs code", names)[0] == "Visual Studio Code"
    assert pc_control.find_program("word", names)[0] == "Word"
    assert pc_control.find_program("spotifi", names)[0] == "Spotify"
    assert pc_control.find_program("zzz", names)[0] is None


def test_voice_close_goes_to_agent_not_kill():
    r = VoiceAssistant(SystemManager(hosted=True)).handle("close notepad")
    assert r.kind == "agent"


def test_default_browser_is_chrome_new_tab(monkeypatch):
    calls = []
    monkeypatch.setattr(pc_control, "browser_exe", lambda b: f"C:/{b}.exe" if b in {"chrome", "firefox"} else None)
    monkeypatch.setattr(pc_control.subprocess, "Popen", lambda args, **kw: calls.append(args))
    monkeypatch.setattr(pc_control.webbrowser, "open_new_tab", lambda url: calls.append(["system", url]) or True)
    ok, msg = pc_control.open_url("https://x.com", "default", "chrome")
    assert ok and calls[-1] == ["C:/chrome.exe", "https://x.com"] and "new Chrome tab" in msg
    pc_control.open_url("https://x.com", "firefox", "chrome")
    assert calls[-1] == ["C:/firefox.exe", "-new-tab", "https://x.com"]
    ok, msg = pc_control.open_url("https://x.com", "default", "edge")  # preferred browser missing -> system default tab
    assert ok and calls[-1] == ["system", "https://x.com"] and "not installed" in msg
    ok, _ = pc_control.open_url("https://x.com", "edge", "chrome")  # explicitly named but missing -> honest failure
    assert not ok


def test_web_browser_setting_default(svc):
    assert svc.settings.web_browser == "chrome"
    assert "new tab" in svc.planner.plan("open youtube.com").steps[0].description
