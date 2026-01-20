"""Storage driver factory."""

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.models.storage_config import TenantStorageConfig
from app.storage.base import BaseStorageDriver, StorageError
from app.storage.encryption import decrypt_credentials
from app.storage.local_driver import LocalStorageDriver
from app.storage.s3_driver import S3StorageDriver


def get_storage_driver(db: Session, tenant_id: int) -> BaseStorageDriver:
    """Get storage driver instance for tenant.

    Args:
        db: Database session
        tenant_id: Tenant ID

    Returns:
        Configured storage driver instance

    Raises:
        StorageError: If storage not configured or driver not supported
        ValueError: If credentials decryption fails

    Example:
        >>> driver = get_storage_driver(db, tenant_id=1)
        >>> files = await driver.list_files()
    """
    # Get tenant storage config
    config = (
        db.query(TenantStorageConfig)
        .filter(TenantStorageConfig.tenant_id == tenant_id)
        .first()
    )

    if not config:
        raise StorageError(f"Storage not configured for tenant {tenant_id}")

    # Prepare driver configuration
    driver_config = {
        "base_path": config.base_path,
    }

    # Decrypt and merge credentials if present
    if config.credentials_encrypted:
        try:
            credentials = decrypt_credentials(config.credentials_encrypted)
            driver_config.update(credentials)
        except Exception as e:
            raise ValueError(f"Failed to decrypt credentials: {e}")

    # Instantiate appropriate driver
    provider = config.provider.lower()

    if provider == "local":
        return LocalStorageDriver(driver_config)

    elif provider == "s3":
        # Validate required S3 fields
        required_fields = ["aws_access_key_id", "aws_secret_access_key", "bucket_name"]
        missing = [f for f in required_fields if f not in driver_config]
        if missing:
            raise StorageError(f"Missing required S3 configuration: {missing}")
        return S3StorageDriver(driver_config)

    elif provider == "dropbox":
        # Dropbox driver not yet implemented
        raise StorageError("Dropbox driver not yet implemented")

    else:
        raise StorageError(f"Unsupported storage provider: {provider}")


def get_storage_driver_from_config(
    provider: str, base_path: str, credentials: Optional[dict] = None
) -> BaseStorageDriver:
    """Get storage driver from explicit configuration (for testing).

    Args:
        provider: Storage provider (local, s3, dropbox)
        base_path: Base path for storage
        credentials: Optional credentials dict

    Returns:
        Configured storage driver instance

    Example:
        >>> driver = get_storage_driver_from_config(
        ...     provider="local",
        ...     base_path="/tmp/assets"
        ... )
    """
    driver_config = {"base_path": base_path}

    if credentials:
        driver_config.update(credentials)

    provider = provider.lower()

    if provider == "local":
        return LocalStorageDriver(driver_config)
    elif provider == "s3":
        return S3StorageDriver(driver_config)
    elif provider == "dropbox":
        raise StorageError("Dropbox driver not yet implemented")
    else:
        raise StorageError(f"Unsupported storage provider: {provider}")
