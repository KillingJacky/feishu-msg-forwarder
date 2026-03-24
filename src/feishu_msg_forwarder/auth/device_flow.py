from __future__ import annotations

import base64
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx

from ..exceptions import AuthError
from ..models import TokenBundle


class DeviceAuthorization:
    def __init__(
        self,
        *,
        device_code: str,
        user_code: str,
        verification_uri: str,
        verification_uri_complete: str,
        expires_in: int,
        interval: int,
    ) -> None:
        self.device_code = device_code
        self.user_code = user_code
        self.verification_uri = verification_uri
        self.verification_uri_complete = verification_uri_complete
        self.expires_in = expires_in
        self.interval = interval


def resolve_device_auth_url(base_url: str) -> str:
    if not base_url or base_url == "https://open.feishu.cn":
        return "https://accounts.feishu.cn/oauth/v1/device_authorization"
    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    if host.startswith("open."):
        return f"{parsed.scheme}://accounts.{host[5:]}/oauth/v1/device_authorization"
    return "https://accounts.feishu.cn/oauth/v1/device_authorization"


def request_device_authorization(app_id: str, app_secret: str, base_url: str, scopes: list[str]) -> DeviceAuthorization:
    if "offline_access" not in scopes:
        scopes = [*scopes, "offline_access"]

    url = resolve_device_auth_url(base_url)
    basic = base64.b64encode(f"{app_id}:{app_secret}".encode("utf-8")).decode("ascii")
    data = {"client_id": app_id, "scope": " ".join(scopes)}
    headers = {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        response = httpx.post(url, data=data, headers=headers, timeout=20.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AuthError(f"设备授权请求失败: {exc}") from exc

    payload = response.json()
    if payload.get("error"):
        raise AuthError(f"设备授权失败: {payload.get('error_description') or payload['error']}")

    return DeviceAuthorization(
        device_code=payload["device_code"],
        user_code=payload["user_code"],
        verification_uri=payload["verification_uri"],
        verification_uri_complete=payload.get("verification_uri_complete", payload["verification_uri"]),
        expires_in=int(payload.get("expires_in", 240)),
        interval=int(payload.get("interval", 5)),
    )


def poll_device_token(
    app_id: str,
    app_secret: str,
    base_url: str,
    device_code: str,
    interval: int,
    expires_in: int,
) -> TokenBundle:
    token_url = f"{base_url}/open-apis/authen/v2/oauth/token"
    deadline = time.time() + expires_in
    wait_seconds = max(interval, 1)
    while time.time() < deadline:
        time.sleep(wait_seconds)
        form = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
            "client_id": app_id,
            "client_secret": app_secret,
        }
        try:
            response = httpx.post(token_url, data=form, timeout=20.0)
            payload = response.json()
        except httpx.HTTPError as exc:
            raise AuthError(f"轮询设备授权 token 失败: {exc}") from exc

        error = payload.get("error", "")
        if not error and payload.get("access_token"):
            now = datetime.now(UTC)
            expires_at = now + timedelta(seconds=int(payload.get("expires_in", 7200)))
            refresh_expires = int(payload.get("refresh_token_expires_in", 0))
            refresh_expires_at = now + timedelta(seconds=refresh_expires) if refresh_expires else None
            return TokenBundle(
                access_token=payload["access_token"],
                refresh_token=payload.get("refresh_token", ""),
                token_type=payload.get("token_type", "Bearer"),
                expires_at=expires_at.isoformat(),
                refresh_expires_at=refresh_expires_at.isoformat() if refresh_expires_at else "",
                scope=payload.get("scope", ""),
            )

        if error == "authorization_pending":
            continue
        if error == "slow_down":
            wait_seconds = min(wait_seconds + 5, 60)
            continue
        if error == "access_denied":
            raise AuthError("用户拒绝了设备授权")
        if error in {"expired_token", "invalid_grant"}:
            raise AuthError("设备授权码已过期，请重新执行 auth login --method device")
        raise AuthError(f"轮询设备授权失败: {payload.get('error_description') or error or payload}")

    raise AuthError("设备授权超时，请重新执行 auth login --method device")
