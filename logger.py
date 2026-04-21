"""
security/logger.py
═══════════════════
Security Logger — بيسجّل كل العمليات (من طلب لنتيجة).
يدعم debugging و monitoring.

السجلات بتتحفظ في:
  • الذاكرة (آخر 500 event)
  • ملف JSON (اختياري)
"""

import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


class EventType(Enum):
    SUCCESS = "success"
    BLOCKED = "blocked"
    ERROR   = "error"
    INFO    = "info"


@dataclass
class SecurityEvent:
    timestamp:  str
    event_type: str
    tool_name:  str
    args:       Dict
    result:     str
    elapsed_ms: float = 0.0
    reason:     str   = ""

    def to_dict(self) -> dict:
        return asdict(self)


class SecurityLogger:
    """
    نظام تسجيل الأحداث الأمنية.
    بيحفظ كل tool call مع نتيجته وسببه.
    """

    MAX_MEMORY_EVENTS = 500

    def __init__(self, log_file: Optional[str] = None, verbose: bool = False):
        self._events: List[SecurityEvent] = []
        self._log_file = Path(log_file) if log_file else None
        self._verbose  = verbose

        # إعداد Python logger
        self._logger = logging.getLogger("PeacockSecurity")
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%H:%M:%S"
            ))
            self._logger.addHandler(handler)
        self._logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # ── تسجيل الأحداث ─────────────────────────────────────────

    def log_success(self, tool: str, args: dict, result: str, elapsed_ms: float):
        self._add(EventType.SUCCESS, tool, args, result[:200], elapsed_ms)
        if self._verbose:
            self._logger.debug(f"✅ {tool} ({elapsed_ms:.0f}ms)")

    def log_blocked(self, tool: str, args: dict, reason: str):
        self._add(EventType.BLOCKED, tool, args, "BLOCKED", 0, reason)
        self._logger.warning(f"🛡️ BLOCKED {tool} — {reason}")

    def log_error(self, tool: str, args: dict, error: str, elapsed_ms: float):
        self._add(EventType.ERROR, tool, args, f"ERROR: {error}", elapsed_ms)
        self._logger.error(f"❌ {tool} failed — {error}")

    def log_info(self, message: str, data: dict = None):
        self._add(EventType.INFO, "system", data or {}, message)
        self._logger.info(f"ℹ️ {message}")

    def _add(
        self,
        etype: EventType,
        tool: str,
        args: dict,
        result: str,
        elapsed: float = 0,
        reason: str = ""
    ):
        # إخفاء القيم الحساسة من الـ log
        safe_args = self._mask_sensitive(args)

        event = SecurityEvent(
            timestamp  = datetime.now().isoformat(),
            event_type = etype.value,
            tool_name  = tool,
            args       = safe_args,
            result     = result,
            elapsed_ms = round(elapsed, 2),
            reason     = reason,
        )
        self._events.append(event)

        # حافظ على الذاكرة
        if len(self._events) > self.MAX_MEMORY_EVENTS:
            self._events = self._events[-self.MAX_MEMORY_EVENTS:]

        # اكتب للملف لو مضبوط
        if self._log_file:
            self._write_to_file(event)

    def _mask_sensitive(self, args: dict) -> dict:
        """يخفي القيم الحساسة من الـ log"""
        sensitive_keys = {"api_key", "password", "token", "secret", "key"}
        safe = {}
        for k, v in args.items():
            if any(s in k.lower() for s in sensitive_keys):
                safe[k] = "***"
            elif isinstance(v, str) and len(v) > 200:
                safe[k] = v[:200] + "...[truncated]"
            else:
                safe[k] = v
        return safe

    def _write_to_file(self, event: SecurityEvent):
        try:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass  # مش نكسر العملية بسبب الـ logging

    # ── استعلام ───────────────────────────────────────────────

    @property
    def events(self) -> List[SecurityEvent]:
        return list(self._events)

    def get_recent(self, n: int = 20) -> List[SecurityEvent]:
        return self._events[-n:]

    def get_blocked(self) -> List[SecurityEvent]:
        return [e for e in self._events if e.event_type == EventType.BLOCKED.value]

    def summary(self) -> dict:
        total   = len(self._events)
        blocked = sum(1 for e in self._events if e.event_type == "blocked")
        errors  = sum(1 for e in self._events if e.event_type == "error")
        return {
            "total_events": total,
            "blocked":      blocked,
            "errors":       errors,
            "success":      total - blocked - errors,
        }

    def clear(self):
        self._events.clear()
