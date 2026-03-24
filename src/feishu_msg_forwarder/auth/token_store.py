from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..models import TokenBundle


def load_token(path: str) -> TokenBundle | None:
    token_path = Path(path)
    if not token_path.exists():
        return None
    data = json.loads(token_path.read_text(encoding="utf-8"))
    return TokenBundle(**data)


def save_token(path: str, token: TokenBundle) -> None:
    token_path = Path(path)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps(asdict(token), ensure_ascii=False, indent=2), encoding="utf-8")


def access_token_valid(token: TokenBundle) -> bool:
    expires_at = datetime.fromisoformat(token.expires_at)
    return datetime.now(UTC) + timedelta(seconds=60) < expires_at


def refresh_token_valid(token: TokenBundle) -> bool:
    if not token.refresh_token:
        return False
    if not token.refresh_expires_at:
        return True
    expires_at = datetime.fromisoformat(token.refresh_expires_at)
    return datetime.now(UTC) + timedelta(seconds=60) < expires_at
