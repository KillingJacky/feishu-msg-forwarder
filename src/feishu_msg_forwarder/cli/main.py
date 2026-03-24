from __future__ import annotations

import json
from dataclasses import asdict
from urllib.parse import urlparse

import typer

from ..auth.callback_server import wait_for_callback
from ..auth.device_flow import poll_device_token, request_device_authorization
from ..auth.oauth import exchange_code_for_token, generate_auth_url, parse_callback_url
from ..auth.token_store import load_token, save_token
from ..config import load_config
from ..logging_setup import setup_logging
from ..services.bootstrap import build_runtime

app = typer.Typer(help="Feishu 消息转发器")
auth_app = typer.Typer(help="认证相关命令")
run_app = typer.Typer(help="运行相关命令")
app.add_typer(auth_app, name="auth")
app.add_typer(run_app, name="run")

DEFAULT_SCOPES = [
    "offline_access",
    "im:message:readonly",
    "im:message.group_msg:get_as_user",
    "im:chat:read",
    "search:message",
]


@auth_app.command("login")
def auth_login(
    config_file: str | None = typer.Option(None, "--config-file"),
    method: str = typer.Option("code", "--method"),
    timeout: int = typer.Option(120, "--timeout", help="等待回调的超时秒数"),
) -> None:
    config = load_config(config_file)
    if method == "device":
        device = request_device_authorization(config.app_id, config.app_secret, config.base_url, DEFAULT_SCOPES)
        typer.echo(
            json.dumps(
                {
                    "method": "device",
                    "verification_uri": device.verification_uri,
                    "verification_uri_complete": device.verification_uri_complete,
                    "user_code": device.user_code,
                    "expires_in": device.expires_in,
                    "interval": device.interval,
                    "device_code": device.device_code,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    # --- 授权码流程：自动启动回调服务器 + 打开浏览器 ---
    result = generate_auth_url(config.app_id, config.redirect_uri, DEFAULT_SCOPES)

    # 从 redirect_uri 解析 host 和 port
    parsed_redirect = urlparse(config.redirect_uri)
    cb_host = parsed_redirect.hostname or "127.0.0.1"
    cb_port = parsed_redirect.port or 9768

    typer.echo(f"正在启动本地回调服务器 http://{cb_host}:{cb_port}/callback ...")
    typer.echo(f"正在打开浏览器进行飞书授权 ...")
    typer.echo(f"（如浏览器未自动打开，请手动访问以下地址）")
    typer.echo(result.auth_url)
    typer.echo(f"")
    typer.echo(f"💡 【如果在远程服务器部署，或稍后需手动执行回调】请复制以下 state 值备用：")
    typer.echo(f"    state: {result.state}")
    typer.echo(f"")

    # 打开浏览器
    import webbrowser
    webbrowser.open(result.auth_url)

    # 等待回调
    try:
        # 强制绑定 0.0.0.0 以便在 Docker 环境下接受宿主机的映射端口转发
        callback_result = wait_for_callback(host="0.0.0.0", port=cb_port, timeout=timeout)
    except TimeoutError:
        typer.echo("❌ 等待授权回调超时，请重试", err=True)
        raise typer.Exit(1)

    code = callback_result.get("code", "")
    state = callback_result.get("state", "")
    if state != result.state:
        typer.echo("❌ state 不匹配，可能存在安全风险", err=True)
        raise typer.Exit(1)
    if not code:
        typer.echo("❌ 回调中没有 code 参数", err=True)
        raise typer.Exit(1)

    # 换取 token
    token = exchange_code_for_token(config.base_url, config.app_id, config.app_secret, code, config.redirect_uri)
    save_token(config.token_file, token)
    typer.echo("✅ 授权成功，token 已保存")


@auth_app.command("device-complete")
def auth_device_complete(
    device_code: str = typer.Option(..., "--device-code"),
    interval: int = typer.Option(5, "--interval"),
    expires_in: int = typer.Option(240, "--expires-in"),
    config_file: str | None = typer.Option(None, "--config-file"),
) -> None:
    config = load_config(config_file)
    token = poll_device_token(
        config.app_id,
        config.app_secret,
        config.base_url,
        device_code=device_code,
        interval=interval,
        expires_in=expires_in,
    )
    save_token(config.token_file, token)
    typer.echo("设备授权成功，token 已保存")


@auth_app.command("callback")
def auth_callback(
    callback_url: str | None = typer.Argument(None, help="浏览器跳转后的完整URL"),
    state: str | None = typer.Option(None, "--state", help="第一步生成的state值"),
    config_file: str | None = typer.Option(None, "--config-file"),
) -> None:
    if callback_url is None:
        callback_url = typer.prompt("🌍 请粘贴授权失败页面的完整回调 URL（含 code= 等）")
    if state is None:
        state = typer.prompt("🔑 请输入你在上一步获取的 state 值")

    config = load_config(config_file)
    code = parse_callback_url(callback_url, state)
    token = exchange_code_for_token(config.base_url, config.app_id, config.app_secret, code, config.redirect_uri)
    save_token(config.token_file, token)
    typer.echo("✅ 手动授权成功，凭据已经保存。")


@auth_app.command("status")
def auth_status(config_file: str | None = typer.Option(None, "--config-file")) -> None:
    config = load_config(config_file)
    token = load_token(config.token_file)
    if token is None:
        typer.echo(json.dumps({"logged_in": False}, ensure_ascii=False, indent=2))
        return
    typer.echo(
        json.dumps(
            {
                "logged_in": True,
                "expires_at": token.expires_at,
                "refresh_expires_at": token.refresh_expires_at,
                "scope": token.scope,
                "token_file": config.token_file,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@run_app.command("once")
def run_once(config_file: str | None = typer.Option(None, "--config-file")) -> None:
    config = load_config(config_file)
    setup_logging(config.log_level)
    poller = build_runtime(config_file)
    poller.run_once()


@run_app.command("poll")
def run_poll(config_file: str | None = typer.Option(None, "--config-file")) -> None:
    config = load_config(config_file)
    setup_logging(config.log_level)
    poller = build_runtime(config_file)
    poller.run_forever()


if __name__ == "__main__":
    app()
