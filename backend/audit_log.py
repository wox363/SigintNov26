"""
Audit Log — append-only operator action record
==============================================
AMBER has no user-account system (one workstation = one operator).
When multiple officers share an agency's single install, this log provides
basic defensibility: who-did-what-when, using the OS login as the identity.

Scope (what gets logged):
  - Case created / deleted
  - Upload created / soft-deleted / undone / re-uploaded / purged
  - Analysis started / completed / failed
  - WhatsApp upload created / deleted
  - Cross-case comparison run
  - Report downloaded (DOCX / PDF)
  - Briefing deck downloaded

Not logged:
  - GET requests (reads)
  - Health checks
  - Static-file hits

Storage: MongoDB `audit` collection, append-only. No delete endpoint exposed.
Retention: indefinite. Rotate externally if disk pressure emerges.
"""
from __future__ import annotations

import getpass
import logging
import os
import socket
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_HOSTNAME = socket.gethostname() or "unknown-host"


def _current_operator() -> str:
    """Best-effort identity on an offline Windows deployment.

    Order of preference:
      1. AMBER_OPERATOR environment variable (if the installer sets it per launch)
      2. USERNAME env var (Windows default)
      3. getpass.getuser() (cross-platform fallback)
      4. 'unknown'
    """
    for key in ("AMBER_OPERATOR", "USERNAME", "USER"):
        v = os.environ.get(key)
        if v:
            return v
    try:
        return getpass.getuser() or "unknown"
    except Exception:
        return "unknown"


async def record(db, action: str, *, case_id: str | None = None,
                 target: str | None = None, details: dict[str, Any] | None = None) -> None:
    """Append one audit record. Never raises — audit must not break the app."""
    try:
        doc = {
            "id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "operator": _current_operator(),
            "host": _HOSTNAME,
            "action": action,
            "case_id": case_id,
            "target": target,
            "details": details or {},
        }
        await db.audit.insert_one(doc)
    except Exception as e:
        # Never let audit failure break the primary operation
        logger.warning(f"Audit write failed for action={action}: {e}")


async def ensure_indexes(db) -> None:
    """Idempotent — called on startup."""
    try:
        await db.audit.create_index([("ts", -1)])
        await db.audit.create_index([("case_id", 1), ("ts", -1)])
        await db.audit.create_index([("operator", 1), ("ts", -1)])
        await db.audit.create_index([("action", 1), ("ts", -1)])
    except Exception as e:
        logger.warning(f"Could not create audit indexes: {e}")
