from __future__ import annotations

import json
from typing import Any

from ..models import NormalizedMessage, OutboundMessage


def normalize_message(item: dict[str, Any], source_chat_id: str) -> NormalizedMessage:
    sender = item.get("sender") or {}
    sender_id = sender.get("id")
    sender_type = sender.get("sender_type")
    sender_name = sender.get("sender_name") or sender.get("name")
    msg_type = item.get("msg_type", "unknown")
    raw_content = _parse_json(item.get("body", {}).get("content"))
    text = _extract_text(msg_type, raw_content)
    create_time_ms = int(item.get("create_time") or 0)
    return NormalizedMessage(
        message_id=item["message_id"],
        source_chat_id=source_chat_id,
        sender_id=sender_id,
        sender_name=sender_name,
        sender_type=sender_type,
        is_bot=(sender_type == "app"),
        msg_type=msg_type,
        text=text,
        raw_content=raw_content,
        create_time_ms=create_time_ms,
        raw=item,
    )


def to_outbound_message(message: NormalizedMessage, forward_mode: str, append_source_info: bool) -> OutboundMessage:
    if forward_mode == "preserve":
        preserved = _preserve_message(message)
        if preserved is not None:
            return preserved
    fallback_text = _build_fallback_text(message, append_source_info)
    return OutboundMessage(msg_type="text", content=json.dumps({"text": fallback_text}, ensure_ascii=False))


def _preserve_message(message: NormalizedMessage) -> OutboundMessage | None:
    if message.raw_content is None:
        return None
    if message.msg_type == "text" and "text" in message.raw_content:
        return OutboundMessage(msg_type="text", content=json.dumps({"text": message.raw_content["text"]}, ensure_ascii=False))
    if message.msg_type == "post":
        if any(key in message.raw_content for key in ("zh_cn", "en_us")):
            # 已经是合法的多语言 post 结构
            return OutboundMessage(msg_type="post", content=json.dumps(message.raw_content, ensure_ascii=False))
        # 如果收到的是扁平的 {"title": "...", "content": [...]}, 需用 zh_cn 包裹
        if "content" in message.raw_content:
            wrapped = {"zh_cn": message.raw_content}
            return OutboundMessage(msg_type="post", content=json.dumps(wrapped, ensure_ascii=False))
        return None
    if message.msg_type == "image" and "image_key" in message.raw_content:
        metadata = {
            "image_key": message.raw_content["image_key"],
            "local_path": message.raw_content.get("local_path"),
            "image_bytes_b64": message.raw_content.get("image_bytes_b64"),
        }
        return OutboundMessage(
            msg_type="image",
            content=json.dumps({"image_key": message.raw_content["image_key"]}, ensure_ascii=False),
            metadata=metadata,
        )
    if message.msg_type == "file" and "file_key" in message.raw_content:
        payload = {"file_key": message.raw_content["file_key"]}
        if "file_name" in message.raw_content:
            payload["file_name"] = message.raw_content["file_name"]
        metadata = {
            "file_key": message.raw_content["file_key"],
            "file_name": message.raw_content.get("file_name"),
            "local_path": message.raw_content.get("local_path"),
            "file_bytes_b64": message.raw_content.get("file_bytes_b64"),
        }
        return OutboundMessage(msg_type="file", content=json.dumps(payload, ensure_ascii=False), metadata=metadata)
    return None


def _build_fallback_text(message: NormalizedMessage, append_source_info: bool) -> str:
    lines = []
    if append_source_info:
        lines.append(f"[来源群: {message.source_chat_id}]")
    if message.sender_name:
        lines.append(f"[发送者: {message.sender_name}]")
    lines.append(f"[类型: {message.msg_type}]")
    lines.append(message.text or "原消息无法原样转发，已降级为文本摘要。")
    return "\n".join(lines)


def _parse_json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def _extract_text(msg_type: str, raw_content: dict[str, Any] | None) -> str | None:
    if raw_content is None:
        return None
    if msg_type == "text":
        return raw_content.get("text")
    if msg_type == "post":
        return _extract_post_text(raw_content)
    if "text" in raw_content:
        return str(raw_content["text"])
    return None


def _extract_post_text(raw_content: dict[str, Any]) -> str:
    texts: list[str] = []
    
    # 兼容扁平和多语言包裹的结构
    payloads = []
    if any(key in raw_content for key in ("zh_cn", "en_us")):
        payloads = [p for p in raw_content.values() if isinstance(p, dict)]
    else:
        payloads = [raw_content]

    for locale_payload in payloads:
        title = locale_payload.get("title")
        if title:
            texts.append(str(title))
        for line in locale_payload.get("content", []):
            if not isinstance(line, list):
                continue
            for block in line:
                if isinstance(block, dict) and "text" in block:
                    texts.append(str(block["text"]))
    
    if texts:
        return "\n".join(texts)
    return json.dumps(raw_content, ensure_ascii=False)
