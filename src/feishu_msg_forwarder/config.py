from __future__ import annotations

import os
from pathlib import Path

import yaml

from .exceptions import ConfigError
from .models import AppConfig, RuleConfig, SourceConfig


def _default_data_dir() -> Path:
    return Path(os.getenv("FEISHU_DATA_DIR", "data"))


def load_config(config_file: str | None = None) -> AppConfig:
    data_dir = _default_data_dir()
    path = Path(config_file or os.getenv("FEISHU_CONFIG_FILE", data_dir / "config.yaml"))
    file_data: dict = {}
    if path.exists():
        file_data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    system = file_data.get("system", {})
    sources_data = file_data.get("sources", [])
    rules_data = file_data.get("rules", [])

    app_id = os.getenv("FEISHU_APP_ID", system.get("app_id", ""))
    app_secret = os.getenv("FEISHU_APP_SECRET", system.get("app_secret", ""))
    if not app_id or not app_secret:
        raise ConfigError("缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET")

    base_url = os.getenv("FEISHU_BASE_URL", system.get("base_url", "https://open.feishu.cn"))
    redirect_uri = os.getenv("FEISHU_REDIRECT_URI", system.get("redirect_uri", "http://127.0.0.1:9768/callback"))
    token_file = os.getenv("FEISHU_TOKEN_FILE", system.get("token_file", str(data_dir / "token.json")))
    db_path = os.getenv("FEISHU_DB_PATH", system.get("db_path", str(data_dir / "app.db")))
    poll_interval = int(os.getenv("FEISHU_POLL_INTERVAL_SECONDS", system.get("poll_interval_seconds", 15)))
    log_level = os.getenv("FEISHU_LOG_LEVEL", system.get("log_level", "INFO"))
    token_refresh_interval = int(os.getenv("FEISHU_TOKEN_REFRESH_INTERVAL_SECONDS", system.get("token_refresh_interval_seconds", 3600)))

    sources = [SourceConfig(chat_id=item["chat_id"], name=item.get("name")) for item in sources_data]
    if not sources:
        raise ConfigError("至少需要配置一个 source")

    rules = [
        RuleConfig(
            rule_id=item["rule_id"],
            enabled=bool(item.get("enabled", True)),
            source_chat_ids=list(item.get("source_chat_ids", [])),
            target_chat_ids=list(item.get("target_chat_ids", [])),
            sender_ids=list(item.get("sender_ids", [])),
            robot_only=bool(item.get("robot_only", False)),
            message_types=list(item.get("message_types", [])),
            keywords=list(item.get("keywords", [])),
            regexes=list(item.get("regexes", [])),
            forward_mode=item.get("forward_mode", "preserve"),
            append_source_info=bool(item.get("append_source_info", False)),
        )
        for item in rules_data
    ]
    if not rules:
        raise ConfigError("至少需要配置一条 rule")

    for rule in rules:
        if not rule.source_chat_ids:
            raise ConfigError(f"规则 {rule.rule_id} 缺少 source_chat_ids")
        if not rule.target_chat_ids:
            raise ConfigError(f"规则 {rule.rule_id} 缺少 target_chat_ids")
        if rule.forward_mode not in {"preserve", "text"}:
            raise ConfigError(f"规则 {rule.rule_id} 的 forward_mode 非法")

    return AppConfig(
        app_id=app_id,
        app_secret=app_secret,
        base_url=base_url.rstrip("/"),
        redirect_uri=redirect_uri,
        token_file=token_file,
        db_path=db_path,
        poll_interval_seconds=poll_interval,
        log_level=log_level,
        sources=sources,
        rules=rules,
        token_refresh_interval_seconds=token_refresh_interval,
    )
