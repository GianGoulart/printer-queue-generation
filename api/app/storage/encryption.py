"""Credentials encryption/decryption utilities."""

import base64
import json
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _get_fernet() -> Fernet:
    """Get Fernet instance with encryption key from settings.

    Returns:
        Fernet instance for encryption/decryption
    """
    # Ensure key is properly formatted (32 bytes base64)
    key = settings.storage_encryption_key.encode()
    if len(key) < 32:
        # Pad key if too short (for development only - use proper key in production)
        key = key.ljust(32, b"=")
    key = base64.urlsafe_b64encode(key[:32])
    return Fernet(key)


def encrypt_credentials(credentials: Dict[str, Any]) -> str:
    """Encrypt credentials dict to string.

    Args:
        credentials: Dict with credentials (access keys, tokens, etc)

    Returns:
        Encrypted string safe for database storage

    Example:
        >>> creds = {"access_key": "AKIA...", "secret_key": "..."}
        >>> encrypted = encrypt_credentials(creds)
        >>> encrypted
        'gAAAAA...'
    """
    f = _get_fernet()
    creds_json = json.dumps(credentials)
    encrypted_bytes = f.encrypt(creds_json.encode())
    return encrypted_bytes.decode()


def decrypt_credentials(encrypted: str) -> Dict[str, Any]:
    """Decrypt credentials string to dict.

    Args:
        encrypted: Encrypted credentials string from database

    Returns:
        Dict with decrypted credentials

    Raises:
        InvalidToken: If decryption fails (wrong key or corrupted data)

    Example:
        >>> decrypted = decrypt_credentials('gAAAAA...')
        >>> decrypted
        {'access_key': 'AKIA...', 'secret_key': '...'}
    """
    f = _get_fernet()
    try:
        decrypted_bytes = f.decrypt(encrypted.encode())
        creds_json = decrypted_bytes.decode()
        return json.loads(creds_json)
    except InvalidToken as e:
        raise ValueError(f"Failed to decrypt credentials: {e}")
