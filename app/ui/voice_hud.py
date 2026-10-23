"""Hands-free voice mode UI: auto-start, sidebar live indicator (every page) and the Voice page panel."""
from __future__ import annotations

import streamlit as st

from app.ui import components as C
from app.ui import state
from app.voice import i18n, listener, stt
from app.voice.listener import LISTENER

STATE_TEXT = {"listening": "Listening — just say a command", "thinking": "Working on it…", "speaking": "Speaking…",
              "waiting_yes": "Waiting for your “yes” or “no”…", "error": "Voice error", "off": "Voice off"}


def effective_lang(s) -> str:
    """The configured language, or the small English model while the high-accuracy one is not downloaded yet."""
    lang = s.settings.voice_lang
    if lang == "en-hq" and not stt.model_ready(s.voice_dir, lang) and stt.model_ready(s.voice_dir, "en"):
        return "en"
    return lang


def ensure() -> None:
    """Start the always-on listener when enabled (local PC only). Idempotent — safe on every rerun."""
    s = state.svc()
    if s.hosted or not s.settings.voice_handsfree:
        return
    lang = effective_lang(s)
    if LISTENER.running and (LISTENER.lang == lang or lang != s.settings.voice_lang):
        return
    if LISTENER.running and lang == s.settings.voice_lang and LISTENER.lang != lang:
        LISTENER.stop()  # the better model just finished downloading: switch to it
    if st.session_state.get("_voice_start_failed") == lang:
        return  # don't retry on every rerun after a failure (e.g. model not downloaded yet)
    ok, why = LISTENER.start(s, lang)
    if not ok:
        st.session_state._voice_start_failed = lang
        st.session_state._voice_start_error = why
    else:
        st.session_state.pop("_voice_start_failed", None)
        state.push_event("INFO", "Hands-free voice listening (offline).")


def set_handsfree(on: bool, lang: str | None = None) -> tuple[bool, str]:
    s = state.svc()
    new = s.settings.model_copy(deep=True)
    new.voice_handsfree = on
    if lang:
        new.voice_lang = lang
    s.apply_settings(new, save=not s.hosted)
    st.session_state.pop("_voice_start_failed", None)
    if not on:
        LISTENER.stop()
        return True, "Hands-free voice turned off."
    LISTENER.stop()
    return LISTENER.start(s, effective_lang(s))


def _meter(level: float) -> str:
    n = int(round(level * 20))
    return "".join(f"<i style='height:{4 + min(i, n) * 1.1:.0f}px;opacity:{1 if i < n else .25}'></i>" for i in range(20))


@st.fragment(run_every=1.0)
def sidebar_indicator() -> None:
    s = state.svc()
    if s.hosted:
        return
    if nav := LISTENER.nav_request:
        LISTENER.nav_request = None
        try:
            st.switch_page(st.session_state.pages[nav])
        except Exception:
            pass
    if not LISTENER.running:
        if s.settings.voice_handsfree and (err := st.session_state.get("_voice_start_error")):
            st.caption(f"🎙 Hands-free voice is waiting: {err}")
        return
    label = STATE_TEXT.get(LISTENER.state, LISTENER.state)
    heard = LISTENER.partial or next((m["text"] for m in reversed(LISTENER.log) if m["who"] in {"you", "agent"}), "")
    st.html(f"<div class='v-side {LISTENER.state}'><div class='v-side-h'><span class='v-dot'></span>{C.esc(label)}</div>"
            f"<div class='v-meter'>{_meter(LISTENER.level)}</div>"
            f"<div class='v-heard'>{C.esc(heard[:90])}</div></div>")


@st.fragment(run_every=1.0)
def live_panel() -> None:
    rows = list(LISTENER.log)[-14:]
    body = "".join(
        f"<div class='l'><span class='t'>{m['t']}</span> <span class='{'p' if m['who'] == 'you' else 'OK' if m['who'] == 'agent' else 'WARN'}'>"
        f"{C.esc({'you': 'You', 'agent': 'Agent', 'ignored': 'Ignored', 'system': 'System'}.get(m['who'], m['who']))}:</span> "
        f"<span dir='auto'>{C.esc(m['text'])}</span></div>" for m in rows)
    live = LISTENER.partial
    if live:
        body += f"<div class='l'><span class='p'>…</span> <i>{C.esc(live)}</i></div>"
    status = STATE_TEXT.get(LISTENER.state, LISTENER.state) if LISTENER.running else "Voice off"
    st.markdown(C.panel("Hands-free voice", "brain",
                        f"<div class='v-meter big'>{_meter(LISTENER.level)}</div><div class='term'>{body or '…'}</div>",
                        meta=status), unsafe_allow_html=True)


def page_section() -> None:
    """Hands-free controls at the top of the Voice Assistant page."""
    s = state.svc()
    if s.hosted:
        st.markdown(C.callout("info", "<b>Hands-free (always-on) voice runs on your own PC.</b> A website cannot keep "
                                      "your microphone open, so here use the record button below. Start the agent "
                                      "locally with run.bat to just speak commands with no clicks."),
                    unsafe_allow_html=True)
        return
    ok, why = listener.available()
    lang = s.settings.voice_lang

    def _toggled():
        st.session_state.vh_msg = set_handsfree(bool(st.session_state.vh_toggle), lang)

    c1, c2 = st.columns([2, 3], vertical_alignment="center")
    if "vh_toggle" not in st.session_state:
        st.session_state.vh_toggle = bool(s.settings.voice_handsfree and ok)
    c1.toggle("Always-on voice (hands-free)", key="vh_toggle", disabled=not ok, on_change=_toggled,
              help="Listens to your microphone all the time (offline). Just speak — no clicks, no Enter.")
    if msg := st.session_state.pop("vh_msg", None):
        (c2.success if msg[0] else c2.error)(msg[1])
    elif s.settings.voice_handsfree and not LISTENER.running and not stt.model_ready(s.voice_dir, lang):
        c2.warning(f"Download the {i18n.lang_info(lang)['name']} speech model below — hands-free starts right after.")
    if not ok:
        c2.error(why)
    else:
        c2.caption("LOW-risk commands run instantly · MEDIUM-risk ones ask you to say “yes” · HIGH-risk ones always "
                   "need a click. Say “stop” at any time.")
    live_panel()
