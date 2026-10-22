"""Orchestrator: runs an approved plan one action at a time.

* Refuses to start a plan that needs approval unless it was approved.
* Checks the Stop flag between actions and never starts a new action after Stop.
* Re-validates each action with the policy engine right before running it.
* Pauses for just-in-time confirmation of HIGH-risk steps and on name conflicts.
* Records every outcome (and undo data) in the local history, honestly —
  partial completion is reported as such."""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from app.actions import filesystem as fs
from app.actions import registry
from app.actions.registry import ActionResult, ConflictError, ExecContext
from app.config.settings import Settings
from app.core.action_schema import PathRef, Plan, StepStatus
from app.core.permissions import PathViolation, Permissions
from app.core.policy_engine import PolicyEngine, Simulation
from app.runtime import IS_WINDOWS
from app.storage.audit_log import log_event, redact
from app.storage.database import Database

TERMINAL = {"completed", "partial", "failed", "cancelled", "rejected"}
READ_ONLY = {"list_files", "find_duplicates"}


@dataclass
class StepState:
    index: int
    action: str
    description: str
    risk: str
    status: StepStatus = StepStatus.PENDING
    message: str = ""
    verified: bool = False
    details: dict = field(default_factory=dict)
    started: float | None = None
    finished: float | None = None


class RunState:
    def __init__(self, plan: Plan, task_id: int | None, dry_run: bool):
        self.id = uuid.uuid4().hex[:8]
        self.plan = plan
        self.task_id = task_id
        self.dry_run = dry_run
        self.status = "queued"
        self.steps = [StepState(s.index, s.action.action, s.description, s.risk.value) for s in plan.steps]
        self.log: deque[tuple[str, str, str]] = deque(maxlen=500)
        self.cancel = threading.Event()
        self.lock = threading.RLock()
        self.pause: dict | None = None
        self.confirmed: set[int] = set()
        self.conflict_override: dict[int, str] = {}
        self.current = -1
        self.started_at = time.time()
        self.finished_at: float | None = None
        self.thread: threading.Thread | None = None
        self.summary = ""
        self.sim = Simulation()  # planned disk state, used for dry runs

    def add_log(self, level: str, msg: str) -> None:
        with self.lock:
            self.log.append((datetime.now().strftime("%H:%M:%S"), level, msg))

    @property
    def done(self) -> bool:
        return self.status in TERMINAL

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.steps:
            out[s.status.value] = out.get(s.status.value, 0) + 1
        return out

    @property
    def progress(self) -> float:
        if not self.steps:
            return 1.0
        finished = sum(1 for s in self.steps if s.status not in {StepStatus.PENDING, StepStatus.RUNNING, StepStatus.PAUSED})
        return finished / len(self.steps)


