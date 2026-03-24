from __future__ import annotations

import time
from typing import Any

import httpx

from ..exceptions import ApiError, RetryableApiError


class BaseFeishuClient:
    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout)

    def request(
        self,
        method: str,
        path: str,
        *,
        user_access_token: str | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: Any = None,
        retry: int = 2,
    ) -> dict[str, Any]:
        headers = {}
        if user_access_token:
            headers["Authorization"] = f"Bearer {user_access_token}"

        url = f"{self.base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(retry + 1):
            try:
                resp = self.client.request(
                    method, 
                    url, 
                    headers=headers, 
                    params=params, 
                    json=json_body, 
                    data=data,
                    files=files
                )
                data = resp.json()
                if resp.status_code >= 500:
                    raise RetryableApiError(f"HTTP {resp.status_code}: {data}")
                if data.get("code", 0) != 0:
                    message = data.get("msg", "unknown error")
                    if data.get("code") in {99991679}:
                        raise ApiError(f"飞书权限或授权错误: {message}")
                    raise ApiError(f"飞书接口错误: code={data.get('code')} msg={message}")
                return data
            except RetryableApiError as exc:
                last_error = exc
                if attempt == retry:
                    break
                time.sleep(1 + attempt)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == retry:
                    break
                time.sleep(1 + attempt)
        raise ApiError(f"接口请求失败: {last_error}")

    def download_bytes(
        self,
        path: str,
        *,
        user_access_token: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> bytes:
        """Download binary content (e.g. files, images) from Feishu API."""
        headers = {}
        if user_access_token:
            headers["Authorization"] = f"Bearer {user_access_token}"
        url = f"{self.base_url}{path}"
        try:
            resp = self.client.request("GET", url, headers=headers, params=params)
            if resp.status_code >= 400:
                raise ApiError(f"下载失败: HTTP {resp.status_code}")
            return resp.content
        except httpx.HTTPError as exc:
            raise ApiError(f"下载请求失败: {exc}") from exc
