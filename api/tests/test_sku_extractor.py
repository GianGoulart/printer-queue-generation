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

    def test_unicode_ligature_fl(self):
        # PDF/text often has U+FB02 (ﬂ) instead of "fl"; must expand so "ﬂoyd" -> "floyd"
        assert normalize_sku("u-12-6-\uFB02oyd-m") == "u126floydm"
        assert normalize_sku("\uFB02oyd") == "floyd"


class TestExtractSKU:
    """Tests for extract_sku function. Only tenant sizing_prefixes and POSITION_SUFFIXES are used."""

    def test_simple_stem_normalized(self):
        assert extract_sku("CAM001-P.png") == "cam001p"

    def test_position_suffix_stripped_from_end(self):
        assert extract_sku("CAM_001_P_FRENTE.png") == "cam001p"
        assert extract_sku("CAM001-P-FRENTE.png") == "cam001p"
        assert extract_sku("CAM001-P-BACK.png") == "cam001p"

    def test_with_hyphens(self):
        assert extract_sku("cam-001-p.jpg") == "cam001p"

    def test_number_prefix(self):
        assert extract_sku("001-CAM-P.png") == "001camp"

    def test_no_suffix(self):
        assert extract_sku("LOGO_EMPRESA.png") == "logoempresa"

    def test_multiple_separators(self):
        assert extract_sku("BASIC-SIZE-G.jpeg") == "basicsizeg"

    def test_without_sizing_prefixes_nothing_stripped_from_start(self):
        """Without sizing_prefixes, nothing is stripped from start (only normalize)."""
        assert extract_sku("s-6-3-wolf-g4.png") == "s63wolfg4"
        assert extract_sku("s-12-1-furious4-m.png") == "s121furious4m"

    def test_with_tenant_sizing_prefixes_only_those_stripped_from_start(self):
        """With sizing_prefixes, strip prefix then leading numeric segment so design-only (e.g. butterflyp, skullgg)."""
        prefixes = ["bl-", "inf-2", "m-", "u-11", "u-12", "plus-"]
        assert extract_sku("s-6-3-wolf-g4.png", sizing_prefixes=prefixes) == "s63wolfg4"
        assert extract_sku("bl-7-4-butterfly-p.png", sizing_prefixes=prefixes) == "butterflyp"
        assert extract_sku("inf-2-8-spider6-6.png", sizing_prefixes=prefixes) == "spider66"
        assert extract_sku("u-12-7-skull-gg.png", sizing_prefixes=prefixes) == "skullgg"

    def test_empty_filename(self):
        assert extract_sku("") == ""


class TestExtractSKUVariants:
    """Tests for extract_sku_variants function."""

    def test_basic_variants(self):
        variants = extract_sku_variants("CAM001-P.png")
        assert "cam001p" in variants
        assert len(variants) >= 1

    def test_unique_variants(self):
        variants = extract_sku_variants("CAM001.png")
        # Should not have duplicates
        assert len(variants) == len(set(variants))
