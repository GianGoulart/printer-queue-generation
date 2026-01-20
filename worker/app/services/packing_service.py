"""Packing service for layout algorithms with ROBUST Skyline."""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ItemPlacement:
    """Item placement in a base."""
    
    item_id: int
    sku: str
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    rotated: bool = False
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "item_id": self.item_id,
            "sku": self.sku,
            "x_mm": round(self.x_mm, 2),
            "y_mm": round(self.y_mm, 2),
            "width_mm": round(self.width_mm, 2),
            "height_mm": round(self.height_mm, 2),
            "rotated": self.rotated
        }


@dataclass
class Base:
    """Represents one base/roll."""
    
    index: int  # 1, 2, 3...
    width_mm: float
    length_mm: float
    placements: List[ItemPlacement] = field(default_factory=list)
    utilization: float = 0.0
    
    def calculate_utilization(self) -> float:
        """Calculate utilization percentage of this base."""
        if not self.placements:
            return 0.0
        
        total_area = self.width_mm * self.length_mm
        used_area = sum(p.width_mm * p.height_mm for p in self.placements)
        
        self.utilization = (used_area / total_area) * 100 if total_area > 0 else 0.0
        return self.utilization
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "index": self.index,
            "width_mm": round(self.width_mm, 2),
            "length_mm": round(self.length_mm, 2),
            "utilization": round(self.utilization, 2),
            "items_count": len(self.placements),
            "placements": [p.to_dict() for p in self.placements]
        }


@dataclass
class PackingResult:
    """Result of packing operation."""
    
    bases: List[Base]
    total_bases: int
    total_length_mm: float
    avg_utilization: float
    mode: str
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "mode": self.mode,
            "total_bases": self.total_bases,
            "total_length_mm": round(self.total_length_mm, 2),
            "avg_utilization": round(self.avg_utilization, 2),
            "bases": [b.to_dict() for b in self.bases]
        }


@dataclass
class SkylineSegment:
    """Segment of skyline (height profile of base)."""
    x: float
    y: float  # ✅ MUDANÇA: Y absoluto (não "height" relativo)
    width: float
    
    def __repr__(self):
        return f"Seg(x={self.x:.1f}, y={self.y:.1f}, w={self.width:.1f})"


