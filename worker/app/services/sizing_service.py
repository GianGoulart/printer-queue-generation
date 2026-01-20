"""Sizing service for applying sizing profiles and validating items."""

import json
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SizingResult:
    """Result of sizing calculation."""
    
    final_width_mm: float
    final_height_mm: float
    scale_applied: float  # 1.0 = no scaling
    warnings: List[str]
    is_valid: bool
    error_message: Optional[str] = None


class SizingService:
    """Apply sizing profiles and validate items."""
    
    # Supported image formats
    SUPPORTED_FORMATS = ["PNG", "JPEG", "JPG", "GIF", "WEBP"]
    
    # Margins for machine constraints
    SIDE_MARGIN_MM = 20  # Each side
    SAFETY_MARGIN_MM = 50  # Safety margin for length
    
    def __init__(self):
        """Initialize sizing service."""
        pass
    
    async def apply_sizing(
        self,
        job_item,
        asset,
        sizing_profile,
        machine
    ) -> SizingResult:
        """
        Apply sizing profile to item.
        
        Args:
            job_item: JobItem instance
            asset: Asset instance
            sizing_profile: SizingProfile instance (can be None for default)
            machine: Machine instance
            
        Returns:
            SizingResult with calculated dimensions and validation status
        """
        warnings = []
        
        # Parse asset metadata
        try:
            metadata = json.loads(asset.metadata_json) if asset.metadata_json else {}
        except (json.JSONDecodeError, TypeError):
            return SizingResult(
                final_width_mm=0,
                final_height_mm=0,
                scale_applied=0,
                warnings=[],
                is_valid=False,
                error_message="Invalid asset metadata JSON"
            )
        
        # Validate format
        if not self.validate_format(metadata):
            return SizingResult(
                final_width_mm=0,
                final_height_mm=0,
                scale_applied=0,
                warnings=[],
                is_valid=False,
                error_message=f"Unsupported image format. Supported: {', '.join(self.SUPPORTED_FORMATS)}"
            )
        
        # Validate DPI (warning only, not blocking)
        warnings = []
        dpi_check = metadata.get('dpi', 0)
        if isinstance(dpi_check, (list, tuple)):
            dpi_check = min(dpi_check)
        
        if not self.validate_dpi(metadata, machine.min_dpi):
            warnings.append(
                f"⚠️ DPI below recommended ({dpi_check} < {machine.min_dpi}). "
                f"Print quality may be reduced."
            )
        
        # Get target width from sizing profile or default
        target_width_mm = sizing_profile.target_width_mm if sizing_profile else 100.0
        
        # Calculate dimensions maintaining aspect ratio
        final_width_mm, final_height_mm = self.calculate_dimensions(
            metadata,
            target_width_mm
        )
        
        # Calculate usable width (accounting for margins)
        usable_width_mm = machine.max_width_mm - (2 * self.SIDE_MARGIN_MM)
        
        # Check if needs scaling to fit machine width
        scale_applied = 1.0
        if final_width_mm > usable_width_mm:
            scale_applied = usable_width_mm / final_width_mm
            original_width = final_width_mm
            final_width_mm = usable_width_mm
            final_height_mm = final_height_mm * scale_applied
            
            scale_percent = int(scale_applied * 100)
            warning = (
                f"Item {job_item.id} (SKU: {job_item.sku}): "
                f"scaled to {scale_percent}% to fit width "
                f"({original_width:.1f}mm -> {final_width_mm:.1f}mm)"
            )
            warnings.append(warning)
            logger.warning(warning)
        
        return SizingResult(
            final_width_mm=round(final_width_mm, 2),
            final_height_mm=round(final_height_mm, 2),
            scale_applied=round(scale_applied, 4),
            warnings=warnings,
            is_valid=True
        )
    
    def validate_dpi(self, asset_metadata: dict, min_dpi: int) -> bool:
        """
        Validate asset has minimum DPI.
        
        Args:
            asset_metadata: Asset metadata dictionary
            min_dpi: Minimum required DPI
            
        Returns:
            True if DPI is sufficient
        """
        dpi = asset_metadata.get('dpi', 0)
        
        # If DPI not in metadata, try to calculate from dimensions
        if not dpi:
            width_px = asset_metadata.get('width_px', 0)
            width_inches = asset_metadata.get('width_inches', 0)
            
            if width_px and width_inches:
                dpi = width_px / width_inches
        
        # Handle DPI as list [dpi_x, dpi_y] (common format)
        if isinstance(dpi, (list, tuple)):
            dpi = min(dpi)  # Use minimum DPI (most conservative)
        
        return dpi >= min_dpi
    
    def validate_format(self, asset_metadata: dict) -> bool:
        """
        Validate image format is supported.
        
        Args:
            asset_metadata: Asset metadata dictionary
            
        Returns:
            True if format is supported
        """
        format_type = asset_metadata.get('format', '').upper()
        return format_type in self.SUPPORTED_FORMATS
    
    def calculate_dimensions(
        self,
        asset_metadata: dict,
        target_width_mm: float
    ) -> Tuple[float, float]:
        """
        Calculate final dimensions maintaining aspect ratio.
        
        Args:
            asset_metadata: Asset metadata with dimensions
            target_width_mm: Target width in millimeters
            
        Returns:
            (final_width_mm, final_height_mm)
        """
        # Get original dimensions in pixels
        width_px = asset_metadata.get('width_px', 0)
        height_px = asset_metadata.get('height_px', 0)
        
        if not width_px or not height_px:
            # Fallback: try to get from other fields
            width_px = asset_metadata.get('width', 0)
            height_px = asset_metadata.get('height', 0)
        
        if not width_px or not height_px:
            logger.error(f"Missing dimensions in metadata: {asset_metadata}")
            return (target_width_mm, target_width_mm)  # Square fallback
        
        # Calculate aspect ratio
        aspect_ratio = height_px / width_px
        
        # Calculate final dimensions
        final_width_mm = target_width_mm
        final_height_mm = target_width_mm * aspect_ratio
        
        return (final_width_mm, final_height_mm)
    
    async def apply_sizing_batch(
        self,
        items_with_data: List[Tuple],  # (job_item, asset, sizing_profile, machine)
    ) -> List[Tuple]:  # List of (job_item, SizingResult)
        """
        Apply sizing to multiple items.
        
        Args:
            items_with_data: List of tuples (job_item, asset, sizing_profile, machine)
            
        Returns:
            List of (job_item, SizingResult) tuples
        """
        results = []
        
        for job_item, asset, sizing_profile, machine in items_with_data:
            result = await self.apply_sizing(
                job_item,
                asset,
                sizing_profile,
                machine
            )
            results.append((job_item, result))
        
        return results
