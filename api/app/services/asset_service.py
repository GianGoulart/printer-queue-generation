"""Asset business logic service."""

import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.asset import Asset


def upsert_asset(
    db: Session,
    tenant_id: int,
    filename: str,
    file_uri: str,
    sku_normalized: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Asset:
    """Create or update asset.

    If asset with same tenant_id and sku_normalized exists, update it.
    Otherwise, create new asset.

    Args:
        db: Database session
        tenant_id: Tenant ID
        filename: Original filename
        file_uri: URI/path to file in storage
        sku_normalized: Normalized SKU
        metadata: Optional metadata dict (image dimensions, format, etc)

    Returns:
        Created or updated Asset

    Examples:
        >>> asset = upsert_asset(
        ...     db, tenant_id=1,
        ...     filename="CAM001-P.png",
        ...     file_uri="s3://bucket/CAM001-P.png",
        ...     sku_normalized="cam001",
        ...     metadata={"width_px": 800, "height_px": 600}
        ... )
        >>> asset.sku_normalized
        'cam001'
    """
    # Check if asset already exists
    existing = (
        db.query(Asset)
        .filter(
            Asset.tenant_id == tenant_id,
            Asset.sku_normalized == sku_normalized,
        )
        .first()
    )

    if existing:
        # Update existing asset
        existing.original_filename = filename
        existing.file_uri = file_uri
        if metadata:
            existing.metadata_json = json.dumps(metadata)
        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Create new asset
        asset = Asset(
            tenant_id=tenant_id,
            original_filename=filename,
            file_uri=file_uri,
            sku_normalized=sku_normalized,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset


def find_asset_by_sku(
    db: Session,
    tenant_id: int,
    sku: str,
    exact: bool = True,
) -> Optional[Asset]:
    """Find asset by SKU (exact or fuzzy match).

    Args:
        db: Database session
        tenant_id: Tenant ID
        sku: SKU to search for
        exact: If True, exact match only. If False, use fuzzy match.

    Returns:
        Asset if found, None otherwise

    Examples:
        >>> asset = find_asset_by_sku(db, tenant_id=1, sku="cam001", exact=True)
        >>> asset.sku_normalized
        'cam001'
    """
    query = db.query(Asset).filter(Asset.tenant_id == tenant_id)

    if exact:
        return query.filter(Asset.sku_normalized == sku.lower()).first()
    else:
        # Fuzzy match using trigram similarity
        from sqlalchemy import func

        return (
            query.filter(func.similarity(Asset.sku_normalized, sku.lower()) > 0.3)
            .order_by(func.similarity(Asset.sku_normalized, sku.lower()).desc())
            .first()
        )


def search_assets_by_sku(
    db: Session,
    tenant_id: int,
    sku: str,
    threshold: float = 0.3,
    limit: int = 10,
) -> list[tuple[Asset, float]]:
    """Search assets by SKU with similarity scores.

    Args:
        db: Database session
        tenant_id: Tenant ID
        sku: SKU to search for
        threshold: Minimum similarity score (0.0 to 1.0)
        limit: Maximum number of results

    Returns:
        List of tuples (Asset, score)

    Examples:
        >>> results = search_assets_by_sku(db, tenant_id=1, sku="cam")
        >>> for asset, score in results:
        ...     print(f"{asset.sku_normalized}: {score:.2f}")
        cam001: 0.85
        cam002: 0.78
    """
    from sqlalchemy import func, select

    # Build query with similarity score
    stmt = (
        select(Asset, func.similarity(Asset.sku_normalized, sku.lower()).label("score"))
        .where(
            Asset.tenant_id == tenant_id,
            func.similarity(Asset.sku_normalized, sku.lower()) > threshold,
        )
        .order_by(func.similarity(Asset.sku_normalized, sku.lower()).desc())
        .limit(limit)
    )

    results = db.execute(stmt).all()
    return [(row[0], float(row[1])) for row in results]


def delete_asset(db: Session, asset_id: int, tenant_id: int) -> bool:
    """Delete asset by ID.

    Args:
        db: Database session
        asset_id: Asset ID
        tenant_id: Tenant ID (for security check)

    Returns:
        True if deleted, False if not found

    Examples:
        >>> deleted = delete_asset(db, asset_id=123, tenant_id=1)
        >>> deleted
        True
    """
    asset = (
        db.query(Asset)
        .filter(Asset.id == asset_id, Asset.tenant_id == tenant_id)
        .first()
    )

    if not asset:
        return False

    db.delete(asset)
    db.commit()
    return True
