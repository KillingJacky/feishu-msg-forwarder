from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

from ..exceptions import AuthError
from ..models import AppConfig
from .oauth import refresh_access_token
from .token_store import access_token_valid, load_token, refresh_token_valid, save_token

logger = logging.getLogger(__name__)


class TokenManager:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._tenant_token: str | None = None
        self._tenant_expires_at: datetime | None = None

    def get_user_access_token(self, explicit_token: str | None = None, force_refresh: bool = False) -> str:
        if explicit_token:
            return explicit_token
        env_token = os.getenv("FEISHU_USER_ACCESS_TOKEN")
        if env_token:
            return env_token

        token = load_token(self.config.token_file)
        if token is None:
            raise AuthError("未找到本地 token，请先执行 auth login")
        
        # 如果不是强制刷新，且 token 依然有效，直接返回
        if not force_refresh and access_token_valid(token):
            return token.access_token

        if refresh_token_valid(token):
            logger.info("access token 已过期或触发强制刷新，正在自动更新")
            refreshed = refresh_access_token(
                self.config.base_url,
                self.config.app_id,
                self.config.app_secret,
                token.refresh_token,
            )
            save_token(self.config.token_file, refreshed)
            return refreshed.access_token
        raise AuthError("refresh token 已失效，请重新授权登录")

    def get_tenant_access_token(self) -> str:
        now = datetime.now(UTC)
        if self._tenant_token and self._tenant_expires_at and now + timedelta(seconds=60) < self._tenant_expires_at:
            return self._tenant_token

        import httpx

        logger.info("正在获取新的 tenant_access_token")
        url = f"{self.config.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        resp = httpx.post(
            url,
            json={"app_id": self.config.app_id, "app_secret": self.config.app_secret},
            timeout=20.0,
        )
        data = resp.json()
        if data.get("code", -1) != 0:
            raise AuthError(f"获取 tenant_access_token 失败: {data.get('msg', 'unknown')}")
        
        tenant_token = data.get("tenant_access_token", "")
        expires_in = data.get("expire", 0)  # 飞书 tenant_access_token 接口返回 'expire'
        if not tenant_token:
            raise AuthError("响应中缺少 tenant_access_token")
        
        self._tenant_token = tenant_token
        self._tenant_expires_at = now + timedelta(seconds=expires_in)
        return tenant_token


def resolve_user_access_token(config: AppConfig, explicit_token: str | None = None) -> str:
    return TokenManager(config).get_user_access_token(explicit_token)


def resolve_tenant_access_token(config: AppConfig) -> str:
    return TokenManager(config).get_tenant_access_token()
