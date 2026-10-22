"""Multilingual voice: native keywords -> canonical commands, localized replies, Urdu script."""
import pytest

from app.core.system_manager import SystemManager
from app.voice import i18n, tts
from app.voice.assistant import VoiceAssistant


@pytest.mark.parametrize("lang,text,canon", [
    ("ur", "بیٹری کتنی ہے", "battery"), ("ur", "awaz barhao", "volume up"), ("ur", "समय क्या है", "what time is it"),
    ("hi", "सिस्टम की हालत", "system status"), ("ar", "كم الساعة", "what time is it"), ("fr", "quelle heure est-il", "what time is it"),
    ("es", "abre la calculadora", "open calculator"), ("de", "wie spät ist es", "what time is it"), ("ru", "сколько памяти", "memory usage"),
    ("zh", "系统状态", "system status"), ("tr", "sesi kapat", "mute"), ("ur", "کمپیوٹر بند کرو", "shut down the computer"),
])
def test_native_keywords(lang, text, canon):
    assert i18n.to_command(text, lang) == canon


def test_localized_replies_and_safety():
    sm = SystemManager(hosted=True)
    r = VoiceAssistant(sm, "ur").handle("سسٹم کی حالت")
    assert r.kind == "answer" and "سسٹم" in r.say and r.heard == "system status"
    r = VoiceAssistant(sm, "ur").handle("کمپیوٹر بند کرو")
    assert r.kind == "answer" and "نہیں" in r.say  # hosted: refused, never executed
    assert VoiceAssistant(sm, "es").handle("abre la calculadora").target == "open calculator"
    assert VoiceAssistant(sm, "ja").handle("hello").kind == "answer"  # English still works in any language


def test_every_language_has_model_and_voice():
    for code, info in i18n.LANGS.items():
        assert info["model"].startswith("vosk-model") and info["voice"] and info["mb"] > 0
        assert i18n.t("cpu", code, v="5")


def test_devanagari_to_urdu():
    assert i18n.deva_to_urdu("क्या है") == "کیا ہے"


def test_offline_voice_many_languages():
    for lang, s in [("ur", "سلام"), ("hi", "नमस्ते"), ("ar", "مرحبا"), ("en", "hello")]:
        assert tts.synthesize(s, 1, lang), lang
