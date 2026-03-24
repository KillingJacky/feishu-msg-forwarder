from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AuthUrlResult:
    auth_url: str
    state: str
    redirect_uri: str


@dataclass(slots=True)
class TokenBundle:
    access_token: str
    refresh_token: str
    token_type: str
    expires_at: str
    refresh_expires_at: str
    scope: str


@dataclass(slots=True)
class SourceConfig:
    chat_id: str
    name: str | None = None


@dataclass(slots=True)
class RuleConfig:
    rule_id: str
    enabled: bool
    source_chat_ids: list[str]
    target_chat_ids: list[str]
    sender_ids: list[str] = field(default_factory=list)
    robot_only: bool = False
    message_types: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    regexes: list[str] = field(default_factory=list)
    forward_mode: str = "preserve"
    append_source_info: bool = False


@dataclass(slots=True)
class AppConfig:
    app_id: str
    app_secret: str
    base_url: str
    redirect_uri: str
    token_file: str
    db_path: str
    poll_interval_seconds: int
    log_level: str
    sources: list[SourceConfig]
    rules: list[RuleConfig]


@dataclass(slots=True)
class NormalizedMessage:
    message_id: str
    source_chat_id: str
    sender_id: str | None
    sender_name: str | None
    sender_type: str | None
    is_bot: bool
    msg_type: str
    text: str | None
    raw_content: dict[str, Any] | None
    create_time_ms: int
    raw: dict[str, Any]


@dataclass(slots=True)
class MatchResult:
    rule_id: str
    target_chat_ids: list[str]
    forward_mode: str
    append_source_info: bool


@dataclass(slots=True)
class DeliveryTask:
    message_id: str
    rule_id: str
    target_chat_id: str
    forward_mode: str
    append_source_info: bool


@dataclass(slots=True)
class OutboundMessage:
    msg_type: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