class Orchestrator:
    def __init__(self, settings: Settings, perms: Permissions, policy: PolicyEngine, db: Database | None,
                 virtual=None):
        self.settings = settings
        self.perms = perms
        self.policy = policy
        self.db = db
        self.launched: dict = {}  # app windows opened by this agent in this session
        self.virtual = virtual  # web virtual desktop (hosted mode) or None

    def update(self, settings: Settings, perms: Permissions, policy: PolicyEngine) -> None:
        self.settings, self.perms, self.policy = settings, perms, policy

    # ------------------------------------------------------------------ entry points
    def reject(self, plan: Plan, reason: str = "Rejected by user") -> int | None:
        log_event("plan_rejected", request=plan.request, steps=len(plan.steps))
        if not self.db:
            return None
        return self.db.create_task(request=plan.request, summary=plan.summary, engine=plan.engine,
                                   risk=plan.risk.value, status="rejected", approval="rejected",
                                   dry_run=plan.dry_run, step_count=len(plan.steps), note=reason)

    def submit(self, plan: Plan, *, approved: bool = False, background: bool = True) -> RunState:
        if not plan.executable:
            raise ValueError("This plan cannot be executed (it needs clarification, is blocked or has violations).")
        dry = plan.dry_run
        needs = self.policy.approval_required(plan)
        if needs and not approved:
            task_id = self.reject(plan, "Approval required but not given")
            state = RunState(plan, task_id, dry)
            state.status = "rejected"
            state.summary = "REJECTED: approval was not given — nothing was executed."
            for s in state.steps:
                s.status = StepStatus.CANCELLED
                s.message = "Not run — approval was not given."
            state.add_log("WARN", "Approval required but not given — nothing was executed.")
            return state
        approval = "approved" if needs else ("dry-run" if dry else "not required")
        task_id = self.db.create_task(request=plan.request, summary=plan.summary, engine=plan.engine,
                                      risk=plan.risk.value, status="running", approval=approval, dry_run=dry,
                                      step_count=len(plan.steps)) if self.db else None
        state = RunState(plan, task_id, dry)
        state.status = "running"
        state.add_log("INFO", f"Run {state.id} started · {len(plan.steps)} step(s) · approval: {approval}"
                              + (" · DRY RUN" if dry else ""))
        log_event("run_started", run=state.id, request=plan.request, steps=len(plan.steps), approval=approval)
        self._launch(state, 0, background)
        return state

    def stop(self, state: RunState) -> None:
        if state.done:
            return
        state.cancel.set()
        state.add_log("WARN", "STOP requested — no further actions will be started. An action already in progress "
                              "is allowed to finish safely.")
        if state.status == "paused":
            self._finalize(state, cancelled_from=state.pause["step"] if state.pause else state.current + 1)

    def resume(self, state: RunState, decision: str, background: bool = True) -> None:
        """decision: confirm | decline (JIT) / skip | rename | stop (conflict)."""
        if state.status != "paused" or not state.pause:
            return
        idx, kind = state.pause["step"], state.pause["kind"]
        state.pause = None
        if decision in {"decline", "stop"}:
            state.steps[idx].status = StepStatus.CANCELLED
            state.steps[idx].message = "Declined by user." if decision == "decline" else "Stopped by user at conflict."
            state.add_log("WARN", f"Step {idx + 1} {state.steps[idx].message.lower()} Run stopped.")
            self._record(state, idx, ActionResult(StepStatus.CANCELLED, state.steps[idx].message))
            self._finalize(state, cancelled_from=idx + 1)
            return
        if kind == "confirm":
            state.confirmed.add(idx)
            state.add_log("INFO", f"Step {idx + 1} confirmed by user.")
        else:
            state.conflict_override[idx] = decision
            state.add_log("INFO", f"Conflict at step {idx + 1}: user chose '{decision}'.")
        state.status = "running"
        self._launch(state, idx, background)

    # ------------------------------------------------------------------ engine
    def _launch(self, state: RunState, start: int, background: bool) -> None:
        if background:
            state.thread = threading.Thread(target=self._run, args=(state, start), daemon=True,
                                            name=f"agent-run-{state.id}")
            state.thread.start()
        else:
            self._run(state, start)

    def _run(self, state: RunState, start: int) -> None:
        if IS_WINDOWS:
            try:
                import comtypes
                comtypes.CoInitialize()
            except Exception:
                pass
        steps = state.plan.steps
        try:
            for i in range(start, len(steps)):
                if state.cancel.is_set():
                    self._finalize(state, cancelled_from=i)
                    return
                step, ss = steps[i], state.steps[i]
                state.current = i
                if step.requires_confirmation and not state.dry_run and i not in state.confirmed:
                    ss.status = StepStatus.PAUSED
                    state.pause = {"kind": "confirm", "step": i,
                                   "message": f"HIGH-RISK step {i + 1}: {step.description}. {step.consequence}",
                                   "options": ["confirm", "decline"]}
                    state.status = "paused"
                    state.add_log("WARN", f"Paused before step {i + 1} — just-in-time confirmation required.")
                    self._db_status(state, "paused")
                    return
                ss.status, ss.started = StepStatus.RUNNING, time.time()
                state.add_log("RUN", f"[{i + 1}/{len(steps)}] {step.description}")
                result = self._execute_step(state, i)
                if result is None:  # paused on a conflict
                    return
                ss.status, ss.message, ss.verified = result.status, result.message, result.verified
                ss.details, ss.finished = result.details, time.time()
                level = {"success": "OK", "simulated": "SIM", "skipped": "SKIP", "unverified": "WARN"}.get(
                    result.status.value, "FAIL")
                state.add_log(level, result.message)
                self._record(state, i, result)
                if result.status == StepStatus.FAILED and self.settings.policy.stop_on_failure:
                    state.add_log("WARN", "Stopping: an action failed and 'stop on failure' is enabled.")
                    self._finalize(state, cancelled_from=i + 1, reason="Not started because an earlier step failed.")
                    return
                delay = self.settings.execution.step_delay_s
                if delay and i < len(steps) - 1:
                    state.cancel.wait(delay)  # returns early when Stop is pressed
            self._finalize(state)
        except Exception as exc:  # never leave a run hanging in 'running'
            state.add_log("FAIL", f"Unexpected error: {redact(exc)}")
            log_event("run_crashed", run=state.id, error=f"{exc.__class__.__name__}: {exc}")
            self._finalize(state, cancelled_from=state.current + 1, reason="Not started because of an unexpected error.")

    def _execute_step(self, state: RunState, i: int) -> ActionResult | None:
        step = state.plan.steps[i]
        if state.dry_run:
            return self._simulate_step(state, i)
        chk = self.policy.check(step.action)  # re-validate against the current disk state
        if chk.violation:
            return ActionResult(StepStatus.FAILED, f"Refused by policy at run time: {chk.violation}")
        ctx = ExecContext(perms=self.perms, settings=self.settings, dry_run=state.dry_run,
                          conflict_mode=state.conflict_override.get(i, self.settings.policy.conflict_policy),
                          cancel=state.cancel, launched=self.launched, virtual=self.virtual)
        try:
            return registry.execute(step.action, ctx)
        except ConflictError as exc:
            state.steps[i].status = StepStatus.PAUSED
            state.pause = {"kind": "conflict", "step": i, "message": str(exc), "options": ["skip", "rename", "stop"]}
            state.status = "paused"
            state.add_log("WARN", f"Paused at step {i + 1}: {exc}")
            self._db_status(state, "paused")
            return None
        except PathViolation as exc:
            return ActionResult(StepStatus.FAILED, f"Refused by sandbox: {exc}")
        except PermissionError as exc:
            return ActionResult(StepStatus.FAILED, f"Windows denied access ({redact(exc)}). Nothing was overwritten.")
        except FileExistsError:
            return ActionResult(StepStatus.FAILED, "The destination appeared while running — not overwritten.")
        except OSError as exc:
            return ActionResult(StepStatus.FAILED, f"Operating-system error: {redact(exc)}")

    def _simulate_step(self, state: RunState, i: int) -> ActionResult:
        """Dry run: check every step against the *planned* state; only read-only actions touch the disk."""
        step = state.plan.steps[i]
        chk = self.policy.check(step.action, state.sim)
        if chk.violation:
            return ActionResult(StepStatus.FAILED, f"[dry run] Would be refused: {chk.violation}")
        if step.action.action in READ_ONLY:
            try:
                if self.perms.resolve(step.action.target).is_dir():
                    ctx = ExecContext(perms=self.perms, settings=self.settings, dry_run=True, launched=self.launched)
                    return registry.execute(step.action, ctx)
            except PathViolation as exc:
                return ActionResult(StepStatus.FAILED, f"[dry run] {exc}")
        msg = f"[dry run] Would: {step.description}."
        if chk.conflict:
            msg += f" Conflict: {chk.conflict} The real run would pause and ask."
        if chk.note:
            msg += f" ({chk.note})"
        return ActionResult(StepStatus.SIMULATED, msg)

    def _record(self, state: RunState, i: int, result: ActionResult) -> None:
        step = state.plan.steps[i]
        if self.db:
            self.db.add_action(state.task_id, step_index=i, action_type=step.action.action,
                               target=" → ".join(step.targets), risk=step.risk.value, status=result.status.value,
                               verified=result.verified, message=result.message, undo=result.undo or None)
        log_event("action", run=state.id, step=i + 1, action=step.action.action, status=result.status.value,
                  verified=result.verified, message=result.message)

    def _db_status(self, state: RunState, status: str) -> None:
        if self.db:
            self.db.update_task(state.task_id, status=status)

    def _finalize(self, state: RunState, cancelled_from: int | None = None,
                  reason: str = "Not started — run was stopped.") -> None:
        if cancelled_from is not None:
            for s in state.steps[cancelled_from:]:
                if s.status in {StepStatus.PENDING, StepStatus.PAUSED}:
                    s.status, s.message = StepStatus.CANCELLED, reason
        c = state.counts()
        ok = c.get("success", 0) + c.get("unverified", 0) + c.get("simulated", 0) + c.get("skipped", 0)
        failed, cancelled = c.get("failed", 0), c.get("cancelled", 0)
        if state.cancel.is_set() or (cancelled and not failed):
            status = "cancelled"
        elif failed:
            status = "partial" if ok else "failed"
        else:
            status = "completed"
        state.status, state.pause, state.finished_at = status, None, time.time()
        parts = [f"{ok}/{len(state.steps)} step(s) done"]
        if c.get("unverified"):
            parts.append(f"{c['unverified']} unverified")
        if failed:
            parts.append(f"{failed} failed")
        if cancelled:
            parts.append(f"{cancelled} not run")
        state.summary = f"{status.upper()}: " + ", ".join(parts) + (" (dry run — no changes made)" if state.dry_run else "")
        state.add_log("DONE", state.summary)
        if self.db:
            self.db.update_task(state.task_id, status=status, finished_at=datetime.now().isoformat(timespec="seconds"),
                                success_count=ok, failed_count=failed, summary=state.summary)
        log_event("run_finished", run=state.id, status=status, summary=state.summary)

    # ------------------------------------------------------------------ undo
    def undo_task(self, task_id: int) -> dict:
        """Reverse a finished task's file changes, newest first. Never overwrites; skips anything that changed since."""
        if not self.db:
            return {"ok": False, "message": "History is disabled, so there is nothing to undo."}
        task = self.db.get_task(task_id)
        if not task:
            return {"ok": False, "message": f"Task #{task_id} not found."}
        if task["undone"]:
            return {"ok": False, "message": f"Task #{task_id} was already undone."}
        ops = list(reversed(self.db.undo_ops(task_id)))
        if not ops:
            return {"ok": False, "message": "This task made no reversible file changes."}
        undo_id = self.db.create_task(request=f"Undo task #{task_id}", summary=f"Reverse {len(ops)} change(s)",
                                      engine="undo", risk="medium", status="running", approval="approved",
                                      dry_run=False, step_count=len(ops))
        results = []
        for i, op in enumerate(ops):
            try:
                status, msg = self._undo_op(op)
            except (PathViolation, OSError, ValueError) as exc:
                status, msg = "failed", f"Could not undo: {redact(exc)}"
            results.append((status, msg))
            self.db.add_action(undo_id, step_index=i, action_type=f"undo_{op['op']}", target=self._op_target(op),
                               risk="medium", status=status, verified=status == "success", message=msg)
        ok = sum(1 for s, _ in results if s == "success")
        failed = sum(1 for s, _ in results if s == "failed")
        status = "completed" if ok == len(results) else ("partial" if ok else "failed")
        summary = f"Undo of #{task_id}: {ok}/{len(results)} change(s) reversed"
        self.db.update_task(undo_id, status=status, finished_at=datetime.now().isoformat(timespec="seconds"),
                            success_count=ok, failed_count=failed, summary=summary)
        if ok:
            self.db.update_task(task_id, undone=1)
        log_event("undo", task=task_id, reversed=ok, total=len(results))
        return {"ok": ok > 0, "message": summary, "details": results}

    def undo_last(self) -> dict:
        """Undo the most recent task that changed files and hasn't been undone yet."""
        if not self.db:
            return {"ok": False, "message": "History is disabled, so there is nothing to undo."}
        for t in self.db.list_tasks(limit=100):
            if t["engine"] != "undo" and not t["undone"] and self.db.undo_ops(t["id"]):
                return self.undo_task(t["id"])
        return {"ok": False, "message": "There is no recent run with reversible file changes."}

    def record_refusal(self, request: str, reason: str) -> None:
        if self.db:
            self.db.create_task(request=request, summary=reason, engine="policy", risk="blocked", status="refused",
                                approval="blocked", dry_run=False, step_count=0, note=reason)

    @staticmethod
    def _op_target(op: dict) -> str:
        ref = op.get("target") or op.get("from") or {}
        return f"{ref.get('root', '')}/{ref.get('path', '')}"

    def _undo_op(self, op: dict) -> tuple[str, str]:
        kind = op["op"]
        if kind == "remove_empty_dir":
            ref = PathRef(**op["target"])
            p = self.perms.resolve(ref, write=True)
            if not p.is_dir():
                return "skipped", f"{ref.display()} no longer exists."
            if any(p.iterdir()):
                return "skipped", f"{ref.display()} is not empty — left in place."
            p.rmdir()
            return "success", f"Removed empty folder {ref.display()}."
        if kind == "quarantine_created":
            ref = PathRef(**op["target"])
            p = self.perms.resolve(ref, write=True)
            if not p.exists():
                return "skipped", f"{ref.display()} no longer exists."
            if p.is_file() and op.get("sha256") and fs.sha256_file(p) != op["sha256"]:
                return "skipped", f"{ref.display()} was modified since — left in place."
            fs.quarantine(p, self.perms.trash_dir(ref.root))
            return "success", f"Moved {ref.display()} to quarantine."
        if kind in {"move_back", "restore"}:
            src_ref, dst_ref = PathRef(**op["from"]), PathRef(**op["to"])
            src = self.perms.resolve(src_ref, write=True, allow_trash=kind == "restore")
            dst = self.perms.resolve(dst_ref, write=True)
            if not src.exists():
                return "skipped", f"{src_ref.display()} no longer exists."
            if dst.exists() and str(dst).lower() != str(src).lower():
                return "skipped", f"{dst_ref.display()} is occupied — not overwritten."
            if not dst.parent.is_dir():
                return "skipped", f"Folder {dst_ref.parent.display()} no longer exists."
            fs.move_path(src, dst)
            return "success", f"Restored {dst_ref.display()}."
        raise ValueError(f"unknown undo operation {kind!r}")
