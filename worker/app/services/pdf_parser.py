"""PDF Parser Service using Docling and RobustPDFParser."""

import logging
import re
import tempfile
from pathlib import Path
from typing import List, Optional, Set

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PicklistItem(BaseModel):
    """Parsed item from picklist."""
    
    sku: str
    quantity: int
    size_label: Optional[str] = None
    position: Optional[int] = None  # ✅ Ordem no picklist original (1, 2, 3...)


class PDFParserError(Exception):
    """Base exception for PDF parsing errors."""
    pass


class PDFParserService:
    """Parse picklist PDF using RobustPDFParser (primary) or Docling (fallback)."""
    
    TIMEOUT_SECONDS = 60
    MAX_FILE_SIZE_MB = 10
    
    def __init__(self, valid_skus: Optional[Set[str]] = None):
        """
        Initialize parser.
        
        Args:
            valid_skus: Optional set of valid SKUs from catalog for validation
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.valid_skus = valid_skus or set()
    
    async def parse_pdf(self, pdf_content: bytes, filename: str = "picklist.pdf") -> List[PicklistItem]:
        """
        Extract structured data from PDF.
        
        Args:
            pdf_content: PDF file content as bytes
            filename: Original filename (for logging)
            
        Returns:
            List of PicklistItem with SKU, quantity, size
            
        Raises:
            PDFParserError: If parsing fails
        """
        self.logger.info(f"Starting PDF parsing: {filename} ({len(pdf_content)} bytes)")
        
        # Validate file size
        file_size_mb = len(pdf_content) / (1024 * 1024)
        if file_size_mb > self.MAX_FILE_SIZE_MB:
            raise PDFParserError(f"File too large: {file_size_mb:.2f}MB (max {self.MAX_FILE_SIZE_MB}MB)")
        
        # Try RobustPDFParser first (if we have valid SKUs catalog)
        if self.valid_skus:
            try:
                self.logger.info("Attempting to parse with RobustPDFParser (coordinate-based)")
                items = self._parse_with_robust_parser(pdf_content)
                
                if items:
                    self.logger.info(
                        f"✅ RobustPDFParser successfully parsed {len(items)} items from {filename}"
                    )
                    return items
                else:
                    self.logger.warning("RobustPDFParser returned no items, falling back to Docling")
            
            except Exception as e:
                self.logger.warning(f"RobustPDFParser failed: {e}, falling back to Docling")
        else:
            self.logger.info("No valid SKUs catalog provided, using Docling parser")
        
        # Fallback: Parse with Docling
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_file.write(pdf_content)
            tmp_path = Path(tmp_file.name)
        
        try:
            items = await self._parse_with_docling(tmp_path)
            
            self.logger.info(f"Docling successfully parsed {len(items)} items from {filename}")
            
            if len(items) == 0:
                raise PDFParserError("No items extracted from PDF")
            
            return items
            
        finally:
            # Cleanup temp file
            if tmp_path.exists():
                tmp_path.unlink()
    
    def _parse_with_robust_parser(self, pdf_content: bytes) -> List[PicklistItem]:
        """
        Parse PDF using RobustPDFParser (coordinate-based extraction).
        
        Args:
            pdf_content: PDF file content as bytes
            
        Returns:
            List of parsed items
        """
        try:
            from app.services.robust_pdf_parser import RobustPDFParser
            
            # Initialize parser with valid SKUs catalog
            parser = RobustPDFParser(valid_skus=self.valid_skus)
            
            # Parse PDF
            result = parser.parse(pdf_content)
            
            # Log results
            self.logger.info(f"RobustPDFParser: {result.comentarios}")
            
            if result.fragmentos_descartados:
                self.logger.debug(
                    f"Discarded fragments: {', '.join(result.fragmentos_descartados[:5])}"
                )
            
            # Convert to PicklistItem format
            items = []
            for index, sku in enumerate(result.skus_identificados, start=1):
                # Default quantity to 1 (can be enhanced later)
                items.append(PicklistItem(
                    sku=sku,
                    quantity=1,
                    size_label=None,
                    position=index  # ✅ Preservar ordem EXATA do PDF (já corrigida por page_num)
                ))
            
            self.logger.info(
                f"RobustPDFParser extracted {len(items)} SKUs in PDF order. "
                f"First 5: {[item.sku for item in items[:5]]}"
            )
            
            return items
            
        except ImportError:
            self.logger.error("RobustPDFParser not available (PyMuPDF not installed)")
            return []
        except Exception as e:
            self.logger.error(f"RobustPDFParser error: {e}", exc_info=True)
            return []
    
    async def _parse_with_docling(self, pdf_path: Path) -> List[PicklistItem]:
        """
        Parse PDF using Docling library.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of parsed items
        """
        try:
            from docling.document_converter import DocumentConverter
            
            self.logger.info(f"Parsing PDF with Docling: {pdf_path}")
            
            # Initialize converter
            converter = DocumentConverter()
            
            # Convert PDF to document
            result = converter.convert(str(pdf_path))
            
            # Extract items from document
            items = []
            
            # Get the converted document
            doc = result.document
            
            # Try to extract from tables first
            if hasattr(doc, 'tables') and doc.tables:
                self.logger.info(f"Found {len(doc.tables)} table(s)")
                for table in doc.tables:
                    try:
                        # Convert table to dataframe
                        table_data = table.export_to_dataframe()
                        
                        self.logger.debug(f"Table has {len(table_data)} rows")
                        
                        # Process each row
                        for _, row in table_data.iterrows():
                            try:
                                item = self._parse_table_row(row)
                                if item:
                                    items.append(item)
                            except Exception as e:
                                self.logger.warning(f"Failed to parse row: {e}")
                                continue
                    except Exception as e:
                        self.logger.warning(f"Failed to process table: {e}")
                        continue
            
            # Fallback: try to extract from text if no tables found
            if len(items) == 0:
                self.logger.info("No items from tables, trying text extraction")
                try:
                    text = doc.export_to_text()
                    self.logger.debug(f"Extracted text length: {len(text)}")
                    items = self._parse_from_text(text)
                except Exception as e:
                    self.logger.warning(f"Text extraction failed: {e}")
            
            # ✅ Atribuir posições na ordem de extração do PDF
            for index, item in enumerate(items, start=1):
                item.position = index
            
            self.logger.info(
                f"Docling extracted {len(items)} SKUs in PDF order. "
                f"First 5: {[item.sku for item in items[:5]]}"
            )
            
            return items
            
        except ImportError as e:
            self.logger.error(f"Import error: {e}")
            raise PDFParserError(
                "Docling library not installed. "
                "Install with: pip install docling"
            )
        except Exception as e:
            self.logger.exception(f"Docling parsing failed: {str(e)}")
            raise PDFParserError(f"Failed to parse PDF: {str(e)}")
    
    def _parse_table_row(self, row) -> Optional[PicklistItem]:
        """
        Parse a single table row into PicklistItem.
        
        Args:
            row: Pandas Series or dict-like row
            
        Returns:
            PicklistItem or None if row invalid
        """
        # Log available columns for debugging
        if hasattr(row, 'index'):
            self.logger.debug(f"Row columns: {list(row.index)}")
        elif hasattr(row, 'keys'):
            self.logger.debug(f"Row keys: {list(row.keys())}")
        
        # Try different common column name patterns (case-insensitive)
        sku_candidates = ["sku", "código", "codigo", "product", "item", "ref", "referência", "referencia"]
        qty_candidates = ["quantity", "qty", "quantidade", "qtd", "amount", "quant"]
        size_candidates = ["size", "tamanho", "tam"]
        
        sku = None
        qty = None
        size = None
        
        # Get all row keys/columns (case-insensitive)
        if hasattr(row, 'index'):
            row_keys = {str(k).lower(): k for k in row.index}
        elif hasattr(row, 'keys'):
            row_keys = {str(k).lower(): k for k in row.keys()}
        else:
            self.logger.warning(f"Unexpected row type: {type(row)}")
            return None
        
        # Extract SKU (case-insensitive)
        for col_lower in sku_candidates:
            if col_lower.lower() in row_keys:
                actual_col = row_keys[col_lower.lower()]
                if row[actual_col] and str(row[actual_col]).strip():
                    sku = str(row[actual_col]).strip()
                    self.logger.debug(f"Found SKU in column '{actual_col}': {sku}")
                    break
        
        # Extract quantity (case-insensitive)
        for col_lower in qty_candidates:
            if col_lower.lower() in row_keys:
                actual_col = row_keys[col_lower.lower()]
                if row[actual_col]:
                    try:
                        qty = int(float(str(row[actual_col])))
                        self.logger.debug(f"Found quantity in column '{actual_col}': {qty}")
                        break
                    except (ValueError, TypeError):
                        continue
        
        # Extract size (case-insensitive)
        for col_lower in size_candidates:
            if col_lower.lower() in row_keys:
                actual_col = row_keys[col_lower.lower()]
                if row[actual_col] and str(row[actual_col]).strip():
                    size = str(row[actual_col]).strip()
                    self.logger.debug(f"Found size in column '{actual_col}': {size}")
                    break
        
        # Validate minimum requirements
        if not sku or not qty:
            self.logger.debug(f"Row missing required fields - SKU: {sku}, Qty: {qty}")
            return None
        
        # Normalize data
        sku_normalized = self.normalize_sku(sku)
        size_normalized = self.normalize_size_label(size) if size else None
        
        return PicklistItem(
            sku=sku_normalized,
            quantity=qty,
            size_label=size_normalized
        )
    
    def _parse_from_text(self, text: str) -> List[PicklistItem]:
        """
        Fallback: parse items from plain text.
        
        Args:
            text: Plain text content
            
        Returns:
            List of items
        """
        self.logger.info("Attempting text-based parsing")
        
        items = []
        
        # Pattern: SKU followed by quantity and optionally size
        # Example: "CAMISA-AZUL 5 P" or "SHORT-VERM, 3, M"
        pattern = r'([A-Z0-9\-_]+)[\s,]+(\d+)[\s,]*([PMG]{1,2})?'
        
        for match in re.finditer(pattern, text, re.MULTILINE):
            sku = match.group(1)
            qty = int(match.group(2))
            size = match.group(3) if match.group(3) else None
            
            items.append(PicklistItem(
                sku=self.normalize_sku(sku),
                quantity=qty,
                size_label=self.normalize_size_label(size) if size else None
            ))
        
        self.logger.info(f"Text parsing extracted {len(items)} items")
        
        return items
    
    def normalize_sku(self, raw_sku: str) -> str:
        """
        Normalize SKU: uppercase, trim, remove special chars.
        
        Args:
            raw_sku: Raw SKU from PDF
            
        Returns:
            Normalized SKU
        """
        if not raw_sku:
            return ""
        
        # Convert to uppercase
        sku = raw_sku.upper()
        
        # Trim whitespace
        sku = sku.strip()
        
        # Remove excessive whitespace
        sku = re.sub(r'\s+', ' ', sku)
        
        # Optional: remove certain special chars that might be OCR errors
        # Keep hyphens, underscores, and alphanumeric
        # sku = re.sub(r'[^A-Z0-9\-_ ]', '', sku)
        
        return sku
    
    def normalize_size_label(self, raw_size: Optional[str]) -> Optional[str]:
        """
        Normalize size: P, M, G, GG, etc.
        
        Args:
            raw_size: Raw size from PDF
            
        Returns:
            Normalized size or None
        """
        if not raw_size:
            return None
        
        size = raw_size.upper().strip()
        
        # Map common variations
        size_map = {
            "P": "P",
            "PEQUENO": "P",
            "SMALL": "P",
            "S": "P",
            "M": "M",
            "MEDIO": "M",
            "MÉDIO": "M",
            "MEDIUM": "M",
            "G": "G",
            "GRANDE": "G",
            "LARGE": "G",
            "L": "G",
            "GG": "GG",
            "XG": "GG",
            "XL": "GG",
            "EXTRA GRANDE": "GG",
            "XLARGE": "GG",
        }
        
        return size_map.get(size, size)
