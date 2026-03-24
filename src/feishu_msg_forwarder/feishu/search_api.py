from __future__ import annotations

from .base_client import BaseFeishuClient


class SearchApi:
    def __init__(self, client: BaseFeishuClient) -> None:
        self.client = client

    def search_messages(
        self,
        user_access_token: str,
        *,
        query: str,
        chat_ids: list[str],
        page_size: int = 50,
        page_token: str | None = None,
    ) -> dict:
        params = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        return self.client.request(
            "POST",
            "/open-apis/search/v2/message",
            user_access_token=user_access_token,
            params=params,
            json_body={"query": query, "chat_ids": chat_ids},
        )
