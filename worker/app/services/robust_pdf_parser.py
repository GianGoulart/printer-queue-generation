"""Robust PDF Parser with coordinate-based text extraction."""

import difflib
import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import fitz  # PyMuPDF
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Word(BaseModel):
    """Extracted word with coordinates."""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page_num: int  # ✅ Número da página (0-indexed)


class Line(BaseModel):
    """Reconstructed line of text."""
    text: str
    words: List[Word]
    y: float
    page_num: int  # ✅ Número da página


class SKUMatch(BaseModel):
    """Matched SKU with metadata."""
    sku: str
    quantity: Optional[int] = None  # ✅ Quantidade extraída da mesma linha
    method: str  # "regex", "heuristic", "fuzzy", "layout"
    confidence: float  # 0.0 to 1.0
    fragments_used: List[str]
    line_number: int
    layout_id: Optional[int] = None  # When method=="layout", which tenant layout matched


class SKUWithQuantity(BaseModel):
    """SKU with its quantity."""
    sku: str
    quantity: int


class ParseResult(BaseModel):
    """Result of PDF parsing."""
    skus_identificados: List[str]
    skus_with_quantities: List[SKUWithQuantity]  # ✅ SKUs com quantidades
    matches: List[SKUMatch]
    fragmentos_usados: List[str]
    fragmentos_descartados: List[str]
    comentarios: str


