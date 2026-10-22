"""User settings: approved folders, app allowlist, workflows, local AI and policy options.

Settings are validated with Pydantic and stored as JSON. The demo workspace path
is stored as the placeholder ${DEMO_WORKSPACE} so the file stays portable."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.runtime import CONFIG_DIR

DEMO_TOKEN = "${DEMO_WORKSPACE}"
ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,39}$")


class ApprovedRoot(BaseModel):
    alias: str
    path: str
    access: Literal["read", "read_write"] = "read_write"

    @field_validator("alias")
    @classmethod
    def _alias(cls, v: str) -> str:
        v = v.strip()
        if not ALIAS_RE.match(v):
            raise ValueError("alias must be 1-40 letters, digits, spaces, '_' or '-'")
        return v


class AppEntry(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    aliases: list[str] = Field(default_factory=list)
    command: str = Field(min_length=1, max_length=400)
    window_title: str = ""
    platforms: list[str] = Field(default_factory=lambda: ["win32"])
    automatable: bool = False

    def matches(self, text: str) -> bool:
        t = text.strip().lower()
        return t == self.name.lower() or t in {a.lower() for a in self.aliases}


class Workflow(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = ""
    commands: list[str] = Field(min_length=1, max_length=20)


class LLMSettings(BaseModel):
    mode: Literal["auto", "rules", "ollama", "llamacpp"] = "auto"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    llamacpp_url: str = "http://127.0.0.1:8080"
    timeout_s: float = Field(45, ge=2, le=300)


class PolicySettings(BaseModel):
    require_approval_medium: bool = True
    jit_confirm_high: bool = True
    conflict_policy: Literal["ask", "skip", "rename"] = "ask"
    max_actions_per_run: int = Field(100, ge=1, le=500)
    max_bulk_delete: int = Field(20, ge=1, le=100)
    stop_on_failure: bool = True


class ExecutionSettings(BaseModel):
    step_delay_s: float = Field(0.35, ge=0, le=5)
    verify_launch_timeout_s: float = Field(6, ge=1, le=30)


class Settings(BaseModel):
    approved_roots: list[ApprovedRoot] = Field(default_factory=list)
    apps: list[AppEntry] = Field(default_factory=list)
    workflows: list[Workflow] = Field(default_factory=list)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    policy: PolicySettings = Field(default_factory=PolicySettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    history_enabled: bool = True
    animations: bool = True
    theme: Literal["dual", "blue"] = "dual"
    background_fx: bool = True

    def root_aliases(self) -> list[str]:
        return [r.alias for r in self.approved_roots]


def _substitute(raw: str, demo_path: Path) -> dict:
    return json.loads(raw.replace(DEMO_TOKEN, json.dumps(str(demo_path))[1:-1]))


def load_defaults(demo_path: Path) -> Settings:
    raw = (CONFIG_DIR / "defaults.json").read_text(encoding="utf-8")
    return Settings.model_validate(_substitute(raw, demo_path))


class SettingsStore:
    """Loads/saves settings. With path=None (hosted mode) settings live in memory only."""

    def __init__(self, path: Path | None, demo_path: Path):
        self.path = path
        self.demo_path = demo_path

    def load(self) -> Settings:
        defaults = load_defaults(self.demo_path)
        if not self.path or not self.path.exists():
            return defaults
        try:
            data = _substitute(self.path.read_text(encoding="utf-8"), self.demo_path)
            merged = defaults.model_dump()
            merged.update(data)
            return Settings.model_validate(merged)
        except (ValueError, OSError):
            # A corrupted settings file must never brick the app: fall back to defaults.
            return defaults

    def save(self, settings: Settings) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(settings.model_dump(), indent=2)
        demo = json.dumps(str(self.demo_path))[1:-1]
        self.path.write_text(text.replace(demo, DEMO_TOKEN), encoding="utf-8")
