"""Image processing service for image packing feature."""

import logging
import zipfile
from pathlib import Path
from typing import List, Optional

from PIL import Image

logger = logging.getLogger(__name__)


class ImageInfo:
    """Information about an image."""
    
    def __init__(
        self,
        file_path: str,
        file_name: str,
        width_mm: float,
        height_mm: float,
        dpi: Optional[float] = None,
        source_uri: Optional[str] = None
    ):
        self.file_path = file_path
        self.file_name = file_name
        self.width_mm = width_mm
        self.height_mm = height_mm
        self.dpi = dpi
        self.source_uri = source_uri  # Original storage URI (for ZIP files, this is the ZIP URI)


class ImageProcessorService:
    """Service for processing images and extracting dimensions."""
    
    DEFAULT_DPI = 300
    MIN_DPI = 70  # Minimum DPI for testing purposes
    
    def __init__(self):
        """Initialize image processor."""
        pass
    
    def process_images(
        self,
        file_paths: List[str],
        extract_dir: Optional[Path] = None,
        source_uris: Optional[List[str]] = None
    ) -> List[ImageInfo]:
        """
        Process images from file paths (can be ZIP files or individual images).
        
        Args:
            file_paths: List of file paths (can be ZIP or image files)
            extract_dir: Directory to extract ZIP files to
            
        Returns:
            List of ImageInfo objects
        """
        image_infos = []
        
        # Create mapping of file paths to source URIs
        path_to_uri = {}
        if source_uris and len(source_uris) == len(file_paths):
            path_to_uri = dict(zip(file_paths, source_uris))
        
        for idx, file_path in enumerate(file_paths):
            path = Path(file_path)
            source_uri = path_to_uri.get(file_path) or (source_uris[idx] if source_uris and idx < len(source_uris) else None)
            
            if not path.exists():
                logger.warning(f"File not found: {file_path}")
                continue
            
            # Check if it's a ZIP file
            if path.suffix.lower() == '.zip' or zipfile.is_zipfile(path):
                logger.info(f"Extracting ZIP file: {file_path}")
                extracted_images = self._extract_zip(path, extract_dir, source_uri=source_uri)
                image_infos.extend(extracted_images)
            else:
                # Try to process as image
                try:
                    image_info = self._get_image_size_mm(path, source_uri=source_uri)
                    if image_info:
                        image_infos.append(image_info)
                except Exception as e:
                    logger.error(f"Failed to process image {file_path}: {e}")
                    continue
        
        logger.info(f"Processed {len(image_infos)} images")
        return image_infos
    
    def _extract_zip(self, zip_path: Path, extract_dir: Optional[Path] = None, source_uri: Optional[str] = None) -> List[ImageInfo]:
        """Extract images from ZIP file."""
        if extract_dir is None:
            extract_dir = zip_path.parent / "extracted"
        
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        image_infos = []
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # List all files in ZIP
                file_list = zip_ref.namelist()
                
                for file_name in file_list:
                    # Skip directories
                    if file_name.endswith('/'):
                        continue
                    
                    # Check if it's an image file
                    if not self._is_image_file(file_name):
                        logger.debug(f"Skipping non-image file in ZIP: {file_name}")
                        continue
                    
                    # Extract file
                    try:
                        zip_ref.extract(file_name, extract_dir)
                        extracted_path = extract_dir / file_name
                        
                        # Process image (for ZIP files, source_uri is the ZIP URI)
                        image_info = self._get_image_size_mm(extracted_path, source_uri=source_uri)
                        if image_info:
                            image_infos.append(image_info)
                    except Exception as e:
                        logger.error(f"Failed to extract/process {file_name} from ZIP: {e}")
                        continue
        
        except Exception as e:
            logger.error(f"Failed to extract ZIP {zip_path}: {e}")
            raise
        
        return image_infos
    
    def _is_image_file(self, file_name: str) -> bool:
        """Check if file is an image based on extension."""
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff', '.tif'}
        return Path(file_name).suffix.lower() in image_extensions
    
    def _get_image_size_mm(self, image_path: Path, source_uri: Optional[str] = None) -> Optional[ImageInfo]:
        """Get image dimensions in millimeters."""
        try:
            with Image.open(image_path) as img:
                # Get image dimensions in pixels
                width_px, height_px = img.size
                
                # Get DPI from image metadata
                dpi = self._get_dpi_from_image(img)
                
                # Convert to millimeters
                width_mm, height_mm = self._image_pixels_to_mm(width_px, height_px, dpi)
                
                return ImageInfo(
                    file_path=str(image_path),
                    file_name=image_path.name,
                    width_mm=width_mm,
                    height_mm=height_mm,
                    dpi=dpi,
                    source_uri=source_uri
                )
        
        except Exception as e:
            logger.error(f"Failed to get image size for {image_path}: {e}")
            return None
    
    def _get_dpi_from_image(self, img: Image.Image) -> float:
        """Get DPI from image metadata."""
        try:
            # Try to get DPI from EXIF data
            dpi = img.info.get('dpi')
            if dpi:
                if isinstance(dpi, tuple):
                    # DPI can be (x, y) tuple
                    return float(dpi[0])
                return float(dpi)
        except Exception:
            pass
        
        # Default DPI if not found
        return self.DEFAULT_DPI
    
    def _image_pixels_to_mm(self, width_px: int, height_px: int, dpi: float) -> tuple[float, float]:
        """
        Convert image dimensions from pixels to millimeters.
        
        Formula: mm = (pixels / DPI) * 25.4
        """
        if dpi <= 0:
            logger.warning(f"Invalid DPI {dpi}, using default {self.DEFAULT_DPI}")
            dpi = self.DEFAULT_DPI
        
        # Convert pixels to inches, then to millimeters
        width_inches = width_px / dpi
        height_inches = height_px / dpi
        
        width_mm = width_inches * 25.4
        height_mm = height_inches * 25.4
        
        return width_mm, height_mm
