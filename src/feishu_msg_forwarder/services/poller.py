from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from ..models import AppConfig
from .transformer import normalize_message

logger = logging.getLogger(__name__)


class Poller:
    def __init__(self, config: AppConfig, repo, ingestor, forwarder, message_api, search_api, user_access_token: str) -> None:
        self.config = config
        self.repo = repo
        self.ingestor = ingestor
        self.forwarder = forwarder
        self.message_api = message_api
        self.search_api = search_api
        self.user_access_token = user_access_token

    def run_forever(self) -> None:
        while True:
            self.run_once()
            time.sleep(self.config.poll_interval_seconds)

    def run_once(self) -> None:
        for source in self.config.sources:
            initial_baseline = int(datetime.now(UTC).timestamp() * 1000)
            cursor_ms, cursor_ids = self.repo.get_source_cursor(source.chat_id, initial_baseline)
            items = self._fetch_messages(source.chat_id, cursor_ms)
            filtered_items, next_cursor_ms, next_cursor_ids = self._filter_by_cursor(source.chat_id, items, cursor_ms, cursor_ids)
            self.ingestor.ingest_items(source.chat_id, filtered_items)
            self.repo.update_source_cursor(source.chat_id, next_cursor_ms, next_cursor_ids)
        self.forwarder.process_pending()

    def _fetch_messages(self, chat_id: str, baseline_ms: int) -> list[dict]:
        try:
            start_time_sec = baseline_ms // 1000
            end_time_sec = int(datetime.now(UTC).timestamp())
            data = self.message_api.list_messages(
                self.user_access_token,
                chat_id,
                start_time=str(start_time_sec),
                end_time=str(end_time_sec),
                sort_type="ByCreateTimeAsc",
                page_size=50,
            )
            return (data.get("data") or {}).get("items") or []
        except Exception as exc:
            logger.warning("主读取路径失败，切换兜底 chat_id=%s error=%s", chat_id, exc)
        return self._fetch_messages_via_search(chat_id)

    def _fetch_messages_via_search(self, chat_id: str) -> list[dict]:
        try:
            data = self.search_api.search_messages(self.user_access_token, query=" ", chat_ids=[chat_id], page_size=50)
            message_ids = (data.get("data") or {}).get("items") or []
            items: list[dict] = []
            for message_id in message_ids:
                detail = self.message_api.get_message(self.user_access_token, message_id)
                detail_items = (detail.get("data") or {}).get("items") or []
                items.extend(detail_items)
            return items
        except Exception as exc:
            logger.warning("搜索兜底路径失败（可能缺少 search:message 权限），chat_id=%s error=%s", chat_id, exc)
            return []

    def _filter_by_cursor(
        self,
        chat_id: str,
        items: list[dict],
        cursor_ms: int,
        cursor_ids: set[str],
    ) -> tuple[list[dict], int, set[str]]:
        normalized = []
        for item in items:
            if "message_id" not in item:
                continue
            message = normalize_message(item, chat_id)
            normalized.append((message.create_time_ms, message.message_id, item))

        normalized.sort(key=lambda x: (x[0], x[1]))

        filtered: list[dict] = []
        latest_ms = cursor_ms
        latest_ids = set(cursor_ids)

        for create_time_ms, message_id, item in normalized:
            if create_time_ms < cursor_ms:
                continue
            if create_time_ms == cursor_ms and message_id in cursor_ids:
                continue
            filtered.append(item)
            if create_time_ms > latest_ms:
                latest_ms = create_time_ms
                latest_ids = {message_id}
            elif create_time_ms == latest_ms:
                latest_ids.add(message_id)

        return filtered, latest_ms, latest_ids
