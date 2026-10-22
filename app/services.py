"""Wires the layers together (settings -> permissions -> policy -> planner/orchestrator).

UI code talks only to a Services object, so the same core runs under the
Streamlit UI, the tests, or any other front end."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.config.settings import Settings, SettingsStore
from app.core.orchestrator import Orchestrator
from app.core.permissions import Permissions
from app.core.planner import Planner
from app.core.policy_engine import PolicyEngine
from app.core.system_monitor import SystemMonitor
from app.actions.virtual_desktop import VirtualDesktop
from app.demo_seed import copy_demo_to, seed_demo_workspace
from app.llm.local_model import LocalModelClient
from app.runtime import DEMO_WORKSPACE, hosted_mode, local_data_dir
from app.storage.audit_log import log_event, setup_logging
from app.storage.database import Database


_RECOVERED: set[str] = set()


@dataclass
class Services:
    hosted: bool
    workspace: Path
    data_dir: Path
    store: SettingsStore
    settings: Settings
    perms: Permissions
    policy: PolicyEngine
    llm: LocalModelClient
    planner: Planner
    orchestrator: Orchestrator
    db: Database
    monitor: SystemMonitor = field(default_factory=SystemMonitor)

    def apply_settings(self, settings: Settings, save: bool = True) -> None:
        """Validate-and-swap: rebuild the policy stack from new settings; keep history/monitor/app handles."""
        if save:
            self.store.save(settings)
        self.settings = settings
        self.perms = Permissions(settings)
        self.policy = PolicyEngine(settings, self.perms, hosted=self.hosted)
        self.llm = LocalModelClient(settings.llm)
        self.planner = Planner(settings, self.perms, self.policy, self.llm)
        self.orchestrator.update(settings, self.perms, self.policy)
        self.db.enabled = settings.history_enabled
        log_event("settings_applied", roots=len(settings.approved_roots), apps=len(settings.apps))


def build_services(*, hosted: bool | None = None, data_dir: Path | None = None,
                   workspace: Path | None = None) -> Services:
    hosted = hosted_mode() if hosted is None else hosted
    if hosted:
        sandbox = Path(tempfile.mkdtemp(prefix="desktop_agent_"))
        workspace = workspace or copy_demo_to(sandbox / "demo_workspace", DEMO_WORKSPACE)
        data_dir = data_dir or sandbox / "data"
        store = SettingsStore(None, workspace)
    else:
        workspace = workspace or DEMO_WORKSPACE
        if not workspace.exists() or not any(workspace.iterdir()):
            seed_demo_workspace(workspace)
        data_dir = data_dir or local_data_dir()
        store = SettingsStore(data_dir / "settings.json", workspace)
    data_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(data_dir / "logs")
    settings = store.load()
    perms = Permissions(settings)
    policy = PolicyEngine(settings, perms, hosted=hosted)
    llm = LocalModelClient(settings.llm)
    db = Database(data_dir / "history.sqlite3", enabled=settings.history_enabled)
    if str(db.path) not in _RECOVERED:  # once per process, so another tab's live run is never touched
        _RECOVERED.add(str(db.path))
        db.mark_interrupted()
    svc = Services(hosted=hosted, workspace=workspace, data_dir=data_dir, store=store, settings=settings,
                   perms=perms, policy=policy, llm=llm, planner=Planner(settings, perms, policy, llm),
                   orchestrator=Orchestrator(settings, perms, policy, db, VirtualDesktop() if hosted else None), db=db)
    log_event("services_started", hosted=hosted)
    return svc
