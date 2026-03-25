import logging
import time
from typing import Any

import httpx

from ..exceptions import ApiError, RetryableApiError

logger = logging.getLogger(__name__)


class BaseFeishuClient:
    def __init__(self, base_url: str, timeout: float = 20.0, token_manager: Any = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout)
        self.token_manager = token_manager

    def request(
        self,
        method: str,
        path: str,
        *,
        user_access_token: str | None = None,
        tenant_access_token: str | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: Any = None,
        retry: int = 2,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None
        
        current_user_token = user_access_token
        current_tenant_token = tenant_access_token

        for attempt in range(retry + 1):
            headers = {}
            if current_user_token:
                headers["Authorization"] = f"Bearer {current_user_token}"
            elif current_tenant_token:
                headers["Authorization"] = f"Bearer {current_tenant_token}"

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
                data_resp = resp.json()
                
                # 处理 Token 过期错误 (99991677)
                code = data_resp.get("code", 0)
                if code == 99991677:
                    if self.token_manager and attempt < retry:
                        if current_user_token:
                            logger.warning("飞书返回 Token 过期 (99991677)，正在强制刷新并重试 (attempt %d/%d)", attempt + 1, retry)
                            current_user_token = self.token_manager.get_user_access_token(force_refresh=True)
                            continue
                        elif current_tenant_token:
                            logger.warning("飞书返回 Tenant Token 过期 (99991677)，正在重置并重试 (attempt %d/%d)", attempt + 1, retry)
                            self.token_manager._tenant_token = None
                            current_tenant_token = self.token_manager.get_tenant_access_token()
                            continue
                    else:
                        logger.error("Token 过期且已达到最大重试次数或未配置 token_manager")

                if resp.status_code >= 500:
                    raise RetryableApiError(f"HTTP {resp.status_code}: {data_resp}")
                
                if code != 0:
                    message = data_resp.get("msg", "unknown error")
                    if code in {99991679}:
                        raise ApiError(f"飞书权限或授权错误: {message}")
                    raise ApiError(f"飞书接口错误: code={code} msg={message}")
                return data_resp
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
