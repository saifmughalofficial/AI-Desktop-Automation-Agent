"""Invalid action payloads, malformed model output and a missing local AI runtime."""
from __future__ import annotations

import socket

import pytest
from pydantic import ValidationError

from app.config.settings import LLMSettings
from app.core.action_schema import parse_step_payload
from app.llm.local_model import (LocalModelClient, ModelOutputError, ModelUnavailable, check_local_url, extract_json,
                                 validate_proposal)


@pytest.mark.parametrize("payload", [
    {"action": "run_shell", "command": "del *"},                                     # unknown action
    {"action": "list_files", "target": {"root": "Demo"}, "unexpected": 1},            # extra field
    {"action": "list_files", "target": {"root": "Demo", "path": "C:\\Windows"}},      # absolute path
    {"action": "copy_file", "source": {"root": "Demo", "path": "../x"}, "destination": {"root": "Demo"}},
    {"action": "rename_file", "source": {"root": "Demo", "path": "a.txt"}, "new_name": "..\\evil.txt"},
    {"action": "create_folder", "target": {"root": "Demo", "path": ""}},              # empty name
    {"action": "type_text", "app": "Notepad", "text": ""},
    {"macro": "bulk_rename", "target": {"root": "Demo"}},                             # nothing to rename with
    {"no_action": True},
    "list files",
])
def test_invalid_payloads_rejected(payload):
    with pytest.raises((ValueError, ValidationError)):
        parse_step_payload(payload)


def test_valid_payload():
    a = parse_step_payload({"action": "list_files", "target": {"root": "Demo", "path": "a\\b"}, "extensions": [".PDF"]})
    assert a.target.path == "a/b" and a.extensions == ["pdf"]


def test_only_local_urls_allowed():
    assert check_local_url("http://127.0.0.1:11434/") == "http://127.0.0.1:11434"
    for bad in ["https://api.openai.com", "http://192.168.1.5:11434", "ftp://localhost", "localhost:11434"]:
        with pytest.raises(ValueError):
            check_local_url(bad)


def test_extract_json_tolerates_fences_and_chatter():
    obj = extract_json('Sure!\n```json\n{"steps": [], "clarification": "Which folder? {x}"}\n```')
    assert obj["clarification"] == "Which folder? {x}"


@pytest.mark.parametrize("text", ["", "no json here", '{"steps": [', "[1, 2]"])
def test_malformed_model_output(text):
    with pytest.raises(ModelOutputError):
        extract_json(text)


def test_model_step_outside_schema_rejected():
    with pytest.raises(ModelOutputError):
        validate_proposal({"steps": [{"action": "delete_everything"}]})
    with pytest.raises(ModelOutputError):
        validate_proposal({"steps": []})


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_missing_runtime_reports_unavailable():
    port = _free_port()
    cfg = LLMSettings(mode="ollama", ollama_url=f"http://127.0.0.1:{port}", timeout_s=2)
    client = LocalModelClient(cfg)
    st = client.status(max_age=0)
    assert not st["available"] and "not reachable" in st["detail"]
    with pytest.raises(ModelUnavailable):
        client.propose("list files", "")


def test_rules_mode_never_contacts_a_model():
    assert LocalModelClient(LLMSettings(mode="rules")).status()["available"] is False
