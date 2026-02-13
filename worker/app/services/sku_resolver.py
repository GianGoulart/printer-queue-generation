"""SKU Resolver Service with fuzzy matching.

Supports "design-only" assets: picklist SKU e.g. bl-7-4-butterfly-p is resolved by
stripping sizing prefix (bl-7) and matching asset by design (butterfly-p → butterflyp).
"""

import logging
import re
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
    FUZZY_MATCH_THRESHOLD = 0.45  # Lowered so picklist SKUs like s63wolfg4 match asset 3wolfg4 (score ~0.5)
    AMBIGUITY_DIFF_THRESHOLD = 0.1  # If top 2 candidates are within this diff, try substring tie-break
    MAX_CANDIDATES = 5
    
    def __init__(self):
        """Initialize resolver."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def _design_from_remainder(self, remainder: str) -> str:
        """Strip leading numeric segment (e.g. 4- or 4) to get design part. bl-7-4-butterfly-p -> remainder 4butterflyp -> butterflyp."""
        if not remainder:
            return remainder
        # Remove leading digits and optional hyphen/underscore
        m = re.match(r"^[0-9]+[-_]?", remainder)
        if m:
            return remainder[m.end() :].strip("-_") or remainder
        return remainder

    def _candidate_skus_for_lookup(
        self, sku_normalized: str, sizing_prefixes: Optional[List[str]] = None
    ) -> List[str]:
        """
        Build list of SKU strings to try for asset lookup (order matters).
        When sizing_prefixes are provided, we prefer design-only matches first so we resolve
        to assets with correct file_uri (e.g. mario-10.png, sku mario10) instead of full-SKU
        assets that may point to non-existent paths (e.g. u-5-8-mario-10.png).
        - With sizing_prefixes: [design, remainder, ..., full_sku]
        - Without: [full_sku]
        """
        if not sizing_prefixes:
            return list(dict.fromkeys([sku_normalized]))
        candidates = []
        # Longest prefix first so we strip the most specific (e.g. bl74 before bl7)
        for prefix in sorted(sizing_prefixes, key=len, reverse=True):
            if not prefix or not sku_normalized.startswith(prefix):
                continue
            remainder = sku_normalized[len(prefix) :].lstrip("-_")
            if remainder:
                design = self._design_from_remainder(remainder)
                if design and design != remainder:
                    candidates.append(design)
                candidates.append(remainder)
            break  # only use first (longest) matching prefix for main candidates
        candidates.append(sku_normalized)
        return list(dict.fromkeys(candidates))

    async def resolve_sku(
        self,
        sku: str,
        tenant_id: int,
        db: Session,
        sizing_prefixes: Optional[List[str]] = None,
    ) -> SkuResolutionResult:
        """
        Resolve SKU to asset. If sizing_prefixes are provided (e.g. ['bl7','inf10']),
        also tries matching by design only: strip prefix and use remainder/design for lookup.
        
        Args:
            sku: SKU from picklist (e.g. bl-7-4-butterfly-p)
            tenant_id: Tenant ID
            db: Database session
            sizing_prefixes: Optional list of normalized prefixes (bl7, inf10) for design-only lookup
        """
        self.logger.info(f"Resolving SKU: {sku} for tenant {tenant_id}")
        
        sku_normalized = self.normalize_sku(sku)
        candidates = self._candidate_skus_for_lookup(sku_normalized, sizing_prefixes)
        if len(candidates) > 1:
            self.logger.debug(f"Lookup candidates (full + design): {candidates}")
        
        for candidate in candidates:
            result = await self.resolve_exact(candidate, tenant_id, db)
            if result:
                return result
        result = None
        for candidate in candidates:
            result = await self.resolve_fuzzy(candidate, tenant_id, db)
            if result and result.status in ("resolved", "ambiguous"):
                return result
        return result if result else await self.resolve_fuzzy(sku_normalized, tenant_id, db)
    
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
        
        # If we have multiple candidates and top 2 are similar, try substring tie-break
        if len(candidates) >= 2:
            score_diff = abs(candidates[0].score - candidates[1].score)
            if score_diff < self.AMBIGUITY_DIFF_THRESHOLD:
                # Prefer candidate whose sku is substring of requested or vice versa (e.g. s63wolfg4 vs 3wolfg4)
                preferred = self._prefer_substring_match(sku_normalized, candidates)
                if preferred is not None:
                    self.logger.info(
                        f"Resolved via substring tie-break: {preferred.sku} "
                        f"(asset_id={preferred.asset_id}, score={preferred.score:.3f})"
                    )
                    return SkuResolutionResult(
                        status="resolved",
                        asset_id=preferred.asset_id,
                        candidates=candidates,
                        score=preferred.score
                    )
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
    
    def _prefer_substring_match(
        self, sku_normalized: str, candidates: List[AssetCandidate]
    ) -> Optional[AssetCandidate]:
        """If one candidate's sku is substring of requested or vice versa, prefer it (break tie)."""
        for c in candidates:
            a, b = sku_normalized, c.sku.lower()
            if a in b or b in a:
                return c
        return None

    def normalize_sku(self, sku: str) -> str:
        """
        Normalize SKU for matching. Must match API/assets: lowercase, no separators.
        Aligns with sku_extractor.normalize_sku and robust_pdf_parser so picklist
        and catalog use the same form.
        
        Args:
            sku: Raw SKU
            
        Returns:
            Normalized SKU (lowercase, alphanumeric only)
        """
        if not sku:
            return ""
        s = sku.lower().strip()
        for lig, ascii_eq in (("\uFB02", "fl"), ("\uFB01", "fi"), ("\uFB00", "ff"), ("\uFB04", "ffl"), ("\uFB03", "ffi")):
            s = s.replace(lig, ascii_eq)
        s = s.replace("-", "").replace("_", "").replace(" ", "")
        s = re.sub(r"[^a-z0-9]", "", s)
        return s
