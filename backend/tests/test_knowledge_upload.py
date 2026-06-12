from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from fastapi import UploadFile

from app.api.knowledge import _save_upload_file


class SaveUploadFileTests(IsolatedAsyncioTestCase):
    async def test_save_upload_file_sanitizes_filename(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            target_dir = Path(tmp_dir)
            upload = UploadFile(
                filename="../恶意 文件?.md",
                file=BytesIO("测试内容".encode("utf-8")),
            )

            saved_path = await _save_upload_file(upload, target_dir)

            self.assertEqual(saved_path, target_dir / "恶意_文件_.md")
            self.assertTrue(saved_path.exists())
            self.assertEqual(saved_path.read_text(encoding="utf-8"), "测试内容")
            self.assertFalse((target_dir.parent / "恶意 文件?.md").exists())
