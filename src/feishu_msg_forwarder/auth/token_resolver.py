from __future__ import annotations

import logging
import os

from ..exceptions import AuthError
from ..models import AppConfig
from .oauth import refresh_access_token
from .token_store import access_token_valid, load_token, refresh_token_valid, save_token

logger = logging.getLogger(__name__)


def resolve_user_access_token(config: AppConfig, explicit_token: str | None = None) -> str:
    if explicit_token:
        return explicit_token
    env_token = os.getenv("FEISHU_USER_ACCESS_TOKEN")
    if env_token:
        return env_token

    token = load_token(config.token_file)
    if token is None:
        raise AuthError("未找到本地 token，请先执行 auth login")
    if access_token_valid(token):
        return token.access_token
    if refresh_token_valid(token):
        logger.info("access token 已过期，正在自动刷新")
        refreshed = refresh_access_token(config.base_url, config.app_id, config.app_secret, token.refresh_token)
        save_token(config.token_file, refreshed)
        return refreshed.access_token
    raise AuthError("refresh token 已失效，请重新授权登录")


def resolve_tenant_access_token(config: AppConfig) -> str:
    """通过 app_id + app_secret 获取 tenant_access_token（用于文件/图片上传等接口）。"""
    import httpx

    url = f"{config.base_url}/open-apis/auth/v3/tenant_access_token/internal"
    resp = httpx.post(url, json={"app_id": config.app_id, "app_secret": config.app_secret}, timeout=20.0)
    data = resp.json()
    if data.get("code", -1) != 0:
        raise AuthError(f"获取 tenant_access_token 失败: {data.get('msg', 'unknown')}")
    tenant_token = data.get("tenant_access_token", "")
    if not tenant_token:
        raise AuthError("响应中缺少 tenant_access_token")
    logger.info("已获取 tenant_access_token")
    return tenant_token
