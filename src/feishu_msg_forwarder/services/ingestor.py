from __future__ import annotations

import logging

from ..db.repositories import Repository
from ..models import DeliveryTask, RuleConfig
from ..rules.matcher import match_rules
from .transformer import normalize_message

logger = logging.getLogger(__name__)


class Ingestor:
    def __init__(self, repo: Repository, rules: list[RuleConfig]) -> None:
        self.repo = repo
        self.rules = rules

    def ingest_items(self, source_chat_id: str, items: list[dict]) -> None:
        for item in items:
            if "message_id" not in item:
                continue
            message = normalize_message(item, source_chat_id)
            is_new = self.repo.ingest_message(message)
            if not is_new:
                continue
            logger.debug(
                "收录新消息: message_id=%s sender_type=%s sender_id=%s is_bot=%s",
                message.message_id,
                message.sender_type,
                message.sender_id,
                message.is_bot,
            )
            matches = match_rules(message, self.rules)
            for match in matches:
                self.repo.record_match(message.message_id, match)
                for target_chat_id in match.target_chat_ids:
                    created = self.repo.create_delivery_if_needed(
                        DeliveryTask(
                            message_id=message.message_id,
                            rule_id=match.rule_id,
                            target_chat_id=target_chat_id,
                            forward_mode=match.forward_mode,
                            append_source_info=match.append_source_info,
                        )
                    )
                    if created:
                        logger.info(
                            "创建转发任务 message_id=%s rule_id=%s target_chat_id=%s orig_info: sender_type=%s sender_id=%s is_bot=%s",
                            message.message_id,
                            match.rule_id,
                            target_chat_id,
                            message.sender_type,
                            message.sender_id,
                            message.is_bot,
                        )
