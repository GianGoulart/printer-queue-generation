"""Local filesystem storage driver."""

import os
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List

import aiofiles

from app.storage.base import BaseStorageDriver, FileInfo, StorageError


class LocalStorageDriver(BaseStorageDriver):
    """Local filesystem storage driver.

    Configuration:
        base_path: Absolute path to storage directory

    Example:
        >>> driver = LocalStorageDriver({"base_path": "/data/assets/tenant-1"})
        >>> files = await driver.list_files()
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_path = Path(config["base_path"])

        # Ensure base_path is absolute for security
        if not self.base_path.is_absolute():
            self.base_path = self.base_path.resolve()

    def _validate_path(self, file_path: str) -> Path:
        """Validate path is within base_path (prevent directory traversal).

        Args:
            file_path: Relative file path

        Returns:
            Absolute Path object

        Raises:
            StorageError: If path tries to escape base_path
        """
        full_path = (self.base_path / file_path).resolve()

        # Ensure path is within base_path
        try:
            full_path.relative_to(self.base_path)
        except ValueError:
            raise StorageError(
                f"Path {file_path} attempts to escape base directory"
            )

        return full_path

    async def list_files(self, path: str = "", pattern: str = "*") -> List[FileInfo]:
        """List files in local directory.

        Args:
            path: Relative path from base_path
            pattern: Glob pattern (default: "*" for all files)

        Returns:
            List of FileInfo dicts
        """
        search_path = self.base_path / path if path else self.base_path

        if not search_path.exists():
            return []

        files = []
        for root, _, filenames in os.walk(search_path):
            for filename in filenames:
                if fnmatch(filename, pattern):
                    full_path = Path(root) / filename
                    relative_path = full_path.relative_to(self.base_path)

                    stat = full_path.stat()
                    files.append(
                        FileInfo(
                            {
                                "name": filename,
                                "path": str(relative_path),
                                "size_bytes": stat.st_size,
                                "modified_at": datetime.fromtimestamp(stat.st_mtime),
                            }
                        )
                    )

        return files

    async def download_file(self, file_path: str) -> bytes:
        """Download file from local filesystem.

        Args:
            file_path: Relative path to file

        Returns:
            File content as bytes
        """
        full_path = self._validate_path(file_path)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def upload_file(self, file_path: str, content: bytes) -> str:
        """Upload file to local filesystem.

        Args:
            file_path: Destination path
            content: File content

        Returns:
            Path where file was saved
        """
        full_path = self._validate_path(file_path)

        # Create parent directories if they don't exist
        full_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)

        return str(full_path.relative_to(self.base_path))

    async def test_connection(self) -> bool:
        """Test if base path exists and is accessible.

        Returns:
            True if base_path exists and is readable
        """
        try:
            return self.base_path.exists() and os.access(self.base_path, os.R_OK)
        except Exception:
            return False

    async def get_file_info(self, file_path: str) -> FileInfo:
        """Get file metadata.

        Args:
            file_path: Path to file

        Returns:
            FileInfo with metadata
        """
        full_path = self._validate_path(file_path)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        stat = full_path.stat()
        return FileInfo(
            {
                "name": full_path.name,
                "path": file_path,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime),
            }
        )
