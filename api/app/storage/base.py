"""Base storage driver interface."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List


class FileInfo(Dict[str, Any]):
    """File information dict with typed access."""

    @property
    def name(self) -> str:
        return self["name"]

    @property
    def path(self) -> str:
        return self["path"]

    @property
    def size_bytes(self) -> int:
        return self["size_bytes"]

    @property
    def modified_at(self) -> datetime:
        return self["modified_at"]


class BaseStorageDriver(ABC):
    """Base class for storage drivers.

    All storage drivers must implement this interface to provide
    unified access to different storage backends (S3, Dropbox, Local, etc).
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize storage driver with configuration.

        Args:
            config: Storage configuration dict with provider-specific settings
        """
        self.config = config

    @abstractmethod
    async def list_files(self, path: str = "", pattern: str = "*") -> List[FileInfo]:
        """List files in storage.

        Args:
            path: Path to list files from (relative to base_path)
            pattern: Glob pattern to filter files (default: "*")

        Returns:
            List of FileInfo dicts with: name, path, size_bytes, modified_at

        Raises:
            StorageError: If listing fails
        """
        pass

    @abstractmethod
    async def download_file(self, file_path: str) -> bytes:
        """Download file and return bytes.

        Args:
            file_path: Path to file (relative to base_path)

        Returns:
            File content as bytes

        Raises:
            StorageError: If download fails
            FileNotFoundError: If file doesn't exist
        """
        pass

    @abstractmethod
    async def upload_file(self, file_path: str, content: bytes) -> str:
        """Upload file and return URI.

        Args:
            file_path: Destination path (relative to base_path)
            content: File content as bytes

        Returns:
            URI/path where file was uploaded

        Raises:
            StorageError: If upload fails
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if storage is accessible.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_file_info(self, file_path: str) -> FileInfo:
        """Get file metadata without downloading.

        Args:
            file_path: Path to file

        Returns:
            FileInfo with metadata

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        pass


class StorageError(Exception):
    """Base exception for storage operations."""

    pass


class StorageConnectionError(StorageError):
    """Exception for connection errors."""

    pass


class StoragePermissionError(StorageError):
    """Exception for permission errors."""

    pass
