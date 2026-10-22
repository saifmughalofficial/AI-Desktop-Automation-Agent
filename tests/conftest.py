"""Shared fixtures. Every test works in a fresh temporary folder — never on real documents."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import ApprovedRoot, load_defaults  # noqa: E402
from app.core.permissions import Permissions  # noqa: E402
from app.core.policy_engine import PolicyEngine  # noqa: E402
from app.services import build_services  # noqa: E402


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    (root / "Downloads").mkdir(parents=True)
    (root / "Photos").mkdir()
    (root / "Projects").mkdir()
    (root / "Documents").mkdir()
    (root / "Downloads" / "report.pdf").write_bytes(b"%PDF-1.4 sample")
    (root / "Downloads" / "notes.txt").write_text("hello", encoding="utf-8")
    (root / "Downloads" / "notes_copy.txt").write_text("hello", encoding="utf-8")
    (root / "Downloads" / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (root / "Downloads" / "pic.png").write_bytes(b"\x89PNG fake")
    for n in ("IMG_1.jpg", "IMG_2.jpg"):
        (root / "Photos" / n).write_bytes(n.encode())
    (root / "Projects" / "roadmap.txt").write_text("plan", encoding="utf-8")
    return root


@pytest.fixture
def settings(ws: Path):
    s = load_defaults(ws)
    s.llm.mode = "rules"
    s.execution.step_delay_s = 0
    return s


@pytest.fixture
def perms(settings):
    return Permissions(settings)


@pytest.fixture
def policy(settings, perms):
    return PolicyEngine(settings, perms, hosted=True)


@pytest.fixture
def svc(ws: Path, tmp_path: Path):
    s = build_services(hosted=True, data_dir=tmp_path / "data", workspace=ws)
    new = s.settings.model_copy(deep=True)
    new.llm.mode = "rules"
    new.execution.step_delay_s = 0
    s.apply_settings(new, save=False)
    return s


def outside_root(tmp_path: Path) -> ApprovedRoot:
    other = tmp_path / "outside"
    other.mkdir(exist_ok=True)
    return ApprovedRoot(alias="Other", path=str(other))
