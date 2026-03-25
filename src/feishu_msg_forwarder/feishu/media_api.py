from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path

from ..exceptions import ApiError
from .base_client import BaseFeishuClient


class MediaApi:
    def __init__(self, client: BaseFeishuClient) -> None:
        self.client = client

    def upload_image_from_path(self, access_token: str, file_path: str, is_tenant_token: bool = False) -> str:
        with open(file_path, "rb") as fp:
            data_payload = {"image_type": "message"}
            files = {"image": (Path(file_path).name, fp, "application/octet-stream")}
            
            kwargs = {"user_access_token": access_token} if not is_tenant_token else {"tenant_access_token": access_token}
            
            resp_data = self.client.request(
                "POST",
                "/open-apis/im/v1/images",
                data=data_payload,
                files=files,
                retry=1,
                **kwargs
            )
        image_key = ((resp_data.get("data") or {}).get("image_key")) or ""
        if not image_key:
            raise ApiError("上传图片成功但未返回 image_key")
        return image_key

    def upload_file_from_path(self, access_token: str, file_path: str, file_name: str | None = None, is_tenant_token: bool = False) -> str:
        actual_name = file_name or Path(file_path).name
        file_type = _guess_im_file_type(actual_name)
        with open(file_path, "rb") as fp:
            data_payload = {
                "file_type": file_type,
                "file_name": actual_name,
            }
            files = {
                "file": (actual_name, fp, "application/octet-stream"),
            }
            
            kwargs = {"user_access_token": access_token} if not is_tenant_token else {"tenant_access_token": access_token}

            resp_data = self.client.request(
                "POST",
                "/open-apis/im/v1/files",
                data=data_payload,
                files=files,
                retry=1,
                **kwargs
            )
        file_key = ((resp_data.get("data") or {}).get("file_key")) or ""
        if not file_key:
            raise ApiError("上传文件成功但未返回 file_key")
        return file_key

    def upload_image_from_base64(self, access_token: str, payload_b64: str, file_name: str = "image.bin", is_tenant_token: bool = False) -> str:
        with _MaterializedTempFile(payload_b64, file_name) as file_path:
            return self.upload_image_from_path(access_token, file_path, is_tenant_token=is_tenant_token)

    def upload_file_from_base64(self, access_token: str, payload_b64: str, file_name: str, is_tenant_token: bool = False) -> str:
        with _MaterializedTempFile(payload_b64, file_name) as file_path:
            return self.upload_file_from_path(access_token, file_path, file_name=file_name, is_tenant_token=is_tenant_token)

    def download_image(self, user_access_token: str, message_id: str, image_key: str) -> bytes:
        """Download image binary by message_id and image_key."""
        return self.client.download_bytes(
            f"/open-apis/im/v1/messages/{message_id}/resources/{image_key}",
            user_access_token=user_access_token,
            params={"type": "image"},
        )

    def download_file(self, user_access_token: str, message_id: str, file_key: str) -> bytes:
        """Download file binary by message_id and file_key."""
        return self.client.download_bytes(
            f"/open-apis/im/v1/messages/{message_id}/resources/{file_key}",
            user_access_token=user_access_token,
            params={"type": "file"},
        )


def _guess_im_file_type(file_name: str) -> str:
    ext = Path(file_name).suffix.lower()
    if ext == ".opus":
        return "opus"
    if ext == ".mp4":
        return "mp4"
    if ext == ".pdf":
        return "pdf"
    if ext in {".doc", ".docx"}:
        return "doc"
    if ext in {".xls", ".xlsx"}:
        return "xls"
    if ext in {".ppt", ".pptx"}:
        return "ppt"
    return "stream"


class _MaterializedTempFile:
    def __init__(self, payload_b64: str, file_name: str) -> None:
        self.payload_b64 = payload_b64
        self.file_name = file_name
        self.temp_path: str | None = None

    def __enter__(self) -> str:
        suffix = Path(self.file_name).suffix
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        Path(path).write_bytes(base64.b64decode(self.payload_b64))
        self.temp_path = path
        return path

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.temp_path and Path(self.temp_path).exists():
            Path(self.temp_path).unlink()
