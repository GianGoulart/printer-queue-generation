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
    method: str  # "regex", "heuristic", "fuzzy"
    confidence: float  # 0.0 to 1.0
    fragments_used: List[str]
    line_number: int


class ParseResult(BaseModel):
    """Result of PDF parsing."""
    skus_identificados: List[str]
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
    
    # Regex for SKU pattern: prefix-num-num-name-variant
    # Examples: inf-1-6-unicorn-4, bl-7-4-butterfly-p, u-13-8-lion-g
    SKU_PATTERN = re.compile(
        r'\b([a-z]{1,6})-(\d{1,3})-(\d{1,3})-([a-z0-9]+)-([a-z0-9]+)\b',
        re.IGNORECASE
    )
    
    # Y-coordinate tolerance for line grouping (pixels)
    Y_TOLERANCE = 1.5  # ✅ Reduzido para 1.5 (mais preciso)
    
    # Fuzzy match threshold (0.0 to 1.0)
    FUZZY_THRESHOLD = 0.75
    
    def __init__(self, valid_skus: Set[str]):
        """
        Initialize parser.
        
        Args:
            valid_skus: Set of valid SKUs from catalog
        """
        self.valid_skus = {sku.lower() for sku in valid_skus}
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
    
    def extract_skus_with_regex(self, line: Line, line_num: int) -> List[SKUMatch]:
        """
        Extract SKUs using regex pattern.
        
        Args:
            line: Line object
            line_num: Line number for tracking
            
        Returns:
            List of SKUMatch objects
        """
        matches = []
        
        for match in self.SKU_PATTERN.finditer(line.text):
            sku = match.group(0).lower()
            
            # Validate against catalog
            if sku in self.valid_skus:
                matches.append(SKUMatch(
                    sku=sku,
                    method="regex",
                    confidence=1.0,
                    fragments_used=[sku],
                    line_number=line_num
                ))
                self.logger.debug(f"Regex matched: {sku} (line {line_num})")
        
        return matches
    
    def extract_skus_with_heuristic(self, line: Line, line_num: int) -> List[SKUMatch]:
        """
        Extract SKUs using "SKU:" heuristic.
        
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
        
        # Try regex on this fragment
        for match in self.SKU_PATTERN.finditer(after_sku):
            sku = match.group(0).lower()
            
            if sku in self.valid_skus:
                matches.append(SKUMatch(
                    sku=sku,
                    method="heuristic",
                    confidence=1.0,
                    fragments_used=[sku],
                    line_number=line_num
                ))
                self.logger.debug(f"Heuristic matched: {sku} (line {line_num})")
        
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
                
                matches.append(SKUMatch(
                    sku=matched_sku,
                    method="fuzzy",
                    confidence=confidence,
                    fragments_used=[fragment],
                    line_number=line_num
                ))
                self.logger.info(
                    f"Fuzzy matched: '{fragment}' → '{matched_sku}' "
                    f"(confidence: {confidence:.2f}, line {line_num})"
                )
        
        return matches
    
    def parse(self, pdf_bytes: bytes) -> ParseResult:
        """
        Parse PDF and extract SKUs with STRICT geometric ordering (Top-to-Bottom, Left-to-Right).
        
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
                matches=[],
                fragmentos_usados=[],
                fragmentos_descartados=[],
                comentarios="No text extracted from PDF"
            )
        
        # ✅ Step 2: GEOMETRIC ORDERING - Group by page first, then by Y within each page
        pages = defaultdict(list)
        for word in words:
            pages[word.page_num].append(word)
        
        all_matches = []
        found_skus_set = set()
        found_skus_ordered = []  # ✅ This will maintain Top-Down order
        all_fragments_used = []
        line_count = 0
        
        # ✅ Process each page in order (1, 2, 3...)
        for page_num in sorted(pages.keys()):
            page_words = pages[page_num]
            
            # ✅ Group words by Y coordinate (lines) within this page
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
            
            # ✅ Sort lines by Y (Top -> Bottom)
            sorted_y_keys = sorted(y_groups.keys())
            
            # ✅ Process each line in geometric order
            for y in sorted_y_keys:
                line_count += 1
                
                # ✅ Sort words within line by X (Left -> Right)
                line_words = sorted(y_groups[y], key=lambda w: w.x0)
                line_text = " ".join(w.text for w in line_words)
                
                line_obj = Line(
                    text=line_text,
                    words=line_words,
                    y=y,
                    page_num=page_num
                )
                
                # 🔍 DEBUG: Log line position and content
                self.logger.debug(
                    f"[LINE {line_count}] Page={page_num} Y={y:.2f} Text: {line_text[:80]}..."
                )
                
                # ✅ Extract SKUs from this line (maintain order)
                current_line_matches = []
                
                # Try Regex first
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
                    fuzzy_matches = self.fuzzy_match_fragments(line_obj, line_count, found_skus_set)
                    if fuzzy_matches:
                        current_line_matches.extend(fuzzy_matches)
                
                # ✅ Add matches to global list in order found
                for match in current_line_matches:
                    if match.sku not in found_skus_set:
                        all_matches.append(match)
                        found_skus_set.add(match.sku)
                        found_skus_ordered.append(match.sku)  # ✅ Top-Down order preserved!
                        all_fragments_used.extend(match.fragments_used)
                        
                        self.logger.debug(
                            f"[SKU FOUND] Line {line_count}: {match.sku} (method: {match.method})"
                        )
        
        # Collect discarded fragments
        all_text = " ".join(
            " ".join(w.text for w in sorted(pages[p], key=lambda x: (x.y0, x.x0)))
            for p in sorted(pages.keys())
        )
        potential_skus = re.findall(r'[a-z0-9-]{5,}', all_text.lower())
        fragmentos_descartados = [
            f for f in potential_skus 
            if f not in all_fragments_used and f not in found_skus_set
        ]
        
        # Generate summary
        methods_used = defaultdict(int)
        for match in all_matches:
            methods_used[match.method] += 1
        
        comentarios = (
            f"Extracted {len(all_matches)} SKUs from {line_count} lines "
            f"across {len(pages)} page(s) in TOP-DOWN order. "
            f"Methods: {dict(methods_used)}. "
            f"Discarded {len(fragmentos_descartados)} fragments."
        )
        
        # Log first 5 SKUs for verification
        if found_skus_ordered:
            first_5 = ", ".join(found_skus_ordered[:5])
            self.logger.info(f"✅ First 5 SKUs (Top-Down): {first_5}")
        
        return ParseResult(
            skus_identificados=found_skus_ordered,  # ✅ Strict geometric order!
            matches=all_matches,
            fragmentos_usados=list(set(all_fragments_used)),
            fragmentos_descartados=fragmentos_descartados[:10],
            comentarios=comentarios
        )
