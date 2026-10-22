"""Redaction and structured (JSON-lines) logging.

Secrets, e-mail addresses and the user's home path are scrubbed before anything
is written to the history database or the log file. Document contents are
never logged."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_HOME = str(Path.home())
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|auth|cookie|session[_-]?id)"
                r"(\s*[:=]\s*|\s+is\s+)(\S+)"), r"\1\2[REDACTED]"),
    (re.compile(r"(?i)\bbearer\s+[a-z0-9._\-~+/]+=*"), "Bearer [REDACTED]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b(?:sk|pk|ghp|gho|xox[abp])[-_][A-Za-z0-9_\-]{16,}\b"), "[REDACTED-KEY]"),
    (re.compile(r"\b[A-Fa-f0-9]{40,}\b"), "[REDACTED-HEX]"),
]


def redact(text: object, limit: int = 600) -> str:
    s = "" if text is None else str(text)
    if _HOME and len(_HOME) > 3:
        s = re.sub(re.escape(_HOME), "~", s, flags=re.I)
    for pattern, repl in _RULES:
        s = pattern.sub(repl, s)
    return s if len(s) <= limit else s[: limit - 1] + "…"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": datetime.fromtimestamp(record.created).isoformat(timespec="seconds"),
                   "level": record.levelname, "event": redact(record.getMessage())}
        payload.update({k: redact(v) for k, v in getattr(record, "fields", {}).items()})
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(log_dir: Path) -> logging.Logger:
    logger = logging.getLogger("desktop_agent")
    target = str(log_dir / "agent.log")
    if any(getattr(h, "baseFilename", None) == target for h in logger.handlers):
        return logger
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(target, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    logging.getLogger("desktop_agent").log(level, event, extra={"fields": fields})
