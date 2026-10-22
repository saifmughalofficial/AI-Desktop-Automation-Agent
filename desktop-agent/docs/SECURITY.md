# Security model

## Principles
- **Least privilege.** The agent can only touch files inside approved folders and can only launch allowlisted programs.
- **Plans are untrusted.** Output from the rules parser or a local model is treated as data. It is validated against a strict Pydantic schema: unknown actions, extra fields, absolute paths and `..` are all rejected. The policy engine then re-checks every step right before it runs.
- **The policy engine decides** the risk level, approval requirement and just-in-time confirmation. A model's opinion is never consulted for these.
- **No arbitrary execution.** User or model text is never passed to `eval`, `exec`, a shell, PowerShell or Command Prompt. Apps start with `subprocess.Popen([exe], shell=False)`, and only from the allowlist.
- **Visible and stoppable.** There are no hidden windows, persistence, credential access or security changes. STOP is checked between actions.
- **Local only.** There is no telemetry. Model URLs must be localhost, and proxies are bypassed for them.

## Sandbox (app/core/permissions.py)
- Paths are expressed as `(root alias, relative path)`, then canonicalised with `os.path.realpath`, which resolves symlinks and junctions. Any result outside the approved root is refused.
- The following cannot be approved: drive roots, the entire home folder, Windows, Program Files, ProgramData and AppData (which hold credentials and settings).
- Approved folders can be read-only or read-write.
- The internal quarantine `.agent_trash` cannot be targeted by plans.

## Risk levels (app/core/policy_engine.py)
| Level | Examples | Handling |
|---|---|---|
| LOW | list, duplicates, launch an allowlisted app, create one folder | Visible and stoppable |
| MEDIUM | copy, move, rename, several folders, zip, new file, type text | Approval dialog showing exact targets (configurable) |
| HIGH | delete (quarantine) | Approval, plus a tick box, plus typing APPROVE, plus confirmation right before each step. Cannot be disabled |
| Refused (high-risk categories) | send/e-mail, upload/share, purchases, installing software, system settings | Not implemented in this version |
| BLOCKED | passwords/cookies/tokens, disabling security, stealth or persistence, shell/scripts/executables, wiping drives or whole folders | Never implemented; refused before planning |

## Data protection
- Files are never overwritten: copies and new files use exclusive-create mode, and moves check the destination first. Name conflicts pause the run.
- "Delete" moves the item into `<root>\.agent_trash`. Undo restores it.
- Bulk deletes are capped (default 20 per run), and so are actions per run (default 100).
- History and logs store summaries and outcomes only. Passwords, tokens, cookies, e-mail addresses and the home path are redacted, and document contents are never stored.

## Desktop automation
- Typing is only allowed into a window the agent itself launched in the current session. The window is found by its accessibility tree, not by screen coordinates, and the typed text is read back to verify it.
- If an application cannot be controlled reliably, the step fails with an honest message. Unverifiable results are marked UNVERIFIED.

## Hosted deployment
On Streamlit Cloud the agent runs in sandbox mode:
- each session gets a private temporary copy of the demo workspace
- settings and history are kept per session
- desktop control is disabled

When running locally, `run.bat` binds to 127.0.0.1 so other machines on the network cannot reach the agent.

## Reporting
Report security issues privately to the project maintainer rather than in public issues.
