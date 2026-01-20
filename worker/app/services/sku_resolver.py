"""SKU Resolver Service with fuzzy matching."""

import logging
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session


class AssetCandidate(BaseModel):
    """Asset candidate for SKU resolution."""
    
    asset_id: int
    sku: str
    file_uri: str
    score: float


class SkuResolutionResult(BaseModel):
    """Result of SKU resolution."""
    
    status: str  # 'resolved' | 'missing' | 'ambiguous'
    asset_id: Optional[int] = None
    candidates: List[AssetCandidate] = []
    score: float = 0.0


class SKUResolverService:
    """Resolve SKUs to assets using exact and fuzzy matching."""
    
    EXACT_MATCH_THRESHOLD = 1.0
    FUZZY_MATCH_THRESHOLD = 0.7
    AMBIGUITY_DIFF_THRESHOLD = 0.1  # If top 2 candidates are within this diff, it's ambiguous
    MAX_CANDIDATES = 5
    
    def __init__(self):
        """Initialize resolver."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    async def resolve_sku(
        self,
        sku: str,
        tenant_id: int,
        db: Session
    ) -> SkuResolutionResult:
        """
        Resolve SKU to asset.
        
        Args:
            sku: SKU to resolve
            tenant_id: Tenant ID
            db: Database session
            
        Returns:
            SkuResolutionResult with status and details
        """
        self.logger.info(f"Resolving SKU: {sku} for tenant {tenant_id}")
        
        # Normalize SKU
        sku_normalized = self.normalize_sku(sku)
        
        # Try exact match first
        result = await self.resolve_exact(sku_normalized, tenant_id, db)
        if result:
            return result
        
        # Fallback to fuzzy matching
        result = await self.resolve_fuzzy(sku_normalized, tenant_id, db)
        return result
    
    async def resolve_exact(
        self,
        sku_normalized: str,
        tenant_id: int,
        db: Session
    ) -> Optional[SkuResolutionResult]:
        """
        Try exact match.
        
        Args:
            sku_normalized: Normalized SKU
            tenant_id: Tenant ID
            db: Database session
            
        Returns:
            SkuResolutionResult if exact match found, None otherwise
        """
        import sys
        
        # Save and remove worker's app module temporarily
        worker_app = sys.modules.get('app')
        if worker_app:
            del sys.modules['app']
        
        # Add /api_code to path and import Asset
        if '/api_code' not in sys.path:
            sys.path.insert(0, '/api_code')
            
        import app.models.asset as asset_module
        Asset = asset_module.Asset
        
        # Remove from path and restore worker app
        if '/api_code' in sys.path:
            sys.path.remove('/api_code')
        if worker_app:
            sys.modules['app'] = worker_app
        
        asset = db.query(Asset).filter(
            Asset.tenant_id == tenant_id,
            Asset.sku_normalized == sku_normalized
        ).first()
        
        if asset:
            self.logger.info(f"Exact match found: {asset.sku_normalized} (asset_id={asset.id})")
            return SkuResolutionResult(
                status="resolved",
                asset_id=asset.id,
                candidates=[AssetCandidate(
                    asset_id=asset.id,
                    sku=asset.sku_normalized,
                    file_uri=asset.file_uri,
                    score=1.0
                )],
                score=1.0
            )
        
        return None
    
    async def resolve_fuzzy(
        self,
        sku_normalized: str,
        tenant_id: int,
        db: Session
    ) -> SkuResolutionResult:
        """
        Fallback to fuzzy matching with trigram similarity.
        
        Args:
            sku_normalized: Normalized SKU
            tenant_id: Tenant ID
            db: Database session
            
        Returns:
            SkuResolutionResult with candidates
        """
        import sys
        
        # Save and remove worker's app module temporarily
        worker_app = sys.modules.get('app')
        if worker_app:
            del sys.modules['app']
        
        # Add /api_code to path and import Asset
        if '/api_code' not in sys.path:
            sys.path.insert(0, '/api_code')
            
        import app.models.asset as asset_module
        Asset = asset_module.Asset
        
        # Remove from path and restore worker app
        if '/api_code' in sys.path:
            sys.path.remove('/api_code')
        if worker_app:
            sys.modules['app'] = worker_app
        
        # Use PostgreSQL pg_trgm similarity
        # similarity() returns a value between 0 and 1
        query = db.query(
            Asset.id,
            Asset.sku_normalized,
            Asset.file_uri,
            func.similarity(Asset.sku_normalized, sku_normalized).label('score')
        ).filter(
            Asset.tenant_id == tenant_id,
            func.similarity(Asset.sku_normalized, sku_normalized) > self.FUZZY_MATCH_THRESHOLD
        ).order_by(
            text('score DESC')
        ).limit(self.MAX_CANDIDATES)
        
        results = query.all()
        
        if not results:
            self.logger.info(f"No fuzzy matches found for: {sku_normalized}")
            return SkuResolutionResult(
                status="missing",
                candidates=[]
            )
        
        # Build candidates list
        candidates = [
            AssetCandidate(
                asset_id=r.id,
                sku=r.sku_normalized,
                file_uri=r.file_uri,
                score=float(r.score)
            )
            for r in results
        ]
        
        self.logger.info(f"Found {len(candidates)} fuzzy matches for: {sku_normalized}")
        
        # Check if top match is good enough
        top_candidate = candidates[0]
        
        # If we have multiple candidates and top 2 are similar, it's ambiguous
        if len(candidates) >= 2:
            score_diff = abs(candidates[0].score - candidates[1].score)
            if score_diff < self.AMBIGUITY_DIFF_THRESHOLD:
                self.logger.info(
                    f"Ambiguous match: top 2 candidates have similar scores "
                    f"({candidates[0].score:.3f} vs {candidates[1].score:.3f})"
                )
                return SkuResolutionResult(
                    status="ambiguous",
                    candidates=candidates
                )
        
        # Single good match or clear winner
        if top_candidate.score >= self.FUZZY_MATCH_THRESHOLD:
            self.logger.info(
                f"Fuzzy match resolved: {top_candidate.sku} "
                f"(asset_id={top_candidate.asset_id}, score={top_candidate.score:.3f})"
            )
            return SkuResolutionResult(
                status="resolved",
                asset_id=top_candidate.asset_id,
                candidates=candidates,
                score=top_candidate.score
            )
        
        # Score too low
        return SkuResolutionResult(
            status="missing",
            candidates=candidates
        )
    
    def normalize_sku(self, sku: str) -> str:
        """
        Normalize SKU for matching.
        
        Args:
            sku: Raw SKU
            
        Returns:
            Normalized SKU
        """
        if not sku:
            return ""
        
        # Uppercase and trim
        return sku.upper().strip()
