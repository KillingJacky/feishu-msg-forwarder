from __future__ import annotations

from .base_client import BaseFeishuClient


class ChatApi:
    def __init__(self, client: BaseFeishuClient) -> None:
        self.client = client

    def search_chats(self, user_access_token: str, query: str = "", page_size: int = 100, page_token: str = "") -> dict:
        if query:
            return self.client.request(
                "GET",
                "/open-apis/im/v1/chats/search",
                user_access_token=user_access_token,
                params={"query": query, "page_size": page_size, "page_token": page_token},
            )
        return self.client.request(
            "GET",
            "/open-apis/im/v1/chats",
            user_access_token=user_access_token,
            params={"page_size": page_size, "page_token": page_token},
        )
