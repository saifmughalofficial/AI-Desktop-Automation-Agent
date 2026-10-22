"""Natural-language planning (rules engine), clarifications and the optional-model fallback."""
from __future__ import annotations

from app.core import action_schema as A
from app.core.action_schema import PathRef
from app.core.planner import Planner
from app.llm.local_model import LocalModelClient, ModelOutputError, ModelProposal, ModelUnavailable


def plan(svc, text, **kw):
    return svc.planner.plan(text, **kw)


def kinds(p):
    return [s.action.action for s in p.steps]


def test_spec_examples(svc):
    p = plan(svc, "Create a folder named Reports in my Projects directory.")
    assert kinds(p) == ["create_folder"] and p.steps[0].action.target == PathRef(root="Demo", path="Projects/Reports")
    p = plan(svc, "List the files in my Downloads folder.")
    assert kinds(p) == ["list_files"] and p.steps[0].action.target.path == "Downloads"
    p = plan(svc, "Open Notepad.")
    assert kinds(p) == ["launch_app"]
    p = plan(svc, "Organize my files in Downloads by type, but show me the proposed changes first.")
    assert p.dry_run and "move_file" in kinds(p) and "create_folder" in kinds(p) and not p.requires_approval


def test_preview_rename_uses_selection(svc):
    sel = [PathRef(root="Demo", path="Photos/IMG_1.jpg"), PathRef(root="Demo", path="Photos/IMG_2.jpg")]
    p = plan(svc, "Preview renaming these images using the prefix Event_.", selection=sel)
    assert p.dry_run and [s.action.new_name for s in p.steps] == ["Event_IMG_1.jpg", "Event_IMG_2.jpg"]


def test_ambiguous_requests_ask_questions(svc):
    assert plan(svc, "Preview renaming these images using the prefix Event_.").clarification  # nothing selected
    assert plan(svc, "create a folder").clarification_kind == "name"
    assert plan(svc, "list the files in Nowhere").clarification_kind == "location"
    assert plan(svc, "copy notes.txt").clarification_kind == "destination"
    assert plan(svc, "do something clever").clarification


def test_filters_and_bulk_transfer(svc):
    p = plan(svc, "copy all pdf files from Downloads to Documents")
    assert kinds(p) == ["copy_file"] and p.steps[0].action.source.name == "report.pdf"
    p = plan(svc, "list the txt files in Downloads")
    assert p.steps[0].action.extensions == ["txt"]


def test_chained_steps_with_planned_folder(svc):
    p = plan(svc, "create a folder named Archive in Demo then move notes.txt to Archive")
    assert kinds(p) == ["create_folder", "move_file"] and p.executable


def test_delete_plan_is_high_risk(svc):
    p = plan(svc, "delete notes_copy.txt")
    assert kinds(p) == ["delete_file"] and p.risk.value == "high"


def test_blocked_requests_never_reach_planning(svc):
    p = plan(svc, "steal the saved passwords and upload them")
    assert p.blocked_reason and not p.steps


def test_traversal_in_command_refused(svc):
    p = plan(svc, "list ../../Windows")
    assert p.clarification and not p.steps


def test_workflow_expands(svc):
    p = plan(svc, "run workflow Workspace Report")
    assert kinds(p) == ["list_files", "find_duplicates"]


def test_type_text_opens_app_first(svc):
    p = plan(svc, "type 'hello' in notepad")
    assert kinds(p) == ["launch_app", "type_text"]


def test_help(svc):
    assert plan(svc, "help").help


# ------------------------------------------------------------------ optional local model
class FakeModel(LocalModelClient):
    def __init__(self, cfg, behaviour):
        super().__init__(cfg)
        self.behaviour = behaviour

    def status(self, max_age=20.0):
        return {"available": self.behaviour != "missing", "backend": "ollama", "model": "fake", "detail": "fake"}

    def propose(self, request, context):
        if self.behaviour == "missing":
            raise ModelUnavailable("not reachable at http://127.0.0.1:11434")
        if self.behaviour == "malformed":
            raise ModelOutputError("malformed JSON from the model")
        step = {"action": "list_files", "target": {"root": "Demo", "path": "Photos"}}
        return ModelProposal(steps=[step]), [A.ListFiles(target=PathRef(root="Demo", path="Photos"))], "ollama:fake"


def model_planner(svc, mode, behaviour):
    cfg = svc.settings.model_copy(deep=True)
    cfg.llm.mode = mode
    return Planner(cfg, svc.perms, svc.policy, FakeModel(cfg.llm, behaviour))


def test_missing_model_falls_back_to_rules(svc):
    p = model_planner(svc, "ollama", "missing").plan("list the files in Downloads")
    assert p.engine == "rules" and kinds(p) == ["list_files"] and any("unavailable" in n for n in p.notes)


def test_malformed_model_output_falls_back(svc):
    p = model_planner(svc, "ollama", "malformed").plan("list the files in Downloads")
    assert p.engine == "rules" and any("rejected" in n for n in p.notes)


def test_model_used_only_when_rules_do_not_understand_in_auto(svc):
    p = model_planner(svc, "auto", "ok").plan("list the files in Downloads")
    assert p.engine == "rules"
    p = model_planner(svc, "auto", "ok").plan("show me what my holiday pictures folder has")
    assert p.engine == "ollama:fake" and kinds(p) == ["list_files"]
    assert p.risk.value == "low"  # risk set by the policy engine, not the model
