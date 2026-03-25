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
    try:
        expires_at = datetime.fromisoformat(token.expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        # 增加到 5 分钟缓冲，防止时钟漂移
        return datetime.now(UTC) + timedelta(seconds=300) < expires_at
    except Exception:
        return False


def refresh_token_valid(token: TokenBundle) -> bool:
    if not token.refresh_token:
        return False
    if not token.refresh_expires_at:
        return True
    try:
        expires_at = datetime.fromisoformat(token.refresh_expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return datetime.now(UTC) + timedelta(seconds=60) < expires_at
    except Exception:
        return False
