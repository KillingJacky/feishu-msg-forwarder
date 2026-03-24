from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from ..db.repositories import Repository
from ..exceptions import ApiError
from ..feishu.media_api import MediaApi
from ..feishu.message_api import MessageApi
from ..models import NormalizedMessage, OutboundMessage
from .transformer import to_outbound_message

logger = logging.getLogger(__name__)


class Forwarder:
    def __init__(self, repo: Repository, message_api: MessageApi, media_api: MediaApi, user_access_token: str, tenant_access_token: str) -> None:
        self.repo = repo
        self.message_api = message_api
        self.media_api = media_api
        self.user_access_token = user_access_token
        self.tenant_access_token = tenant_access_token

    def process_pending(self) -> None:
        rows = self.repo.fetch_pending_deliveries()
        for row in rows:
            self.repo.mark_delivery_attempt(row["id"])
            try:
                raw_content = json.loads(row["raw_content_json"]) if row["raw_content_json"] else None
                message = NormalizedMessage(
                    message_id=row["message_id"],
                    source_chat_id=row["source_chat_id"],
                    sender_id=None,
                    sender_name=row["sender_name"],
                    sender_type=None,
                    is_bot=False,
                    msg_type=row["msg_type"],
                    text=row["normalized_text"],
                    raw_content=raw_content,
                    create_time_ms=0,
                    raw={},
                )
                append_source_info = bool(row["append_source_info"])
                resp = self._send_with_fallback(
                    message=message,
                    target_chat_id=row["target_chat_id"],
                    forward_mode=row["forward_mode"],
                    append_source_info=append_source_info,
                )
                target_message_id = ((resp.get("data") or {}).get("message_id")) or ""
                self.repo.mark_delivery_sent(row["id"], target_message_id)
                logger.info("转发成功 source_message_id=%s target_chat_id=%s", row["message_id"], row["target_chat_id"])
            except ApiError as exc:
                self.repo.mark_delivery_failed(row["id"], str(exc))
                logger.warning(
                    "转发失败 source_message_id=%s target_chat_id=%s error=%s",
                    row["message_id"],
                    row["target_chat_id"],
                    exc,
                )

    def _send_with_fallback(
        self,
        *,
        message: NormalizedMessage,
        target_chat_id: str,
        forward_mode: str,
        append_source_info: bool,
    ) -> dict:
        # 飞书原生“转发消息”接口限制：仅支持 tenant_access_token。
        # 如果调用该接口，消息发送者会强制变成机器人（Bot），这违背了我们“以用户身份转发”的需求。
        # 因此，这里彻底弃用原生转发接口，统一使用 user_access_token 重新构建和发送消息。
        outbound = to_outbound_message(message, forward_mode, append_source_info=append_source_info)
        try:
            return self._send_outbound(target_chat_id, outbound)
        except ApiError as first_error:
            logger.info("自定义发送失败 source_message_id=%s target_chat_id=%s error=%s", message.message_id, target_chat_id, first_error)
            if forward_mode == "preserve":
                reuploaded = self._try_media_reupload(message)
                if reuploaded is not None:
                    try:
                        logger.info("原素材复用失败，改为重新上传后发送 source_message_id=%s target_chat_id=%s", message.message_id, target_chat_id)
                        return self._send_outbound(target_chat_id, reuploaded)
                    except ApiError:
                        pass
                fallback = to_outbound_message(message, "text", append_source_info=append_source_info)
                logger.info("自定义发送失败，降级文本发送 source_message_id=%s target_chat_id=%s", message.message_id, target_chat_id)
                return self._send_outbound(target_chat_id, fallback)
            raise first_error

    def _send_outbound(self, target_chat_id: str, outbound: OutboundMessage) -> dict:
        return self.message_api.send_message(
            self.user_access_token,
            receive_id=target_chat_id,
            msg_type=outbound.msg_type,
            content=outbound.content,
        )

    def _try_media_reupload(self, message: NormalizedMessage) -> OutboundMessage | None:
        if message.raw_content is None:
            return None

        if message.msg_type == "image":
            image_key = message.raw_content.get("image_key")
            local_path = message.raw_content.get("local_path")
            image_bytes_b64 = message.raw_content.get("image_bytes_b64")

            # 优先用本地已有的资源
            if local_path:
                new_key = self.media_api.upload_image_from_path(self.tenant_access_token, local_path)
            elif image_bytes_b64:
                new_key = self.media_api.upload_image_from_base64(self.tenant_access_token, image_bytes_b64)
            elif image_key:
                # 从飞书下载原图再重新上传（下载用 user token，上传用 tenant token）
                logger.info("下载原图并重新上传 message_id=%s image_key=%s", message.message_id, image_key)
                image_bytes = self.media_api.download_image(self.user_access_token, message.message_id, image_key)
                tmp_path = _write_temp_file(image_bytes, ".png")
                try:
                    new_key = self.media_api.upload_image_from_path(self.tenant_access_token, tmp_path)
                finally:
                    Path(tmp_path).unlink(missing_ok=True)
            else:
                return None
            return OutboundMessage(msg_type="image", content=json.dumps({"image_key": new_key}, ensure_ascii=False))

        if message.msg_type == "file":
            file_key = message.raw_content.get("file_key")
            file_name = message.raw_content.get("file_name") or "file.bin"
            local_path = message.raw_content.get("local_path")
            file_bytes_b64 = message.raw_content.get("file_bytes_b64")

            if local_path:
                new_key = self.media_api.upload_file_from_path(self.tenant_access_token, local_path, file_name=file_name)
            elif file_bytes_b64:
                new_key = self.media_api.upload_file_from_base64(self.tenant_access_token, file_bytes_b64, file_name=file_name)
            elif file_key:
                # 从飞书下载原文件再重新上传（下载用 user token，上传用 tenant token）
                logger.info("下载原文件并重新上传 message_id=%s file_key=%s", message.message_id, file_key)
                file_bytes = self.media_api.download_file(self.user_access_token, message.message_id, file_key)
                suffix = Path(file_name).suffix or ".bin"
                tmp_path = _write_temp_file(file_bytes, suffix)
                try:
                    new_key = self.media_api.upload_file_from_path(self.tenant_access_token, tmp_path, file_name=file_name)
                finally:
                    Path(tmp_path).unlink(missing_ok=True)
            else:
                return None
            return OutboundMessage(
                msg_type="file",
                content=json.dumps({"file_key": new_key, "file_name": file_name}, ensure_ascii=False),
            )

        if message.msg_type == "post":
            import copy

            post_content = copy.deepcopy(message.raw_content)
            modified = False

            def traverse(node: Any) -> None:
                nonlocal modified
                if isinstance(node, dict):
                    if node.get("tag") == "img" and "image_key" in node:
                        old_key = node["image_key"]
                        logger.info("富文本内嵌图片：下载并重新上传 message_id=%s image_key=%s", message.message_id, old_key)
                        try:
                            image_bytes = self.media_api.download_image(self.user_access_token, message.message_id, old_key)
                            tmp_path = _write_temp_file(image_bytes, ".png")
                            try:
                                new_key = self.media_api.upload_image_from_path(self.tenant_access_token, tmp_path)
                                node["image_key"] = new_key
                                modified = True
                            finally:
                                Path(tmp_path).unlink(missing_ok=True)
                        except Exception as e:
                            logger.error("富文本图片下载重传失败 image_key=%s err=%s", old_key, e)
                    else:
                        for v in node.values():
                            traverse(v)
                elif isinstance(node, list):
                    for item in node:
                        traverse(item)

            traverse(post_content)
            if modified:
                if "content" in post_content and not any(k in post_content for k in ("zh_cn", "en_us")):
                    post_content = {"zh_cn": post_content}
                return OutboundMessage(msg_type="post", content=json.dumps(post_content, ensure_ascii=False))

        return None


def _write_temp_file(data: bytes, suffix: str) -> str:
    """Write bytes to a temp file and return the path."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    Path(path).write_bytes(data)
    return path
