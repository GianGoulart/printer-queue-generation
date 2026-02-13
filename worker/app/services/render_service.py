"""Render service for generating print-ready PDFs."""

import io
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from reportlab.lib.pagesizes import landscape, portrait
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from PIL import Image

logger = logging.getLogger(__name__)


class RenderService:
    """Render PDFs from layout."""
    
    # PDF settings
    DPI = 300
    COMPRESSION_QUALITY = 95
    
    def __init__(self):
        """Initialize render service."""
        pass
    
    async def render_bases(
        self,
        job,
        bases: List,
        items_map: dict,
        assets_map: dict,
        storage_driver
    ) -> tuple[List[str], List[dict]]:
        """
        Render all bases to PDFs.
        
        Returns:
            Tuple of (pdf_uris, failed_items) where failed_items is a list of dicts
            with item_id, sku, and reason for failure
        """
        pdf_uris = []
        all_failed_items = []
        
        for base in bases:
            try:
                # Render single base
                pdf_content, failed_items = await self.render_base(
                    base=base,
                    job=job,
                    items_map=items_map,
                    assets_map=assets_map,
                    storage_driver=storage_driver
                )
                
                # Collect failed items
                all_failed_items.extend(failed_items)
                
                # Validate PDF before saving
                if not pdf_content or len(pdf_content) < 100:
                    raise ValueError(f"Generated PDF for base {base.index} is too small or empty")
                
                # Save to storage
                output_path = f"tenant/{job.tenant_id}/outputs/{job.id}/base_{base.index}.pdf"
                uri = await storage_driver.upload_file(
                    file_path=output_path,
                    content=pdf_content
                )
                
                pdf_uris.append(uri)
                logger.info(f"✅ Rendered base {base.index} for job {job.id}: {uri}")
                
            except Exception as e:
                logger.error(f"Error rendering base {base.index} for job {job.id}: {e}", exc_info=True)
                raise
        
        return pdf_uris, all_failed_items
    
    async def render_base(
        self,
        base,
        job,
        items_map: dict,
        assets_map: dict,
        storage_driver
    ) -> tuple[bytes, List[dict]]:
        """
        Render single base to PDF.
        
        Returns:
            Tuple of (pdf_content, failed_items) where failed_items is a list of dicts
            with item_id, sku, and reason for failure
        """
        # Create PDF in memory
        buffer = io.BytesIO()
        
        # Set page size (width x length in mm)
        page_width = base.width_mm * mm
        page_length = base.length_mm * mm
        
        # Create canvas
        c = canvas.Canvas(buffer, pagesize=(page_width, page_length))
        
        # Add metadata
        c.setTitle(f"Base {base.index} - Job {job.id}")
        c.setAuthor("Printer Queue System")
        c.setSubject(f"Print job {job.id} for tenant {job.tenant_id}")
        c.setCreator("Printer Queue Service v1.0")
        
        items_drawn = 0
        items_failed = 0
        failed_items = []  # Track failed items with details
        
        # Draw each placement
        for placement in base.placements:
            try:
                # Get item and asset
                item = items_map.get(placement.item_id)
                if not item:
                    reason = "Item not found in items_map"
                    logger.error(f"Skipping placement {placement.item_id}: {reason}")
                    items_failed += 1
                    failed_items.append({
                        "item_id": placement.item_id,
                        "sku": getattr(placement, 'sku', 'unknown'),
                        "reason": reason
                    })
                    continue
                
                if not item.asset_id:
                    reason = "No asset_id assigned to item"
                    logger.error(f"Skipping placement {placement.item_id} (SKU: {item.sku}): {reason}")
                    items_failed += 1
                    failed_items.append({
                        "item_id": placement.item_id,
                        "sku": item.sku,
                        "reason": reason
                    })
                    continue
                
                asset = assets_map.get(item.asset_id)
                if not asset:
                    reason = f"Asset {item.asset_id} not found in database"
                    logger.error(
                        f"Skipping placement {placement.item_id} (SKU: {item.sku}): {reason}"
                    )
                    items_failed += 1
                    failed_items.append({
                        "item_id": placement.item_id,
                        "sku": item.sku,
                        "reason": reason
                    })
                    continue
                
                # Validate placement boundaries
                if not self._validate_placement(placement, base.width_mm, base.length_mm):
                    reason = "Placement out of base boundaries"
                    logger.error(f"Skipping placement {placement.item_id}: {reason}")
                    items_failed += 1
                    failed_items.append({
                        "item_id": placement.item_id,
                        "sku": item.sku,
                        "reason": reason
                    })
                    continue
                
                # Download image from storage
                try:
                    image_content = await storage_driver.download_file(asset.file_uri)
                except Exception as download_error:
                    reason = f"Failed to download from storage: {str(download_error)}"
                    logger.error(
                        f"Skipping placement {placement.item_id} (SKU: {item.sku}): {reason}",
                        exc_info=True
                    )
                    items_failed += 1
                    failed_items.append({
                        "item_id": placement.item_id,
                        "sku": item.sku,
                        "reason": reason,
                        "file_uri": asset.file_uri
                    })
                    continue
                
                if not image_content:
                    reason = "Empty image content from storage"
                    logger.error(
                        f"Skipping placement {placement.item_id} (SKU: {item.sku}): {reason}"
                    )
                    items_failed += 1
                    failed_items.append({
                        "item_id": placement.item_id,
                        "sku": item.sku,
                        "reason": reason,
                        "file_uri": asset.file_uri
                    })
                    continue
                
                # Validate that content looks like an image (check magic bytes)
                if len(image_content) < 8:
                    reason = f"File too small ({len(image_content)} bytes)"
                    logger.error(
                        f"Skipping placement {placement.item_id} (SKU: {item.sku}): {reason}"
                    )
                    items_failed += 1
                    failed_items.append({
                        "item_id": placement.item_id,
                        "sku": item.sku,
                        "reason": reason,
                        "file_uri": asset.file_uri
                    })
                    continue
                
                # Check for common image magic bytes
                is_valid_image = False
                magic_bytes = image_content[:8]
                # PNG: 89 50 4E 47 0D 0A 1A 0A
                # JPEG: FF D8 FF
                # GIF: 47 49 46 38 (GIF8)
                if (magic_bytes.startswith(b'\x89PNG\r\n\x1a\n') or
                    magic_bytes.startswith(b'\xff\xd8\xff') or
                    magic_bytes.startswith(b'GIF8') or
                    magic_bytes.startswith(b'RIFF') or  # WebP
                    magic_bytes.startswith(b'BM')):  # BMP
                    is_valid_image = True
                
                if not is_valid_image:
                    reason = f"Invalid image format (magic bytes: {magic_bytes.hex()})"
                    logger.error(
                        f"Skipping placement {placement.item_id} (SKU: {item.sku}): {reason}"
                    )
                    items_failed += 1
                    failed_items.append({
                        "item_id": placement.item_id,
                        "sku": item.sku,
                        "reason": reason,
                        "file_uri": asset.file_uri
                    })
                    continue
                
                # Create temporary file for image
                # Determine file extension from magic bytes or asset filename
                file_ext = '.png'
                if magic_bytes.startswith(b'\xff\xd8\xff'):
                    file_ext = '.jpg'
                elif magic_bytes.startswith(b'GIF8'):
                    file_ext = '.gif'
                elif magic_bytes.startswith(b'RIFF'):
                    file_ext = '.webp'
                elif magic_bytes.startswith(b'BM'):
                    file_ext = '.bmp'
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                    tmp_file.write(image_content)
                    tmp_path = tmp_file.name
                
                try:
                    # Process image (convert to RGB if needed, remove transparency)
                    # This will also validate that the image can be opened
                    processed_path = self._process_image(tmp_path)
                    
                    # ✅ FIX: Inverter coordenada Y (ReportLab usa origem inferior esquerda)
                    x_points = placement.x_mm * mm
                    y_points = (base.length_mm - placement.y_mm - placement.height_mm) * mm
                    width_points = placement.width_mm * mm
                    height_points = placement.height_mm * mm
                    
                    # Draw image on canvas
                    c.drawImage(
                        processed_path,
                        x_points,
                        y_points,
                        width=width_points,
                        height=height_points,
                        preserveAspectRatio=True
                    )
                    
                    items_drawn += 1
                    logger.debug(
                        f"Drew item {item.id} (SKU: {item.sku}) at "
                        f"({placement.x_mm:.1f}, {placement.y_mm:.1f}mm) "
                        f"size: {placement.width_mm:.1f}x{placement.height_mm:.1f}mm"
                    )
                    
                except Exception as e:
                    reason = f"Error processing/drawing image: {str(e)}"
                    logger.error(
                        f"Error processing/drawing image for placement {placement.item_id} "
                        f"(SKU: {item.sku}, asset_id: {item.asset_id}, file_uri: {asset.file_uri}): {e}",
                        exc_info=True
                    )
                    items_failed += 1
                    failed_items.append({
                        "item_id": placement.item_id,
                        "sku": item.sku,
                        "reason": reason,
                        "file_uri": asset.file_uri,
                        "asset_id": item.asset_id
                    })
                    
                finally:
                    # Clean up temp files
                    for path in [tmp_path, processed_path if 'processed_path' in locals() else None]:
                        if path:
                            try:
                                Path(path).unlink(missing_ok=True)
                            except Exception as e:
                                logger.warning(f"Could not delete temp file {path}: {e}")
                        
            except Exception as e:
                reason = f"Unexpected error: {str(e)}"
                sku = getattr(placement, 'sku', 'unknown')
                logger.error(
                    f"Error drawing placement {placement.item_id} (SKU: {sku}) "
                    f"on base {base.index}: {e}",
                    exc_info=True
                )
                items_failed += 1
                failed_items.append({
                    "item_id": placement.item_id,
                    "sku": sku,
                    "reason": reason
                })
        
        # ✅ FIX: Finaliza a página antes de salvar
        c.showPage()
        c.save()
        
        # Reset buffer position to beginning
        buffer.seek(0)
        
        # Get PDF content
        pdf_content = buffer.read()
        buffer.close()
        
        logger.info(
            f"Rendered base {base.index}: {base.width_mm:.0f}x{base.length_mm:.0f}mm, "
            f"{items_drawn}/{len(base.placements)} items drawn successfully, "
            f"{items_failed} failed, "
            f"PDF size: {len(pdf_content)} bytes"
        )
        
        # Warn if no items were drawn
        if items_drawn == 0:
            logger.error(f"Base {base.index} was rendered but contains NO images!")
            raise ValueError(f"No items could be drawn on base {base.index}")
        
        return pdf_content, failed_items
    
    def _process_image(self, image_path: str) -> str:
        """
        Process image to ensure compatibility with ReportLab.
        Converts RGBA/LA/P to RGB, handles transparency.
        
        Returns path to processed image.
        
        Raises:
            UnidentifiedImageError: If the file is not a valid image
        """
        try:
            with Image.open(image_path) as img:
                # Se já é RGB/L, retorna o original
                if img.mode in ('RGB', 'L'):
                    return image_path
                
                # Converte para RGB
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Cria fundo branco
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    
                    # Converte palette para RGBA se necessário
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    
                    # Cola imagem com transparência
                    if img.mode in ('RGBA', 'LA'):
                        rgb_img.paste(img, mask=img.split()[-1])  # Usa canal alpha como máscara
                    else:
                        rgb_img.paste(img)
                    
                    img.close()
                    
                    # Salva processada
                    file_ext = Path(image_path).suffix
                    processed_path = image_path.replace(file_ext, '_processed.png')
                    rgb_img.save(processed_path, 'PNG', quality=self.COMPRESSION_QUALITY)
                    rgb_img.close()
                    
                    logger.debug(f"Converted image from {img.mode} to RGB: {processed_path}")
                    return processed_path
                
                # Outros modos: converte direto para RGB
                rgb_img = img.convert('RGB')
                img.close()
                
                file_ext = Path(image_path).suffix
                processed_path = image_path.replace(file_ext, '_processed.png')
                rgb_img.save(processed_path, 'PNG', quality=self.COMPRESSION_QUALITY)
                rgb_img.close()
                
                return processed_path
                
        except Exception as e:
            logger.error(f"Error processing image {image_path}: {e}", exc_info=True)
            # Re-raise to let caller handle it
            raise
    
    def _validate_placement(
        self,
        placement,
        base_width_mm: float,
        base_length_mm: float
    ) -> bool:
        """Validate that placement is within base boundaries."""
        # Check if item is within base
        if placement.x_mm < 0 or placement.y_mm < 0:
            logger.error(f"Invalid placement: negative coordinates for item {placement.item_id}")
            return False
        
        if (placement.x_mm + placement.width_mm) > base_width_mm:
            logger.error(
                f"Invalid placement: item {placement.item_id} exceeds base width "
                f"({placement.x_mm + placement.width_mm:.1f} > {base_width_mm:.1f}mm)"
            )
            return False
        
        if (placement.y_mm + placement.height_mm) > base_length_mm:
            logger.error(
                f"Invalid placement: item {placement.item_id} exceeds base length "
                f"({placement.y_mm + placement.height_mm:.1f} > {base_length_mm:.1f}mm)"
            )
            return False
        
        return True
    
    async def create_preview(
        self,
        pdf_content: bytes,
        max_width: int = 800
    ) -> bytes:
        """
        Create PNG preview from PDF.
        
        Args:
            pdf_content: PDF bytes
            max_width: Maximum width for preview image
            
        Returns:
            PNG image bytes
        """
        # TODO: Implement PDF to image conversion
        # For now, return empty bytes
        logger.warning("Preview generation not yet implemented")
        return b""