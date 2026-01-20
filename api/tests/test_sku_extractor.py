"""Tests for SKU extractor."""

import pytest

from app.services.sku_extractor import extract_sku, normalize_sku, extract_sku_variants


class TestNormalizeSKU:
    """Tests for normalize_sku function."""

    def test_lowercase(self):
        assert normalize_sku("CAM001") == "cam001"

    def test_remove_separators(self):
        assert normalize_sku("CAM-001") == "cam001"
        assert normalize_sku("CAM_001") == "cam001"
        assert normalize_sku("CAM 001") == "cam001"

    def test_remove_special_chars(self):
        assert normalize_sku("CAM@001#") == "cam001"

    def test_strip_spaces(self):
        assert normalize_sku("  CAM001  ") == "cam001"

    def test_empty_string(self):
        assert normalize_sku("") == ""

    def test_complex(self):
        assert normalize_sku("CAM-001_P FRENTE") == "cam001pfrente"


class TestExtractSKU:
    """Tests for extract_sku function."""

    def test_simple_with_size(self):
        assert extract_sku("CAM001-P.png") == "cam001"

    def test_with_underscores(self):
        assert extract_sku("CAM_001_P_FRENTE.png") == "cam001"

    def test_with_hyphens(self):
        assert extract_sku("cam-001-p.jpg") == "cam001"

    def test_number_prefix(self):
        assert extract_sku("001-CAM-P.png") == "001cam"

    def test_no_size_suffix(self):
        assert extract_sku("LOGO_EMPRESA.png") == "logoempresa"

    def test_multiple_separators(self):
        assert extract_sku("BASIC-SIZE-G.jpeg") == "basicsize"

    def test_english_sizes(self):
        assert extract_sku("SHIRT-S.png") == "shirt"
        assert extract_sku("SHIRT-XL.png") == "shirt"

    def test_position_suffixes(self):
        assert extract_sku("CAM001-P-FRENTE.png") == "cam001"
        assert extract_sku("CAM001-P-BACK.png") == "cam001"

    def test_numeric_sizes(self):
        assert extract_sku("ITEM-1.png") == "item"
        assert extract_sku("ITEM-4.png") == "item"

    def test_empty_filename(self):
        assert extract_sku("") == ""


class TestExtractSKUVariants:
    """Tests for extract_sku_variants function."""

    def test_basic_variants(self):
        variants = extract_sku_variants("CAM001-P.png")
        assert "cam001" in variants
        assert len(variants) >= 1

    def test_unique_variants(self):
        variants = extract_sku_variants("CAM001.png")
        # Should not have duplicates
        assert len(variants) == len(set(variants))