class PackingService:
    """Layout and packing algorithms."""
    
    # Configuration
    # ⚠️ IMPORTANT: ITEM_MARGIN_MM is the MINIMUM space between items for cutting
    # This ensures safe cutting operations (2mm minimum for precise cutting)
    # The margin is applied both horizontally and vertically in the skyline algorithm
    ITEM_MARGIN_MM = 2  # Minimum space between items for cutting (2mm = minimum safe spacing)
    SIDE_MARGIN_MM = 20  # Margin from edges
    SAFETY_MARGIN_MM = 50  # Safety margin at end of roll
    
    def __init__(self):
        """Initialize packing service."""
        pass
    
    async def pack_items(
        self,
        items: List,  # List of JobItem with final dimensions
        machine,
        mode: str = "sequence"
    ) -> PackingResult:
        """
        Pack items into bases.
        
        Args:
            items: Job items with final_width_mm and final_height_mm
            machine: Target machine with constraints
            mode: 'sequence' or 'optimize'
            
        Returns:
            PackingResult with placements
        """
        if not items:
            return PackingResult(
                bases=[],
                total_bases=0,
                total_length_mm=0.0,
                avg_utilization=0.0,
                mode=mode
            )
        
        # Calculate usable dimensions
        usable_width_mm = machine.max_width_mm - (2 * self.SIDE_MARGIN_MM)
        usable_length_mm = machine.max_length_mm - self.SAFETY_MARGIN_MM
        
        # Pack based on mode
        if mode == "optimize":
            bases = await self.pack_optimize(items, usable_width_mm, usable_length_mm)
        else:  # sequence - ✅ USA SKYLINE AGORA!
            bases = await self.pack_sequence_skyline(items, usable_width_mm, usable_length_mm)
        
        # Calculate metrics
        total_length = sum(b.length_mm for b in bases)
        avg_util = sum(b.utilization for b in bases) / len(bases) if bases else 0.0
        
        return PackingResult(
            bases=bases,
            total_bases=len(bases),
            total_length_mm=total_length,
            avg_utilization=avg_util,
            mode=mode
        )
    
    async def pack_sequence(
        self,
        items: List,
        max_width_mm: float,
        max_length_mm: float
    ) -> List[Base]:
        """
        Sequence mode: maintain PDF order using shelf packing.
        
        Args:
            items: Job items in original order
            max_width_mm: Maximum usable width
            max_length_mm: Maximum usable length per base
            
        Returns:
            List of Base objects with placements
        """
        bases = []
        current_base_index = 1
        
        # Initialize first base
        current_base = Base(
            index=current_base_index,
            width_mm=max_width_mm + (2 * self.SIDE_MARGIN_MM),
            length_mm=0.0
        )
        
        # Shelf packing variables
        current_x = self.SIDE_MARGIN_MM
        current_y = self.SIDE_MARGIN_MM
        current_shelf_height = 0.0
        
        for item in items:
            item_width = item.final_width_mm
            item_height = item.final_height_mm
            
            # Check if item fits in current row
            if current_x + item_width + self.SIDE_MARGIN_MM > max_width_mm + self.SIDE_MARGIN_MM:
                # Move to next shelf (row)
                current_x = self.SIDE_MARGIN_MM
                current_y += current_shelf_height + self.ITEM_MARGIN_MM
                current_shelf_height = 0.0
            
            # Check if we need a new base
            if current_y + item_height + self.SIDE_MARGIN_MM > max_length_mm:
                # Finalize current base
                current_base.length_mm = current_y + current_shelf_height + self.SIDE_MARGIN_MM
                current_base.calculate_utilization()
                bases.append(current_base)
                
                # Start new base
                current_base_index += 1
                current_base = Base(
                    index=current_base_index,
                    width_mm=max_width_mm + (2 * self.SIDE_MARGIN_MM),
                    length_mm=0.0
                )
                current_x = self.SIDE_MARGIN_MM
                current_y = self.SIDE_MARGIN_MM
                current_shelf_height = 0.0
            
            # Place item
            placement = ItemPlacement(
                item_id=item.id,
                sku=item.sku,
                x_mm=current_x,
                y_mm=current_y,
                width_mm=item_width,
                height_mm=item_height,
                rotated=False
            )
            current_base.placements.append(placement)
            
            # Update position
            current_x += item_width + self.ITEM_MARGIN_MM
            current_shelf_height = max(current_shelf_height, item_height)
        
        # Finalize last base
        if current_base.placements:
            current_base.length_mm = current_y + current_shelf_height + self.SIDE_MARGIN_MM
            current_base.calculate_utilization()
            bases.append(current_base)
        
        logger.info(f"Sequence packing: {len(items)} items into {len(bases)} base(s)")
        return bases
    
    async def pack_sequence_skyline(
        self,
        items: List,
        max_width_mm: float,
        max_length_mm: float
    ) -> List[Base]:
        """
        🚀 ROBUST Skyline Algorithm - ZERO OVERLAY GUARANTEED.
        Maintains EXACT order + optimal space utilization.
        
        Args:
            items: Job items in EXACT picklist order
            max_width_mm: Maximum usable width
            max_length_mm: Maximum usable length per base
            
        Returns:
            List of Base objects with collision-free placements
        """
        bases = []
        current_base_index = 1
        
        # Initialize first base
        current_base = Base(
            index=current_base_index,
            width_mm=max_width_mm + (2 * self.SIDE_MARGIN_MM),
            length_mm=0.0
        )
        
        # ✅ Initial skyline: full width available at Y=0
        skyline = [SkylineSegment(x=0, y=0, width=max_width_mm)]
        
        max_y_used = 0.0  # Track maximum height used
        
        for idx, item in enumerate(items):
            item_width = item.final_width_mm
            item_height = item.final_height_mm
            
            # ✅ Find best position in current skyline
            # Consider margins when checking if item fits (for cutting space)
            position = self._find_best_position(
                skyline,
                item_width + self.ITEM_MARGIN_MM,  # ← Include margin in space check
                item_height + self.ITEM_MARGIN_MM,  # ← Include margin in space check
                max_width_mm,
                max_length_mm
            )
            
            if position is None:
                # ❌ Doesn't fit in current base → finalize and create new
                current_base.length_mm = max_y_used + self.SIDE_MARGIN_MM
                current_base.calculate_utilization()
                bases.append(current_base)
                
                logger.info(
                    f"✅ Base {current_base_index}: {len(current_base.placements)} items, "
                    f"{current_base.utilization:.1f}% utilization, "
                    f"length: {current_base.length_mm:.1f}mm"
                )
                
                # New base
                current_base_index += 1
                current_base = Base(
                    index=current_base_index,
                    width_mm=max_width_mm + (2 * self.SIDE_MARGIN_MM),
                    length_mm=0.0
                )
                
                # Reset skyline
                skyline = [SkylineSegment(x=0, y=0, width=max_width_mm)]
                max_y_used = 0.0
                
                # Try again in new base
                position = self._find_best_position(
                    skyline,
                    item_width,
                    item_height,
                    max_width_mm,
                    max_length_mm
                )
                
                if position is None:
                    logger.error(
                        f"❌ Item {item.sku} ({item_width:.1f}x{item_height:.1f}mm) "
                        f"doesn't fit even in empty base! Skipping."
                    )
                    continue
            
            x, y = position
            
            # ✅ VALIDAÇÃO ANTI-OVERLAY (paranoid check)
            if self._check_collision(current_base.placements, x, y, item_width, item_height):
                logger.error(
                    f"🚨 COLLISION DETECTED for item {item.sku} at ({x:.1f}, {y:.1f}mm)! "
                    f"This should NEVER happen. Forcing new base."
                )
                # Force new base
                current_base.length_mm = max_y_used + self.SIDE_MARGIN_MM
                current_base.calculate_utilization()
                bases.append(current_base)
                
                current_base_index += 1
                current_base = Base(
                    index=current_base_index,
                    width_mm=max_width_mm + (2 * self.SIDE_MARGIN_MM),
                    length_mm=0.0
                )
                skyline = [SkylineSegment(x=0, y=0, width=max_width_mm)]
                max_y_used = 0.0
                x, y = 0, 0
            
            # ✅ Create placement (item dimensions only, margins are spacing)
            placement = ItemPlacement(
                item_id=item.id,
                sku=item.sku,
                x_mm=x + self.SIDE_MARGIN_MM,  # Side margin from edge
                y_mm=y + self.SIDE_MARGIN_MM,  # Side margin from edge
                width_mm=item_width,            # Actual item width (no margin)
                height_mm=item_height,          # Actual item height (no margin)
                rotated=False
            )
            current_base.placements.append(placement)
            
            # ✅ Update skyline with item dimensions + margins
            # This ensures minimum spacing (ITEM_MARGIN_MM) between items for cutting
            # Horizontal: item_width + margin → next item will be at least margin away
            # Vertical: item_height + margin → next item will be at least margin away
            self._update_skyline_robust(
                skyline,
                x,
                item_width + self.ITEM_MARGIN_MM,  # ← Space reserved for cutting (horizontal)
                y + item_height + self.ITEM_MARGIN_MM  # ← Space reserved for cutting (vertical)
            )
            
            # Update maximum height used
            max_y_used = max(max_y_used, y + item_height + self.ITEM_MARGIN_MM)
            
            logger.debug(
                f"[{idx+1}/{len(items)}] Item {item.sku} @ ({x:.1f}, {y:.1f}mm) "
                f"on base {current_base_index}"
            )
        
        # ✅ Finalize last base
        if current_base.placements:
            current_base.length_mm = max_y_used + self.SIDE_MARGIN_MM
            current_base.calculate_utilization()
            bases.append(current_base)
            
            logger.info(
                f"✅ Base {current_base_index}: {len(current_base.placements)} items, "
                f"{current_base.utilization:.1f}% utilization, "
                f"length: {current_base.length_mm:.1f}mm"
            )
        
        total_items = sum(len(b.placements) for b in bases)
        avg_util = sum(b.utilization for b in bases) / len(bases) if bases else 0.0
        
        logger.info(
            f"🚀 Skyline packing COMPLETE: {total_items} items in {len(bases)} base(s), "
            f"average utilization: {avg_util:.1f}%"
        )
        
        return bases
    
    def _find_best_position(
        self,
        skyline: List[SkylineSegment],
        width: float,
        height: float,
        max_width: float,
        max_height: float
    ) -> Optional[Tuple[float, float]]:
        """
        ✅ ROBUST: Find best position in skyline for the item.
        Returns (x, y) or None if doesn't fit.
        
        Strategy: Bottom-Left (lowest Y, then leftmost X)
        """
        best_position = None
        best_y = float('inf')
        best_x = float('inf')
        
        # Try each segment as starting point
        for i in range(len(skyline)):
            # Check if item fits starting from this segment
            fit_result = self._can_fit_at_segment(skyline, i, width, height, max_width, max_height)
            
            if fit_result is not None:
                x, y = fit_result
                
                # Prefer lowest Y, then leftmost X
                if y < best_y or (y == best_y and x < best_x):
                    best_y = y
                    best_x = x
                    best_position = (x, y)
        
        return best_position
    
    def _can_fit_at_segment(
        self,
        skyline: List[SkylineSegment],
        start_idx: int,
        width: float,
        height: float,
        max_width: float,
        max_height: float
    ) -> Optional[Tuple[float, float]]:
        """
        ✅ Check if item can fit starting at segment index.
        Returns (x, y) if fits, None otherwise.
        """
        if start_idx >= len(skyline):
            return None
        
        start_segment = skyline[start_idx]
        x = start_segment.x
        
        # Check horizontal bounds
        if x + width > max_width:
            return None
        
        # Find maximum Y across all segments this item will cover
        max_y = 0.0
        covered_width = 0.0
        
        for i in range(start_idx, len(skyline)):
            segment = skyline[i]
            
            # Update max Y
            max_y = max(max_y, segment.y)
            
            # Calculate how much of this segment we need
            segment_used = min(segment.width, width - covered_width)
            covered_width += segment_used
            
            # Check if we have enough width
            if covered_width >= width:
                break
        
        # Check if we collected enough width
        if covered_width < width:
            return None
        
        # Check vertical bounds
        if max_y + height > max_height:
            return None
        
        return (x, max_y)
    
    def _update_skyline_robust(
        self,
        skyline: List[SkylineSegment],
        x: float,
        width: float,
        new_y: float
    ):
        """
        ✅ ROBUST skyline update - ZERO DUPLICATION.
        
        Args:
            skyline: Current skyline (modified in-place)
            x: X position of item
            width: Width of item
            new_y: New Y level after placing item
        """
        x_end = x + width
        new_segments = []
        
        i = 0
        while i < len(skyline):
            seg = skyline[i]
            seg_end = seg.x + seg.width
            
            # Case 1: Segment completely before item
            if seg_end <= x:
                new_segments.append(seg)
                i += 1
                continue
            
            # Case 2: Segment completely after item
            if seg.x >= x_end:
                new_segments.append(seg)
                i += 1
                continue
            
            # Case 3: Segment overlaps with item
            # Split into up to 3 parts: left, covered, right
            
            # Left part (before item)
            if seg.x < x:
                new_segments.append(SkylineSegment(
                    x=seg.x,
                    y=seg.y,
                    width=x - seg.x
                ))
            
            # Covered part (raised to new_y)
            covered_start = max(seg.x, x)
            covered_end = min(seg_end, x_end)
            if covered_end > covered_start:
                new_segments.append(SkylineSegment(
                    x=covered_start,
                    y=new_y,
                    width=covered_end - covered_start
                ))
            
            # Right part (after item)
            if seg_end > x_end:
                new_segments.append(SkylineSegment(
                    x=x_end,
                    y=seg.y,
                    width=seg_end - x_end
                ))
            
            i += 1
        
        # ✅ Merge adjacent segments with same Y
        skyline.clear()
        for seg in new_segments:
            if skyline and abs(skyline[-1].y - seg.y) < 0.01 and abs(skyline[-1].x + skyline[-1].width - seg.x) < 0.01:
                # Merge with previous
                skyline[-1].width += seg.width
            else:
                skyline.append(seg)
    
    def _check_collision(
        self,
        placements: List[ItemPlacement],
        x: float,
        y: float,
        width: float,
        height: float
    ) -> bool:
        """
        ✅ PARANOID collision check - should NEVER trigger if skyline is correct.
        Returns True if collision detected.
        """
        for p in placements:
            # AABB collision check (with margin tolerance)
            px = p.x_mm - self.SIDE_MARGIN_MM
            py = p.y_mm - self.SIDE_MARGIN_MM
            
            # Check if rectangles overlap
            if not (x + width <= px or px + p.width_mm <= x or
                    y + height <= py or py + p.height_mm <= y):
                return True  # Collision!
        
        return False
    
    async def pack_optimize(
        self,
        items: List,
        max_width_mm: float,
        max_length_mm: float
    ) -> List[Base]:
        """
        Optimize mode: minimize waste using best-fit decreasing.
        
        Args:
            items: Job items to pack
            max_width_mm: Maximum usable width
            max_length_mm: Maximum usable length per base
            
        Returns:
            List of Base objects with placements
        """
        # Sort items by area (largest first)
        sorted_items = sorted(
            items,
            key=lambda x: x.final_width_mm * x.final_height_mm,
            reverse=True
        )
        
        bases = []
        current_base_index = 1
        
        # Initialize first base
        current_base = Base(
            index=current_base_index,
            width_mm=max_width_mm + (2 * self.SIDE_MARGIN_MM),
            length_mm=0.0
        )
        
        # Shelf packing with sorted items
        current_x = self.SIDE_MARGIN_MM
        current_y = self.SIDE_MARGIN_MM
        current_shelf_height = 0.0
        
        for item in sorted_items:
            item_width = item.final_width_mm
            item_height = item.final_height_mm
            
            # Check if item fits in current row
            if current_x + item_width + self.SIDE_MARGIN_MM > max_width_mm + self.SIDE_MARGIN_MM:
                # Move to next shelf
                current_x = self.SIDE_MARGIN_MM
                current_y += current_shelf_height + self.ITEM_MARGIN_MM
                current_shelf_height = 0.0
            
            # Check if we need a new base
            if current_y + item_height + self.SIDE_MARGIN_MM > max_length_mm:
                # Finalize current base
                current_base.length_mm = current_y + current_shelf_height + self.SIDE_MARGIN_MM
                current_base.calculate_utilization()
                bases.append(current_base)
                
                # Start new base
                current_base_index += 1
                current_base = Base(
                    index=current_base_index,
                    width_mm=max_width_mm + (2 * self.SIDE_MARGIN_MM),
                    length_mm=0.0
                )
                current_x = self.SIDE_MARGIN_MM
                current_y = self.SIDE_MARGIN_MM
                current_shelf_height = 0.0
            
            # Place item
            placement = ItemPlacement(
                item_id=item.id,
                sku=item.sku,
                x_mm=current_x,
                y_mm=current_y,
                width_mm=item_width,
                height_mm=item_height,
                rotated=False
            )
            current_base.placements.append(placement)
            
            # Update position
            current_x += item_width + self.ITEM_MARGIN_MM
            current_shelf_height = max(current_shelf_height, item_height)
        
        # Finalize last base
        if current_base.placements:
            current_base.length_mm = current_y + current_shelf_height + self.SIDE_MARGIN_MM
            current_base.calculate_utilization()
            bases.append(current_base)
        
        logger.info(
            f"Optimize packing: {len(items)} items into {len(bases)} base(s), "
            f"avg utilization: {sum(b.utilization for b in bases) / len(bases):.1f}%"
        )
        return bases
