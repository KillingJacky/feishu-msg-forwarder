from __future__ import annotations

import logging
import re

from ..models import MatchResult, NormalizedMessage, RuleConfig

logger = logging.getLogger(__name__)


def match_rules(message: NormalizedMessage, rules: list[RuleConfig]) -> list[MatchResult]:
    results: list[MatchResult] = []
    
    for rule in rules:
        if not rule.enabled:
            logger.debug("规则 [%s] 被跳过：规则已禁用", rule.rule_id)
            continue
        if message.source_chat_id not in rule.source_chat_ids:
            # 基础路由不匹配的情况极其频繁（每条消息都会扫一边），在此静默跳过即可
            continue
            
        logger.debug("正在基于规则 [%s] 评估消息 %s ...", rule.rule_id, message.message_id)
            
        if rule.sender_ids and message.sender_id not in rule.sender_ids:
            logger.debug("❌ 规则 [%s] 失败：发送者 ID (%s) 不在允许列表内", rule.rule_id, message.sender_id)
            continue
        if rule.robot_only and not message.is_bot:
            logger.debug("❌ 规则 [%s] 失败：该规则仅允许机器人发送，当前为用户发送", rule.rule_id)
            continue
        if rule.message_types and message.msg_type not in rule.message_types:
            logger.debug("❌ 规则 [%s] 失败：消息类型 (%s) 不在允许类别中 %s", rule.rule_id, message.msg_type, rule.message_types)
            continue
            
        haystack = message.text or ""
        if rule.keywords and not all(keyword in haystack for keyword in rule.keywords):
            logger.debug("❌ 规则 [%s] 失败：消息文本未全部包含要求的关键字 %s", rule.rule_id, rule.keywords)
            continue
        if rule.regexes and not all(re.search(pattern, haystack) for pattern in rule.regexes):
            logger.debug("❌ 规则 [%s] 失败：消息文本未能满足全部正则表达式 %s", rule.rule_id, rule.regexes)
            continue
            
        logger.debug("✅ 规则 [%s] 完全命中！准备下发至目标群: %s", rule.rule_id, rule.target_chat_ids)
        results.append(
            MatchResult(
                rule_id=rule.rule_id,
                target_chat_ids=rule.target_chat_ids,
                forward_mode=rule.forward_mode,
                append_source_info=rule.append_source_info,
            )
        )
    return results