class RobustPDFParser:
    """
    Robust PDF parser that handles complex layouts.
    
    Features:
    - Extracts words with coordinates (x, y)
    - Reconstructs lines by Y-coordinate grouping
    - Uses regex + heuristics to find SKUs
    - Validates against catalog with fuzzy matching
    """
    
    # Regex for SKU patterns (multiple formats supported):
    # 1. Standard 5-segment: prefix-num-num-name-variant (e.g., inf-1-6-unicorn-4, bl-7-4-butterfly-p)
    # 2. Standard 4-segment: prefix-num-num-name (e.g., bl-13-9-flamingo)
    # 3. Simple: alphanumeric (e.g., b99, hallowen)
    # 4. With file extension: any of above + .png/.jpg/etc
    SKU_PATTERN_STANDARD_5 = re.compile(
        r'\b([a-z]{1,6})-(\d{1,3})-(\d{1,3})-([a-z0-9]+)-([a-z0-9]+)(?:\.(?:png|jpg|jpeg|gif|pdf))?\b',
        re.IGNORECASE
    )
    SKU_PATTERN_STANDARD_4 = re.compile(
        r'\b([a-z]{1,6})-(\d{1,3})-(\d{1,3})-([a-z0-9]+)(?:\.(?:png|jpg|jpeg|gif|pdf))?\b',
        re.IGNORECASE
    )
    # Simple SKU pattern: alphanumeric, at least 2 chars, no spaces
    SKU_PATTERN_SIMPLE = re.compile(
        r'\b([a-z0-9]{2,})(?:\.(?:png|jpg|jpeg|gif|pdf))?\b',
        re.IGNORECASE
    )
    
    # Y-coordinate tolerance for line grouping (pixels)
    Y_TOLERANCE = 1.5  # ✅ Reduzido para 1.5 (mais preciso)
    
    # Fuzzy match threshold (0.0 to 1.0)
    FUZZY_THRESHOLD = 0.75
    
    # Pattern to match quantities (numbers)
    QUANTITY_PATTERN = re.compile(r'\b(\d+)\b')
    
    def __init__(
        self,
        valid_skus: Set[str],
        tenant_layouts: Optional[List[dict]] = None,
    ):
        """
        Initialize parser.

        Args:
            valid_skus: Set of valid SKUs from catalog
            tenant_layouts: Optional list of tenant SKU layouts (priority order).
                Each dict: id, name, pattern, pattern_type, allow_hyphen_variants
        """
        self.valid_skus = {sku.lower() for sku in valid_skus}
        self.tenant_layouts = tenant_layouts or []
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def extract_words_with_coordinates(self, pdf_bytes: bytes) -> List[Word]:
        """
        Extract all words with their coordinates from PDF.
        
        Args:
            pdf_bytes: PDF file content
            
        Returns:
            List of Word objects
        """
        words = []
        
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            for page_num, page in enumerate(doc):
                # Extract words with coordinates
                word_list = page.get_text("words")  # Returns: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
                
                for w in word_list:
                    words.append(Word(
                    text=w[4],
                    x0=w[0],
                    y0=w[1],
                    x1=w[2],
                    y1=w[3],
                    page_num=page_num  # ✅ Preservar número da página
                    ))
            
            doc.close()
            self.logger.info(f"Extracted {len(words)} words from PDF")
            
        except Exception as e:
            self.logger.error(f"Failed to extract words: {e}")
            raise
        
        return words
    
    def reconstruct_lines(self, words: List[Word]) -> List[Line]:
        """
        Reconstruct lines by grouping words with similar Y coordinates within each page.
        
        Args:
            words: List of extracted words
            
        Returns:
            List of Line objects, sorted by (page_num, Y position)
        """
        # ✅ Group words by page first
        pages = defaultdict(list)
        for word in words:
            pages[word.page_num].append(word)
        
        lines = []
        
        # ✅ Process each page in order
        for page_num in sorted(pages.keys()):
            page_words = pages[page_num]
            
            # Group words by Y coordinate within this page
            y_groups = defaultdict(list)
            
            for word in page_words:
                # Find existing group within tolerance
                found_group = False
                for y_key in y_groups.keys():
                    if abs(word.y0 - y_key) <= self.Y_TOLERANCE:
                        y_groups[y_key].append(word)
                        found_group = True
                        break
                
                if not found_group:
                    y_groups[word.y0].append(word)
            
            # Sort each group by X coordinate and create lines
            for y, group_words in sorted(y_groups.items()):
                sorted_words = sorted(group_words, key=lambda w: w.x0)
                line_text = " ".join(w.text for w in sorted_words)
                
                lines.append(Line(
                    text=line_text,
                    words=sorted_words,
                    y=y,
                    page_num=page_num  # ✅ Preservar número da página
                ))
        
        self.logger.info(f"Reconstructed {len(lines)} lines from {len(pages)} pages")
        return lines
    
    def extract_quantity_from_line(self, line: Line, sku_match_end: int) -> Optional[int]:
        """
        Extract quantity from the same line, looking for numbers after the SKU.
        
        In table format like "SKU  Imagem  Quantidade", the quantity is typically
        the last number in the line or the number after the SKU.
        
        Args:
            line: Line object
            sku_match_end: End position of SKU match in line text
            
        Returns:
            Quantity if found, None otherwise
        """
        # Look for numbers in the line text after the SKU
        remaining_text = line.text[sku_match_end:].strip()
        
        # Skip common separators (tabs, spaces, etc.)
        remaining_text = remaining_text.lstrip('\t \n\r')
        
        # Try to find a number that looks like a quantity (typically 1-4 digits)
        # Look for standalone numbers (not part of other text)
        quantity_matches = self.QUANTITY_PATTERN.findall(remaining_text)
        
        if quantity_matches:
            # In table format, the quantity is usually the last number in the line
            # or the first number after the SKU (if there's an image column)
            # Try the last number first (most likely to be quantity in a table)
            try:
                quantity = int(quantity_matches[-1])
                # Sanity check: quantities are usually between 1 and 999
                if 1 <= quantity <= 999:
                    self.logger.debug(f"Extracted quantity {quantity} from line: {line.text[:80]}")
                    return quantity
            except (ValueError, IndexError):
                pass
            
            # Fallback: try the first number
            try:
                quantity = int(quantity_matches[0])
                if 1 <= quantity <= 999:
                    self.logger.debug(f"Extracted quantity {quantity} (first match) from line: {line.text[:80]}")
                    return quantity
            except (ValueError, IndexError):
                pass
        
        return None
    
    def normalize_sku_from_pdf(self, raw_sku: str) -> str:
        """
        Normalize SKU extracted from PDF to match catalog format.
        
        Normalization rules (same as sku_extractor.normalize_sku):
        - Convert to lowercase
        - Remove separators (-, _, spaces)
        - Keep only alphanumeric characters
        - Remove file extension if present
        
        Args:
            raw_sku: Raw SKU from PDF (may include .png, .jpg, etc.)
            
        Returns:
            Normalized SKU (lowercase, no separators, no extension)
        """
        if not raw_sku:
            return ""
        # Expand Unicode ligatures (e.g. PDF "ﬂoyd" -> "floyd") so they are not stripped by [^a-z0-9]
        _ligatures = (("\uFB02", "fl"), ("\uFB01", "fi"), ("\uFB00", "ff"), ("\uFB04", "ffl"), ("\uFB03", "ffi"))
        sku = raw_sku.lower()
        for lig, ascii_eq in _ligatures:
            sku = sku.replace(lig, ascii_eq)
        if '.' in sku:
            sku = sku.rsplit('.', 1)[0]
        sku = sku.replace("-", "").replace("_", "").replace(" ", "")
        sku = re.sub(r"[^a-z0-9]", "", sku)
        return sku
    
    def extract_skus_with_regex(self, line: Line, line_num: int) -> List[SKUMatch]:
        """
        Extract SKUs using regex patterns, also extracting quantities when available.
        Supports both standard format (prefix-num-num-name-variant) and simple format (alphanumeric).
        
        Args:
            line: Line object
            line_num: Line number for tracking
            
        Returns:
            List of SKUMatch objects
        """
        matches = []
        found_positions = set()  # Track positions to avoid duplicates
        
        # Try standard 5-segment pattern first (prefix-num-num-name-variant)
        for match in self.SKU_PATTERN_STANDARD_5.finditer(line.text):
            raw_sku = match.group(0).lower()
            start_pos = match.start()
            end_pos = match.end()
            
            # Skip if already found at this position (avoid duplicates)
            if (start_pos, end_pos) in found_positions:
                continue
            found_positions.add((start_pos, end_pos))
            
            # Store raw token from picklist (e.g. u-7-4-butterfly-p); resolver normalizes for lookup
            raw_stored = raw_sku.rsplit(".", 1)[0] if "." in raw_sku else raw_sku
            sku_norm = self.normalize_sku_from_pdf(raw_sku)
            if self.valid_skus and sku_norm not in self.valid_skus:
                self.logger.debug(
                    f"SKU '{sku_norm}' (from '{raw_sku}') matches pattern but not in catalog. "
                    f"Will be marked as 'missing' in resolution phase (line {line_num})"
                )
            quantity = self.extract_quantity_from_line(line, end_pos)
            matches.append(SKUMatch(
                sku=raw_stored,
                quantity=quantity,
                method="regex",
                confidence=1.0,
                fragments_used=[raw_sku],
                line_number=line_num
            ))
            if quantity:
                self.logger.debug(f"Regex matched (standard 5-seg): {raw_stored} (from {raw_sku}) with quantity {quantity} (line {line_num})")
            else:
                self.logger.debug(f"Regex matched (standard 5-seg): {raw_stored} (from {raw_sku}) (line {line_num}, no quantity found)")
        
        # Try standard 4-segment pattern (prefix-num-num-name) - e.g., bl-13-9-flamingo
        for match in self.SKU_PATTERN_STANDARD_4.finditer(line.text):
            raw_sku = match.group(0).lower()
            start_pos = match.start()
            end_pos = match.end()
            
            # Skip if already found at this position (avoid duplicates)
            if (start_pos, end_pos) in found_positions:
                continue
            found_positions.add((start_pos, end_pos))
            
            raw_stored = raw_sku.rsplit(".", 1)[0] if "." in raw_sku else raw_sku
            sku_norm = self.normalize_sku_from_pdf(raw_sku)
            if self.valid_skus and sku_norm not in self.valid_skus:
                self.logger.debug(
                    f"SKU '{sku_norm}' (from '{raw_sku}') matches 4-segment pattern but not in catalog. "
                    f"Will be marked as 'missing' in resolution phase (line {line_num})"
                )
            quantity = self.extract_quantity_from_line(line, end_pos)
            matches.append(SKUMatch(
                sku=raw_stored,
                quantity=quantity,
                method="regex",
                confidence=1.0,
                fragments_used=[raw_sku],
                line_number=line_num
            ))
            if quantity:
                self.logger.debug(f"Regex matched (standard 4-seg): {raw_stored} (from {raw_sku}) with quantity {quantity} (line {line_num})")
            else:
                self.logger.debug(f"Regex matched (standard 4-seg): {raw_stored} (from {raw_sku}) (line {line_num}, no quantity found)")
        
        # Try simple pattern for SKUs that don't match standard format (e.g., b99, hallowen)
        # Only if no standard matches found to avoid false positives
        if not matches:
            # Common words to exclude (Portuguese and English)
            excluded_words = {
                'sku', 'imagem', 'quantidade', 'qtd', 'page', 'of', 'picklist',
                'itens', 'skus', 'repetidos', 'com', 'variadas', 'total',
                'p', 'm', 'g', 'gg', 'xg', 'pp', 's', 'l', 'xl', 'xxl',
                'bl', 'inf', 'plus', 'u', 's', 'm'  # Common prefixes (too short alone)
            }
            
            for match in self.SKU_PATTERN_SIMPLE.finditer(line.text):
                raw_sku = match.group(0).lower()
                start_pos = match.start()
                end_pos = match.end()
                
                # Skip if already found at this position
                if (start_pos, end_pos) in found_positions:
                    continue
                
                # Filter out common words that are not SKUs
                if len(raw_sku) < 3:  # Minimum 3 characters for simple SKUs
                    continue
                if raw_sku.isdigit() and len(raw_sku) < 3:  # Skip single/double digits
                    continue
                if raw_sku in excluded_words:
                    continue
                
                # Skip if it's just a number (not a SKU)
                if raw_sku.isdigit():
                    continue
                
                # Skip if it's a common size label (P, M, G, GG, etc.)
                if raw_sku in ['p', 'm', 'g', 'gg', 'xg', 'pp', 's', 'l', 'xl', 'xxl', 'xxxl']:
                    continue
                
                sku = self.normalize_sku_from_pdf(raw_sku)
                raw_stored = raw_sku.rsplit(".", 1)[0] if "." in raw_sku else raw_sku
                if len(sku) >= 3 and any(c.isalpha() for c in sku) and not sku.isdigit():
                    is_valid_format = (
                        any(c.isdigit() for c in sku) or
                        len(sku) >= 4
                    )
                    if is_valid_format:
                        found_positions.add((start_pos, end_pos))
                        if self.valid_skus and sku not in self.valid_skus:
                            self.logger.debug(
                                f"SKU '{sku}' (from '{raw_sku}') matches simple pattern but not in catalog. "
                                f"Will be marked as 'missing' in resolution phase (line {line_num})"
                            )
                        quantity = self.extract_quantity_from_line(line, end_pos)
                        matches.append(SKUMatch(
                            sku=raw_stored,
                            quantity=quantity,
                            method="regex",
                            confidence=0.8,
                            fragments_used=[raw_sku],
                            line_number=line_num
                        ))
                        if quantity:
                            self.logger.debug(f"Regex matched (simple): {raw_stored} (from {raw_sku}) with quantity {quantity} (line {line_num})")
                        else:
                            self.logger.debug(f"Regex matched (simple): {raw_stored} (from {raw_sku}) (line {line_num}, no quantity found)")
        
        return matches
    
    def extract_skus_with_heuristic(self, line: Line, line_num: int) -> List[SKUMatch]:
        """
        Extract SKUs using "SKU:" heuristic, also extracting quantities when available.
        
        Looks for pattern: "SKU: xxx-xxx-xxx" or "SKU:xxx-xxx-xxx"
        
        Args:
            line: Line object
            line_num: Line number for tracking
            
        Returns:
            List of SKUMatch objects
        """
        matches = []
        
        # Look for "SKU" keyword
        text_lower = line.text.lower()
        if "sku" not in text_lower:
            return matches
        
        # Find position of "SKU" and extract text after it
        sku_index = text_lower.find("sku")
        after_sku = line.text[sku_index + 3:].strip()
        
        # Remove common separators
        after_sku = after_sku.lstrip(":").strip()
        
        for match in self.SKU_PATTERN_STANDARD_5.finditer(after_sku):
            raw_sku = match.group(0).lower()
            sku_match_end = sku_index + 3 + match.end()
            raw_stored = raw_sku.rsplit(".", 1)[0] if "." in raw_sku else raw_sku
            sku_norm = self.normalize_sku_from_pdf(raw_sku)
            if self.valid_skus and sku_norm not in self.valid_skus:
                self.logger.debug(
                    f"SKU '{sku_norm}' (from '{raw_sku}') matches pattern but not in catalog. "
                    f"Will be marked as 'missing' in resolution phase (line {line_num})"
                )
            quantity = self.extract_quantity_from_line(line, sku_match_end)
            matches.append(SKUMatch(
                sku=raw_stored,
                quantity=quantity,
                method="heuristic",
                confidence=1.0,
                fragments_used=[raw_sku],
                line_number=line_num
            ))
            if quantity:
                self.logger.debug(f"Heuristic matched: {raw_stored} (from {raw_sku}) with quantity {quantity} (line {line_num})")
            else:
                self.logger.debug(f"Heuristic matched: {raw_stored} (from {raw_sku}) (line {line_num}, no quantity found)")
        
        if not matches:
            for match in self.SKU_PATTERN_STANDARD_4.finditer(after_sku):
                raw_sku = match.group(0).lower()
                sku_match_end = sku_index + 3 + match.end()
                raw_stored = raw_sku.rsplit(".", 1)[0] if "." in raw_sku else raw_sku
                sku_norm = self.normalize_sku_from_pdf(raw_sku)
                if self.valid_skus and sku_norm not in self.valid_skus:
                    self.logger.debug(
                        f"SKU '{sku_norm}' (from '{raw_sku}') matches 4-segment pattern but not in catalog. "
                        f"Will be marked as 'missing' in resolution phase (line {line_num})"
                    )
                quantity = self.extract_quantity_from_line(line, sku_match_end)
                matches.append(SKUMatch(
                    sku=raw_stored,
                    quantity=quantity,
                    method="heuristic",
                    confidence=1.0,
                    fragments_used=[raw_sku],
                    line_number=line_num
                ))
                if quantity:
                    self.logger.debug(f"Heuristic matched (4-seg): {raw_stored} (from {raw_sku}) with quantity {quantity} (line {line_num})")
                else:
                    self.logger.debug(f"Heuristic matched (4-seg): {raw_stored} (from {raw_sku}) (line {line_num}, no quantity found)")
        
        return matches
    
    def fuzzy_match_fragments(
        self, 
        line: Line, 
        line_num: int,
        already_found: Set[str]
    ) -> List[SKUMatch]:
        """
        Try fuzzy matching for broken SKUs.
        
        Args:
            line: Line object
            line_num: Line number
            already_found: SKUs already found (to avoid duplicates)
            
        Returns:
            List of SKUMatch objects
        """
        matches = []
        
        # Extract potential SKU-like fragments
        # Look for patterns with dashes
        fragments = re.findall(r'[a-z0-9-]{5,}', line.text.lower())
        
        for fragment in fragments:
            if fragment in already_found:
                continue
            
            # Try fuzzy match against catalog
            close_matches = difflib.get_close_matches(
                fragment,
                self.valid_skus,
                n=1,
                cutoff=self.FUZZY_THRESHOLD
            )
            
            if close_matches:
                matched_sku = close_matches[0]
                confidence = difflib.SequenceMatcher(None, fragment, matched_sku).ratio()
                
                # Try to find the fragment position in the line to extract quantity
                fragment_pos = line.text.lower().find(fragment)
                if fragment_pos >= 0:
                    sku_match_end = fragment_pos + len(fragment)
                    quantity = self.extract_quantity_from_line(line, sku_match_end)
                else:
                    quantity = None
                
                matches.append(SKUMatch(
                    sku=matched_sku,
                    quantity=quantity,
                    method="fuzzy",
                    confidence=confidence,
                    fragments_used=[fragment],
                    line_number=line_num
                ))
                if quantity:
                    self.logger.info(
                        f"Fuzzy matched: '{fragment}' → '{matched_sku}' "
                        f"with quantity {quantity} (confidence: {confidence:.2f}, line {line_num})"
                    )
                else:
                    self.logger.info(
                        f"Fuzzy matched: '{fragment}' → '{matched_sku}' "
                        f"(confidence: {confidence:.2f}, line {line_num})"
                    )
        
        return matches
    
    def parse(self, pdf_bytes: bytes) -> ParseResult:
        """
        Parse PDF and extract SKUs with STRICT geometric ordering (Top-to-Bottom, Left-to-Right).
        Includes improved global post-processing to remove partial SKUs that are prefixes of longer SKUs.
        
        Args:
            pdf_bytes: PDF file content
            
        Returns:
            ParseResult with matched SKUs and metadata
        """
        # Step 1: Extract words with coordinates
        words = self.extract_words_with_coordinates(pdf_bytes)
        
        if not words:
            return ParseResult(
                skus_identificados=[],
                skus_with_quantities=[],
                matches=[],
                fragmentos_usados=[],
                fragmentos_descartados=[],
                comentarios="No text extracted from PDF"
            )
        
        # Group words by page first
        pages = defaultdict(list)
        for word in words:
            pages[word.page_num].append(word)
        
        all_matches = []
        found_skus_ordered = []  # Maintain Top-Down order
        all_fragments_used = []
        line_count = 0
        
        # Process each page in order
        for page_num in sorted(pages.keys()):
            page_words = pages[page_num]
            
            # Group words by Y coordinate (lines) within this page
            y_groups = defaultdict(list)
            for word in page_words:
                found_group = False
                for y_key in y_groups.keys():
                    if abs(word.y0 - y_key) <= self.Y_TOLERANCE:
                        y_groups[y_key].append(word)
                        found_group = True
                        break
                if not found_group:
                    y_groups[word.y0].append(word)
            
            # Sort lines by Y (Top -> Bottom)
            sorted_y_keys = sorted(y_groups.keys())
            
            # Process each line in geometric order
            for y in sorted_y_keys:
                line_count += 1
                
                # Sort words within line by X (Left -> Right)
                line_words = sorted(y_groups[y], key=lambda w: w.x0)
                line_text = " ".join(w.text for w in line_words)
                
                line_obj = Line(
                    text=line_text,
                    words=line_words,
                    y=y,
                    page_num=page_num
                )
                
                # Extract SKUs from this line (maintain order)
                current_line_matches = []

                # Use first token only (SKU before space/quantity) for full-line match.
                line_first_token = (line_text.split() or [""])[0].strip()
                line_first_token_normalized = self.normalize_sku_from_pdf(line_first_token) if line_first_token else ""

                # Skip header line (e.g. "picklist 150") — do not add any match for this line
                if line_first_token_normalized == "picklist":
                    self.logger.debug(f"Skipping header line {line_count}: first token 'picklist'")
                    continue

                # Try tenant SKU layouts first (priority order).
                # full_line=True so a 4-segment layout only matches lines with exactly 4 segments,
                # not "inf-9-4-naruto" inside "inf-9-4-naruto-m" (5 segments).
                if self.tenant_layouts and line_first_token:
                    from app.services.layout_matcher import find_matches as layout_find_matches
                    for layout in self.tenant_layouts:
                        raw_matches = layout_find_matches(
                            line_first_token,
                            pattern=layout.get("pattern", ""),
                            pattern_type=layout.get("pattern_type", "regex"),
                            allow_hyphen_variants=layout.get("allow_hyphen_variants", True),
                            full_line=True,
                        )
                        if raw_matches:
                            layout_id = layout.get("id")
                            layout_name = layout.get("name", "")
                            for full_match, _start, end_pos, groups in raw_matches:
                                # Store raw token from picklist (e.g. bl-7-4-butterfly-p) so item.sku matches PDF; resolver normalizes for lookup
                                raw_sku = full_match.rsplit(".", 1)[0] if "." in full_match else full_match
                                quantity = self.extract_quantity_from_line(line_obj, end_pos)
                                current_line_matches.append(SKUMatch(
                                    sku=raw_sku,
                                    quantity=quantity,
                                    method="layout",
                                    confidence=1.0,
                                    fragments_used=[full_match],
                                    line_number=line_count,
                                    layout_id=layout_id,
                                ))
                            self.logger.debug(
                                f"Layout '{layout_name}' (id={layout_id}) matched line {line_count}: {[m.sku for m in current_line_matches]}"
                            )
                            break

                # Fallback: try built-in Regex
                if not current_line_matches:
                    regex_matches = self.extract_skus_with_regex(line_obj, line_count)
                    if regex_matches:
                        current_line_matches.extend(regex_matches)

                # Try Heuristic if no regex match
                if not current_line_matches:
                    heuristic_matches = self.extract_skus_with_heuristic(line_obj, line_count)
                    if heuristic_matches:
                        current_line_matches.extend(heuristic_matches)
                
                # Try Fuzzy matching as last resort
                if not current_line_matches:
                    fuzzy_matches = self.fuzzy_match_fragments(line_obj, line_count, set())
                    if fuzzy_matches:
                        current_line_matches.extend(fuzzy_matches)
                
                # Last resort: if line has no match but has a first token that looks like a SKU,
                # use it so we don't lose the line (150 lines -> 150 items).
                # Do NOT use first_token when it is purely numeric (e.g. "1", "2", "10", "150" — line numbers).
                if not current_line_matches and line_first_token:
                    first_token_normalized = self.normalize_sku_from_pdf(line_first_token)
                    if (
                        len(first_token_normalized) >= 2
                        and first_token_normalized.isalnum()
                        and not first_token_normalized.isdigit()
                    ):
                        quantity = self.extract_quantity_from_line(line_obj, len(line_first_token))
                        raw_first = line_first_token.rsplit(".", 1)[0] if "." in line_first_token else line_first_token
                        current_line_matches.append(SKUMatch(
                            sku=raw_first,
                            quantity=quantity,
                            method="first_token",
                            confidence=0.5,
                            fragments_used=[line_first_token],
                            line_number=line_count,
                        ))
                        self.logger.debug(
                            f"Line {line_count} had no layout/regex/heuristic/fuzzy match; "
                            f"using first token as SKU: {raw_first}"
                        )
                
                # Drop numeric-only SKUs (line numbers like "1", "2", ... "150" mistaken as SKUs)
                current_line_matches = [m for m in current_line_matches if not (m.sku and m.sku.isdigit())]
                
                # Add ALL matches to global list in order found (allow duplicates)
                for match in current_line_matches:
                    all_matches.append(match)
                    found_skus_ordered.append(match.sku)
                    all_fragments_used.extend(match.fragments_used)
        
        # Prefix filter: only drop a match when on the SAME line another match is the
        # longer form (so we never drop a line; we only drop duplicate "short" on same line).
        matches_by_line: Dict[int, List[SKUMatch]] = defaultdict(list)
        for m in all_matches:
            matches_by_line[m.line_number].append(m)
        filtered_matches = []
        for _lnum in sorted(matches_by_line.keys()):
            line_matches = matches_by_line[_lnum]
            to_keep = []
            for m in line_matches:
                is_prefix_of_same_line = False
                for other in line_matches:
                    if other.sku != m.sku and other.sku.startswith(m.sku) and len(other.sku) - len(m.sku) <= 3:
                        is_prefix_of_same_line = True
                        break
                if not is_prefix_of_same_line:
                    to_keep.append(m)
            filtered_matches.extend(to_keep)
        
        # Post-filter: drop header/numeric-only SKUs that may have slipped through (e.g. from regex on other columns).
        filtered_matches = [
            m for m in filtered_matches
            if m.sku and m.sku != "picklist" and not m.sku.isdigit()
        ]
        filtered_skus = list(dict.fromkeys(m.sku for m in filtered_matches))
        
        # Build final ordered list of SKUs with quantities
        skus_with_quantities = []
        for match in filtered_matches:
            quantity = match.quantity if match.quantity is not None else 1
            skus_with_quantities.append(SKUWithQuantity(
                sku=match.sku,
                quantity=quantity
            ))
        
        # Collect discarded fragments
        all_text = " ".join(
            " ".join(w.text for w in sorted(pages[p], key=lambda x: (x.y0, x.x0)))
            for p in sorted(pages.keys())
        )
        potential_skus = re.findall(r'[a-z0-9-]{5,}', all_text.lower())
        unique_filtered_skus = set(filtered_skus)
        fragmentos_descartados = [
            f for f in potential_skus 
            if f not in all_fragments_used and f not in unique_filtered_skus
        ]
        
        # Generate summary
        methods_used = defaultdict(int)
        for match in filtered_matches:
            methods_used[match.method] += 1
        first_token_count = methods_used.get("first_token", 0)
        if first_token_count:
            self.logger.info(
                f"Lines with no layout/regex/heuristic/fuzzy match used first_token fallback: {first_token_count}"
            )
        
        comentarios = (
            f"Extracted {len(filtered_matches)} SKUs from {line_count} lines "
            f"across {len(pages)} page(s) in TOP-DOWN order after improved filtering. "
            f"Methods: {dict(methods_used)}. "
            f"Discarded {len(fragmentos_descartados)} fragments."
        )
        
        # Log first 5 SKUs for verification
        if filtered_skus:
            first_5 = ", ".join(filtered_skus[:5])
            self.logger.info(f"✅ First 5 SKUs (Top-Down, filtered): {first_5}")
        
        quantities_found = sum(1 for match in filtered_matches if match.quantity is not None)
        if quantities_found > 0:
            self.logger.info(
                f"✅ Extracted quantities for {quantities_found}/{len(filtered_matches)} SKUs"
            )
        
        return ParseResult(
            skus_identificados=filtered_skus,
            skus_with_quantities=skus_with_quantities,
            matches=filtered_matches,
            fragmentos_usados=list(set(all_fragments_used)),
            fragmentos_descartados=fragmentos_descartados[:10],
            comentarios=comentarios
        )