"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


def _parse_query(query: str) -> dict:
    """Extract description, size, and max_price from a query via regex."""
    working = query

    max_price = None
    price_match = re.search(
        r"(?:under|below|less than|max|<)\s*\$?\s*(\d+(?:\.\d+)?)"
        r"|\$\s*(\d+(?:\.\d+)?)",
        working,
        flags=re.IGNORECASE,
    )
    if price_match:
        amount = price_match.group(1) or price_match.group(2)
        max_price = float(amount)
        working = working.replace(price_match.group(0), " ")

    size = None
    size_match = re.search(r"\bsize\s+([A-Za-z0-9/]+)", working, flags=re.IGNORECASE)
    if size_match:
        size = size_match.group(1).upper()
        working = working.replace(size_match.group(0), " ")
    else:
        token_match = re.search(
            r"\b(XXS|XS|S|M|L|XL|XXL|\d{1,2})\b", working, flags=re.IGNORECASE
        )
        if token_match:
            size = token_match.group(1).upper()
            working = re.sub(
                r"\b" + re.escape(token_match.group(1)) + r"\b",
                " ", working, count=1, flags=re.IGNORECASE,
            )

    description = re.sub(r"\s+", " ", working).strip()
    for filler in ["i'm looking for a", "looking for a", "looking for",
                   "i want a", "i want", "find me a", "find me", "show me"]:
        if description.lower().startswith(filler):
            description = description[len(filler):].strip()

    return {"description": description, "size": size, "max_price": max_price}

# ── planning loop ─────────────────────────────────────────────────────────────

import re

# ... (keep the existing imports and _new_session above) ...

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    (docstring unchanged — see stub)
    """
    # Step 1: Initialize the session.
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query into description, size, and max_price (regex).
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # Step 3: Search — then BRANCH on the result.
    results = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    session["search_results"] = results

    if not results:
        # ERROR BRANCH: no matches — set a specific, actionable message and
        # return early. Do NOT call suggest_outfit or create_fit_card.
        session["error"] = (
            f"No listings matched '{parsed['description']}'"
            + (f" in size {parsed['size']}" if parsed["size"] else "")
            + (f" under ${parsed['max_price']:.0f}" if parsed["max_price"] else "")
            + ". Try raising your max price, removing the size filter, "
            "or using broader keywords."
        )
        return session

    # Step 4: Select the top-ranked item.
    session["selected_item"] = results[0]

    # Step 5: Suggest an outfit using the selected item + wardrobe.
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], session["wardrobe"]
    )

    # Step 6: Create the shareable fit card.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: Return the completed session.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")