"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    (docstring unchanged — see stub)
    """
    # 1. Load all listings.
    listings = load_listings()

    # 2. Filter by max_price and size (if provided).
    candidates = []
    for item in listings:
        # Price filter (inclusive ceiling).
        if max_price is not None and item["price"] > max_price:
            continue
        # Size filter: case-insensitive substring match so "M" matches "S/M".
        if size is not None:
            if size.strip().lower() not in item["size"].lower():
                continue
        candidates.append(item)

    # 3. Score each remaining listing by keyword overlap with `description`.
    keywords = [w for w in description.lower().split() if w]
    scored = []
    for item in candidates:
        # Build one searchable text blob from the fields worth matching.
        haystack = " ".join([
            item.get("title", ""),
            item.get("description", ""),
            " ".join(item.get("style_tags", [])),
            item.get("category", ""),
            " ".join(item.get("colors", [])),
            str(item.get("brand") or ""),
        ]).lower()

        score = sum(1 for kw in keywords if kw in haystack)

        # 4. Drop any listings with a score of 0 (no relevant matches).
        if score > 0:
            scored.append((score, item))

    # 5. Sort by score, highest first, and return the listing dicts.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]

# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    (docstring unchanged — see stub)
    """
    client = _get_groq_client()

    # Pull the key details of the new item into a readable string.
    item_desc = (
        f"{new_item.get('title', 'item')} "
        f"(category: {new_item.get('category', 'n/a')}, "
        f"colors: {', '.join(new_item.get('colors', [])) or 'n/a'}, "
        f"style: {', '.join(new_item.get('style_tags', [])) or 'n/a'})"
    )

    items = wardrobe.get("items", [])

    # 1 & 2. Empty wardrobe → general styling advice.
    if not items:
        prompt = (
            f"A user just found this secondhand item:\n{item_desc}\n\n"
            "They don't have a wardrobe saved yet. Suggest how to style this piece "
            "from scratch: what categories of items (bottoms, shoes, outerwear) and "
            "colors pair well with it, and what overall vibe or occasion it suits. "
            "Give 1–2 concrete outfit ideas. Keep it to 3–4 sentences, friendly and "
            "specific. Do not invent items the user owns."
        )
    # 3. Non-empty wardrobe → suggest combos using named owned pieces.
    else:
        wardrobe_lines = "\n".join(
            f"- {it['name']} (category: {it['category']}, "
            f"colors: {', '.join(it.get('colors', []))})"
            for it in items
        )
        prompt = (
            f"A user just found this secondhand item:\n{item_desc}\n\n"
            f"Here is their current wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1–2 complete outfit combinations that pair the NEW item with "
            "specific pieces named from their wardrobe above. Refer to the wardrobe "
            "pieces by name. Keep it to 3–4 sentences, friendly and specific. "
            "Only use items that appear in the wardrobe list."
        )

    # 4. Call the LLM and return the response string.
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a thoughtful personal stylist who gives "
                    "specific, wearable outfit advice for secondhand fashion finds.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        # Network/API failure — return a usable string, never crash the agent.
        return (
            f"Couldn't generate a styling suggestion right now ({e}). "
            "Try pairing this piece with neutral basics and your go-to shoes."
        )


# ── Tool 3: create_fit_card ────────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    (docstring unchanged — see stub)
    """
    # 1. Guard against an empty or whitespace-only outfit string.
    if not outfit or not outfit.strip():
        return (
            "Can't create a fit card without an outfit suggestion — "
            "try styling the item first."
        )

    client = _get_groq_client()

    # Pull the details we want mentioned naturally in the caption.
    title = new_item.get("title", "this piece")
    price = new_item.get("price")
    platform = new_item.get("platform", "")
    price_str = f"${price:.0f}" if isinstance(price, (int, float)) else ""

    # 2. Build the prompt with item details + outfit + style guidelines.
    prompt = (
        f"Write a short, casual social-media caption for a thrifted outfit post.\n\n"
        f"Item: {title}\n"
        f"Price: {price_str}\n"
        f"Bought on: {platform}\n"
        f"Outfit it's styled in: {outfit}\n\n"
        "Guidelines:\n"
        "- 2 to 4 sentences, like a real Instagram/TikTok OOTD caption.\n"
        "- Casual and authentic — NOT a product description.\n"
        f"- Mention the item name, the price ({price_str}), and the platform "
        f"({platform}) naturally, once each.\n"
        "- Capture the outfit vibe in specific terms.\n"
        "- A tasteful emoji or two is fine. No hashtag spam."
    )

    # 3. Call the LLM (higher temperature for variety) and return the response.
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You write fun, authentic-sounding outfit captions "
                    "for secondhand fashion finds — the kind people actually post.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=1.0,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        # Network/API failure — return a usable string, never crash the agent.
        return f"Couldn't generate a fit card right now ({e})."