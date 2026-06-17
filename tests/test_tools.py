"""
tests/test_tools.py

Failure-mode and happy-path tests for the three FitFindr tools.
Run from the repo root with:  pytest tests/
"""

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    """Happy path: a common query returns a non-empty list of dicts."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0
    assert isinstance(results[0], dict)


def test_search_empty_results():
    """FAILURE MODE: an impossible query returns [] — never raises."""
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    """Every returned item respects the inclusive price ceiling."""
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_substring_match():
    """Size matching is substring + case-insensitive: 'M' matches 'S/M'."""
    results = search_listings("tee", size="M", max_price=100)
    assert all("m" in item["size"].lower() for item in results)


# ── suggest_outfit ────────────────────────────────────────────────────────────

def test_suggest_outfit_populated_wardrobe():
    """Happy path: returns a non-empty styling string for a real wardrobe."""
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_suggest_outfit_empty_wardrobe():
    """FAILURE MODE: empty wardrobe still returns useful advice — no crash."""
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_happy_path():
    """Happy path: a real outfit string produces a non-empty caption."""
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("paired with baggy jeans and chunky sneakers", item)
    assert isinstance(card, str)
    assert len(card.strip()) > 0


def test_create_fit_card_empty_outfit():
    """FAILURE MODE: empty outfit returns an error string — never raises."""
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("", item)
    assert isinstance(card, str)
    assert "without an outfit" in card.lower()


def test_create_fit_card_whitespace_outfit():
    """Whitespace-only outfit is also caught by the guard."""
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("   ", item)
    assert "without an outfit" in card.lower()