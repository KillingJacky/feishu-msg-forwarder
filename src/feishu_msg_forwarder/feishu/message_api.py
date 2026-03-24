from __future__ import annotations

from .base_client import BaseFeishuClient


class MessageApi:
    def __init__(self, client: BaseFeishuClient) -> None:
        self.client = client

    def list_messages(
        self,
        user_access_token: str,
        container_id: str,
        *,
        container_id_type: str = "chat",
        start_time: str | None = None,
        end_time: str | None = None,
        sort_type: str = "ByCreateTimeAsc",
        page_size: int = 50,
        page_token: str | None = None,
    ) -> dict:
        params = {
            "container_id_type": container_id_type,
            "container_id": container_id,
            "sort_type": sort_type,
            "page_size": page_size,
        }
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        if page_token:
            params["page_token"] = page_token
        return self.client.request("GET", "/open-apis/im/v1/messages", user_access_token=user_access_token, params=params)

    def get_message(self, user_access_token: str, message_id: str) -> dict:
        return self.client.request("GET", f"/open-apis/im/v1/messages/{message_id}", user_access_token=user_access_token)

    def send_message(self, user_access_token: str, receive_id: str, msg_type: str, content: str) -> dict:
        return self.client.request(
            "POST",
            "/open-apis/im/v1/messages",
            user_access_token=user_access_token,
            params={"receive_id_type": "chat_id"},
            json_body={"receive_id": receive_id, "msg_type": msg_type, "content": content},
        )

    def forward_message(self, user_access_token: str, message_id: str, receive_id: str) -> dict:
        return self.client.request(
            "POST",
            f"/open-apis/im/v1/messages/{message_id}/forward",
            user_access_token=user_access_token,
            params={"receive_id_type": "chat_id"},
            json_body={"receive_id": receive_id},
        )
