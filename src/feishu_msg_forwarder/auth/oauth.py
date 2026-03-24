from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, quote, urlparse

import httpx

from ..exceptions import AuthError
from ..models import AuthUrlResult, TokenBundle


AUTH_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"


def generate_auth_url(app_id: str, redirect_uri: str, scopes: list[str]) -> AuthUrlResult:
    state = secrets.token_hex(32)
    auth_url = (
        f"{AUTH_URL}?client_id={quote(app_id, safe='')}&redirect_uri={quote(redirect_uri, safe='')}"
        f"&response_type=code&state={quote(state, safe='')}&scope={quote(' '.join(scopes), safe='')}"
    )
    return AuthUrlResult(auth_url=auth_url, state=state, redirect_uri=redirect_uri)


def parse_callback_url(callback_url: str, expected_state: str) -> str:
    parsed = urlparse(callback_url)
    query = parse_qs(parsed.query)
    if query.get("state", [""])[0] != expected_state:
        raise AuthError("state 不匹配")
    code = query.get("code", [""])[0]
    if not code:
        raise AuthError("回调地址缺少 code")
    return code


def exchange_code_for_token(base_url: str, app_id: str, app_secret: str, code: str, redirect_uri: str) -> TokenBundle:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": app_id,
        "client_secret": app_secret,
        "redirect_uri": redirect_uri,
    }
    return _request_token(base_url, payload)


def refresh_access_token(base_url: str, app_id: str, app_secret: str, refresh_token: str) -> TokenBundle:
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": app_id,
        "client_secret": app_secret,
    }
    return _request_token(base_url, payload)


def _request_token(base_url: str, payload: dict) -> TokenBundle:
    url = f"{base_url}/open-apis/authen/v2/oauth/token"
    try:
        response = httpx.post(url, json=payload, timeout=20.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AuthError(f"token 请求失败: {exc}") from exc

    data = response.json()
    if data.get("error"):
        raise AuthError(f"获取 token 失败: {json.dumps(data, ensure_ascii=False)}")
    if not data.get("access_token"):
        raise AuthError("响应中缺少 access_token")

    now = datetime.now(UTC)
    expires_in = int(data.get("expires_in", 0))
    refresh_expires_in = int(data.get("refresh_token_expires_in", 0))
    return TokenBundle(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", ""),
        token_type=data.get("token_type", "Bearer"),
        expires_at=(now + timedelta(seconds=expires_in)).isoformat(),
        refresh_expires_at=(now + timedelta(seconds=refresh_expires_in)).isoformat() if refresh_expires_in else "",
        scope=data.get("scope", ""),
    )
