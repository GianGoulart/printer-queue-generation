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
    ) -> List[str]:
        """Render all bases to PDFs."""
        pdf_uris = []
        
        for base in bases:
            try:
                # Render single base
                pdf_content = await self.render_base(
                    base=base,
                    job=job,
                    items_map=items_map,
                    assets_map=assets_map,
                    storage_driver=storage_driver
                )
                
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
        
        return pdf_uris
    
    async def render_base(
        self,
        base,
        job,
        items_map: dict,
        assets_map: dict,
        storage_driver
    ) -> bytes:
        """Render single base to PDF."""
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
        
        # Draw each placement
        for placement in base.placements:
            try:
                # Get item and asset
                item = items_map.get(placement.item_id)
                if not item or not item.asset_id:
                    logger.warning(f"Skipping placement {placement.item_id}: no asset")
                    items_failed += 1
                    continue
                
                asset = assets_map.get(item.asset_id)
                if not asset:
                    logger.warning(f"Skipping placement {placement.item_id}: asset not found")
                    items_failed += 1
                    continue
                
                # Validate placement boundaries
                if not self._validate_placement(placement, base.width_mm, base.length_mm):
                    logger.error(f"Skipping placement {placement.item_id}: out of bounds")
                    items_failed += 1
                    continue
                
                # Download image from storage
                image_content = await storage_driver.download_file(asset.file_uri)
                
                if not image_content:
                    logger.error(f"Skipping placement {placement.item_id}: empty image content")
                    items_failed += 1
                    continue
                
                # Create temporary file for image
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                    tmp_file.write(image_content)
                    tmp_path = tmp_file.name
                
                try:
                    # Process image (convert to RGB if needed, remove transparency)
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
                    logger.error(f"Error processing/drawing image for {placement.item_id}: {e}", exc_info=True)
                    items_failed += 1
                    
                finally:
                    # Clean up temp files
                    for path in [tmp_path, processed_path if 'processed_path' in locals() else None]:
                        if path:
                            try:
                                Path(path).unlink(missing_ok=True)
                            except Exception as e:
                                logger.warning(f"Could not delete temp file {path}: {e}")
                        
            except Exception as e:
                logger.error(
                    f"Error drawing placement {placement.item_id} on base {base.index}: {e}",
                    exc_info=True
                )
                items_failed += 1
        
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
        
        return pdf_content
    
    def _process_image(self, image_path: str) -> str:
        """
        Process image to ensure compatibility with ReportLab.
        Converts RGBA/LA/P to RGB, handles transparency.
        
        Returns path to processed image.
        """
        try:
            with Image.open(image_path) as img:
                # ✅ NÃO usar verify() - corrompe o arquivo
                
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
                    
                    # Salva processada
                    processed_path = image_path.replace('.png', '_processed.png')
                    rgb_img.save(processed_path, 'PNG', quality=self.COMPRESSION_QUALITY)
                    
                    logger.debug(f"Converted image from {img.mode} to RGB: {processed_path}")
                    return processed_path
                
                # Outros modos: converte direto para RGB
                rgb_img = img.convert('RGB')
                processed_path = image_path.replace('.png', '_processed.png')
                rgb_img.save(processed_path, 'PNG', quality=self.COMPRESSION_QUALITY)
                
                return processed_path
                
        except Exception as e:
            logger.error(f"Error processing image {image_path}: {e}", exc_info=True)
            # Retorna original em caso de erro
            return image_path
    
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