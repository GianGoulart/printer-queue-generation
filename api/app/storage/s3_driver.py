"""S3-compatible storage driver (AWS S3, Cloudflare R2, MinIO, etc)."""

from datetime import datetime
from fnmatch import fnmatch
from typing import Any, Dict, List

import aioboto3
from botocore.exceptions import ClientError

from app.storage.base import (
    BaseStorageDriver,
    FileInfo,
    StorageConnectionError,
    StorageError,
)


class S3StorageDriver(BaseStorageDriver):
    """S3-compatible storage driver.

    Supports:
    - AWS S3
    - Cloudflare R2
    - MinIO
    - Any S3-compatible API

    Configuration:
        aws_access_key_id: Access key
        aws_secret_access_key: Secret key
        bucket_name: Bucket name
        region: AWS region (default: us-east-1)
        endpoint_url: Custom endpoint URL (for R2, MinIO, etc)
        base_path: Prefix path within bucket (optional)

    Example:
        >>> config = {
        ...     "aws_access_key_id": "AKIA...",
        ...     "aws_secret_access_key": "...",
        ...     "bucket_name": "my-bucket",
        ...     "region": "us-east-1"
        ... }
        >>> driver = S3StorageDriver(config)
        >>> files = await driver.list_files()
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.bucket_name = config["bucket_name"]
        self.base_path = config.get("base_path", "").strip("/")

        # S3 client configuration
        self.s3_config = {
            "aws_access_key_id": config["aws_access_key_id"],
            "aws_secret_access_key": config["aws_secret_access_key"],
            "region_name": config.get("region", "us-east-1"),
        }

        # Support custom endpoint (Cloudflare R2, MinIO, etc)
        if "endpoint_url" in config:
            self.s3_config["endpoint_url"] = config["endpoint_url"]

        self.session = aioboto3.Session()

    def _get_full_key(self, file_path: str) -> str:
        """Get full S3 key with base_path prefix.

        Args:
            file_path: Relative file path

        Returns:
            Full S3 key
        """
        if self.base_path:
            return f"{self.base_path}/{file_path}".strip("/")
        return file_path.strip("/")

    def _strip_base_path(self, key: str) -> str:
        """Remove base_path prefix from S3 key.

        Args:
            key: Full S3 key

        Returns:
            Relative path without base_path
        """
        if self.base_path and key.startswith(self.base_path + "/"):
            return key[len(self.base_path) + 1 :]
        return key

    async def list_files(self, path: str = "", pattern: str = "*") -> List[FileInfo]:
        """List files in S3 bucket.

        Args:
            path: Path prefix to list from
            pattern: Glob pattern to filter files

        Returns:
            List of FileInfo dicts
        """
        prefix = self._get_full_key(path) + "/" if path else self.base_path

        if prefix and not prefix.endswith("/"):
            prefix += "/"

        files = []

        try:
            async with self.session.client("s3", **self.s3_config) as s3:
                # Handle pagination
                paginator = s3.get_paginator("list_objects_v2")
                async for page in paginator.paginate(
                    Bucket=self.bucket_name, Prefix=prefix
                ):
                    if "Contents" not in page:
                        continue

                    for obj in page["Contents"]:
                        key = obj["Key"]
                        filename = key.split("/")[-1]

                        # Skip directories (keys ending with /)
                        if key.endswith("/"):
                            continue

                        # Apply pattern filter
                        if not fnmatch(filename, pattern):
                            continue

                        relative_path = self._strip_base_path(key)

                        files.append(
                            FileInfo(
                                {
                                    "name": filename,
                                    "path": relative_path,
                                    "size_bytes": obj["Size"],
                                    "modified_at": obj["LastModified"],
                                }
                            )
                        )

        except ClientError as e:
            raise StorageError(f"Failed to list files: {e}")

        return files

    async def download_file(self, file_path: str) -> bytes:
        """Download file from S3.

        Args:
            file_path: Path to file

        Returns:
            File content as bytes
        """
        key = self._get_full_key(file_path)

        try:
            async with self.session.client("s3", **self.s3_config) as s3:
                response = await s3.get_object(Bucket=self.bucket_name, Key=key)
                async with response["Body"] as stream:
                    return await stream.read()

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise FileNotFoundError(f"File not found: {file_path}")
            raise StorageError(f"Failed to download file: {e}")

    async def upload_file(self, file_path: str, content: bytes) -> str:
        """Upload file to S3.

        Args:
            file_path: Destination path
            content: File content

        Returns:
            S3 URI where file was uploaded
        """
        key = self._get_full_key(file_path)

        try:
            async with self.session.client("s3", **self.s3_config) as s3:
                await s3.put_object(Bucket=self.bucket_name, Key=key, Body=content)

            return f"s3://{self.bucket_name}/{key}"

        except ClientError as e:
            raise StorageError(f"Failed to upload file: {e}")

    async def test_connection(self) -> bool:
        """Test S3 connection by checking if bucket exists.

        Returns:
            True if bucket is accessible
        """
        try:
            async with self.session.client("s3", **self.s3_config) as s3:
                await s3.head_bucket(Bucket=self.bucket_name)
            return True

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("404", "NoSuchBucket"):
                raise StorageConnectionError(f"Bucket not found: {self.bucket_name}")
            elif error_code == "403":
                raise StorageConnectionError(f"Access denied to bucket: {self.bucket_name}")
            return False

        except Exception:
            return False

    async def get_file_info(self, file_path: str) -> FileInfo:
        """Get file metadata from S3.

        Args:
            file_path: Path to file

        Returns:
            FileInfo with metadata
        """
        key = self._get_full_key(file_path)

        try:
            async with self.session.client("s3", **self.s3_config) as s3:
                response = await s3.head_object(Bucket=self.bucket_name, Key=key)

            filename = key.split("/")[-1]
            return FileInfo(
                {
                    "name": filename,
                    "path": file_path,
                    "size_bytes": response["ContentLength"],
                    "modified_at": response["LastModified"],
                }
            )

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                raise FileNotFoundError(f"File not found: {file_path}")
            raise StorageError(f"Failed to get file info: {e}")
