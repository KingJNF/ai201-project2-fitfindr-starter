# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the
 four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for secondhand items matching the user's keywords, with optional size and price filters. Returns the best matches ranked by how well they fit the description.

**Input parameters:**
- `description` (str): Free-text keywords describing the desired item (e.g., "vintage graphic tee"). Used for relevance scoring against each listing's title, description, and style_tags.
- `size` (str | None): Size string to filter by, or None to skip size filtering. Matching is case-insensitive and substring-based so "M" matches "S/M".
- `max_price` (float| None): Inclusive price ceiling, or None to skip price filtering. Listings priced above this value are excluded.

**What it returns:**
A `list[dict]`, sorted by relevance (best match first). Each dict is a full listing with these fields:
`id` (str), `title` (str), `description` (str), `category` (str),
`style_tags` (list[str]), `size` (str), `condition` (str), `price` (float),
`colors` (list[str]), `brand` (str | None), `platform` (str).
Returns an empty list `[]` when nothing matches.

**What happens if it fails or returns nothing:**
The tool returns `[]` rather than raising. The planning loop detects the empty
list, sets a helpful message in `session["error"]` telling the user what failed
and what to adjust (e.g., raise the price or drop the size filter), and returns
early without calling suggest_outfit or create_fit_card.

---

### Tool 2: suggest_outfit

**What it does:**
Given a found item and the user's wardrobe, calls the LLM to generate 1–2 complete outfit combinations that pair the new item with named pieces the user already owns.

**Input parameters:**
- `new_item` (dict): A listing dict (the item from search_listings the user is considering). The tool uses its title, category, colors, and style_tags to ground the suggestion.
- `wardrobe` (dict): A wardrobe dict with an `items` key holding a list of wardrobe item dicts. Each wardrobe item has `id`, `name`, `category`, `colors`, `style_tags`, and optional `notes`. The list may be empty.

**What it returns:**
A non-empty `str` containing the styling suggestion — specific outfit combinations referencing the new item plus named wardrobe pieces (or general styling advice if the wardrobe is empty).

**What happens if it fails or returns nothing:**
If `wardrobe['items']` is empty, the tool does not crash — it prompts the LLM for general styling advice for the item (what kinds of pieces pair well, what vibe it suits) and returns that string. The agent therefore always receives usable styling text to pass into create_fit_card.

---

### Tool 3: create_fit_card

**What it does:**
Calls the LLM to turn an outfit suggestion and the new item into a short, casual, shareable caption.

**Input parameters:**

* `outfit` (str): The outfit suggestion string returned by suggest_outfit().
* `new_item` (dict): The listing dict for the thrifted item, used to mention the item name, price, and platform naturally in the caption.

**What it returns:**
A `str` of roughly 2–4 sentences usable as an Instagram/TikTok caption. It is generated at a higher LLM temperature so it varies for different inputs rather than reading like a fixed product description.


**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, the tool does NOT call the LLM. It returns a descriptive error-message string (e.g., "Can't create a fit card without an outfit suggestion. Try styling the item first.") instead of raising an exception, so the agent stays alive and can surface the message to the user.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop runs in `run_agent(query, wardrobe)` and is a sequence of conditional steps that read from and write to a single `session` dict. The agent's behavior changes based on what each tool returns.

**Step 1: Initialize state.**
Create the session with `_new_session(query, wardrobe)`. This holds the query, parsed parameters, tool results, and an `error` field (None until something fails).

**Step 2: Parse the query.**
Extract `description`, `size`, and `max_price` from the natural-language query using regex / string parsing (chosen over an LLM call for reliability and zero latency):
  * `max_price`: regex for a number following "under", "$", or "below"  (e.g., "under $30" → 30.0). If none found → None (no price filter).
  * `size`: regex for a size token after the word "size", or a standalone S/M/L/XL / numeric token (e.g., "size M" → "M"). If none found → None.
  * `description`: the query with the matched price/size phrases stripped out, leaving the descriptive keywords (e.g., "vintage graphic tee").
Store all three in `session["parsed"]`.

**Step 3: Search, then BRANCH on the result.**
Call `search_listings(description, size, max_price)` and store the list in `session["search_results"]`.
  - **Branch A — empty list (`results == []`):** set `session["error"]` to a specific, actionable message naming what failed and what to try (e.g., "No listings matched 'designer ballgown' under $5 in size XXS. Try raising your max price or removing the size filter."). Then `return session` immediately. The loop does NOT call suggest_outfit or create_fit_card, so those fields stay None. THIS IS THE ADAPTIVE BRANCH.
  - **Branch B — non-empty list:** set `session["selected_item"] = search_results[0]` (top-ranked match) and
    continue to Step 4.

**Step 4: Suggest an outfit.**
Call `suggest_outfit(session["selected_item"], session["wardrobe"])` and store the returned string in `session["outfit_suggestion"]`. This tool internally handles the empty-wardrobe case (general advice vs. wardrobe-specific combos), so the loop does not need a separate branch here.

**Step 5: Create the fit card.**
Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])` and store the result in `session["fit_card"]`. If the outfit string were empty, this tool returns an error-message string rather than raising, keeping the loop alive.

**Step 6: Return.**
Return the completed `session`. The caller (app.py / CLI) checks `session["error"]` first: if it is None, all three output fields are populated; if it is set, the interaction ended early at Step 3 and the outfit/fit-card fields are None.

**How the agent knows it's done:**
The loop terminates either (a) early at Step 3 when search returns nothing (error path), or (b) after Step 5 when the fit card is set (success path).There is no open-ended re-planning. The decision point that changes behavior is the emptiness check on `search_results`.


---

## State Management

**How does information from one tool get passed to the next?**

All information for a single user interaction lives in one `session` dict, created by `_new_session(query, wardrobe)` at the start of `run_agent()`. This dict is the single source of truth. Every tool reads its inputs from the session and every result is written back into it, so no value ever has to be re-entered by the user or recomputed.

**What is stored (the session fields):**
* `query` (str): the original user query, set at initialization.
* `parsed` (dict): the extracted `description`, `size`, and `max_price` from the parsing step.
* `search_results` (list[dict]): the full list returned by search_listings.
* `selected_item` (dict | None): the top-ranked listing chosen from search_results — this is the item that flows into the next two tools.
* `wardrobe` (dict): the user's wardrobe, set at initialization and passed into suggest_outfit.
* `outfit_suggestion` (str | None): the string returned by suggest_outfit.
* `fit_card` (str | None): the string returned by create_fit_card.
* `error` (str | None): set only if the interaction ends early; None on success.

**When each field is written:**
| Stage | Field written |
|-------|---------------|
| Init | query, wardrobe (error/results start empty/None) |
| After parse | parsed |
| After search | search_results, then selected_item (or error, if empty) |
| After suggest_outfit | outfit_suggestion |
| After create_fit_card | fit_card |

**How data passes between tools (no re-entry):**
* The item found by search_listings is stored as `session["selected_item"]`, and that exact same dict is passed directly into `suggest_outfit(session["selected_item"], session["wardrobe"])`. The user never re-types the item.
* The string returned by suggest_outfit is stored as `session["outfit_suggestion"]`, and that exact string is passed into `create_fit_card(session["outfit_suggestion"], session["selected_item"])`.
* Because `selected_item` is also reused in create_fit_card, the same listing's title/price/platform stay consistent across the outfit suggestion and the final fit card.

**Lifetime / scope:**
State is per-session (one call to `run_agent`). When the run returns, app.py reads the finished session and maps its fields to the three UI panels. Nothing persists across separate queries. Each new query starts a fresh session.


---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No listings match the query (returns `[]`). E.G., the price ceiling, size filter, and keywords together exclude everything. | he planning loop detects the empty list and stops before calling any other tool. It sets `session["error"]` to a specific message that names the failed query and suggests a concrete fix, e.g.: *"No listings matched 'designer ballgown' under $5 in size XXS. Try raising your max price, removing the size filter, or using broader keywords."* The outfit and fit-card panels stay empty.|

| suggest_outfit | The wardrobe is empty (`wardrobe['items'] == []`). A new user with nothing entered, so no owned pieces to pair with. |  The tool does NOT crash or return an empty string. It detects the empty `items` list and prompts the LLM for **general styling advice** for the new item instead (what categories/colors pair well, what vibe it suits, how to style it from scratch), and returns that as a normal suggestion string so the flow continues to create_fit_card. |

| create_fit_card |  The `outfit` argument is missing, empty, or whitespace-only. E.G., suggest_outfit returned nothing usable. | The tool checks the outfit string before calling the LLM. If it's empty/whitespace, it skips the LLM and returns a descriptive error-message string, e.g.: *"Can't generate a fit card without an outfit suggestion — try styling the item first."* It returns this string rather than raising an exception, so the agent stays alive and can surface the message. |

---

## Architecture

## Architecture

User query + wardrobe choice (app.py / CLI)
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  PLANNING LOOP  (run_agent in agent.py)               │
│                                                                       │
│  Step 1: _new_session(query, wardrobe)  ──► initializes SESSION       │
│                                                                       │
│  Step 2: parse query (regex)                                          │
│          └─► SESSION["parsed"] = {description, size, max_price}       │
│                          │                                            │
│                          ▼                                            │
│  Step 3: search_listings(description, size, max_price)                │
│                          │                                            │
│            ┌─────────────┴──────────────┐                            │
│            │ results == []              │ results == [item, ...]      │
│            ▼                            ▼                             │
│   [ERROR BRANCH]              SESSION["search_results"] = results     │
│   SESSION["error"] =          SESSION["selected_item"] = results[0]   │
│     "No listings matched…              │                             │
│      try raising price /               ▼                             │
│      dropping size"          Step 4: suggest_outfit(selected_item,    │
│            │                                       wardrobe)          │
│            │                            │  (handles empty wardrobe    │
│            │                            │   internally → general tips)│
│            │                            ▼                             │
│            │                 SESSION["outfit_suggestion"] = "..."     │
│            │                            │                             │
│            │                            ▼                             │
│            │                 Step 5: create_fit_card(outfit_           │
│            │                          suggestion, selected_item)      │
│            │                            │  (empty outfit → error      │
│            │                            │   string, no LLM call)      │
│            │                            ▼                             │
│            │                 SESSION["fit_card"] = "..."              │
│            │                            │                             │
│            └────────────► return SESSION ◄──┘                         │
└─────────────────────────────────────────────────────────────────────┘
        │
        ▼
Caller checks SESSION["error"]:
   • None  → populate all 3 panels (listing / outfit / fit card)
   • set   → show error in panel 1, leave panels 2 & 3 empty

           ┌──────────────────────────────────────────┐
           │ SESSION  (single source of truth)         │
           │  query · parsed · search_results ·        │
           │  selected_item · wardrobe ·               │
           │  outfit_suggestion · fit_card · error     │
           │  (read + written by every step above)     │
           └──────────────────────────────────────────┘


---

## AI Tool Plan

**AI tool used:** Claude (Anthropic) for all implementation help, since it handles multi-file Python context and lets me paste full spec sections as prompts.

**Milestone 3 — Individual tool implementations:**

* search_listings: I'll give Claude the **Tool 1 block** from this planning.md (inputs with types, the full list of returned listing fields, and the empty-list failure mode) plus the function's docstring/TODO from tools.py. I'll instruct it to implement the function using `load_listings()` from utils/data_loader.py and to follow the 5-step algorithm (load → filter price/size → score by keyword overlap → drop zero-score → sort descending).
* Expected output: a complete `search_listings` that filters on all three parameters and returns `[]` (never raises) when nothing matches.
* Verification before trusting it: I'll confirm (a) it filters by all three params, (b) size matching is case-insensitive and substring-based so "M" matches "S/M", (c) it returns `[]` rather than raising on no match. Then I'll run my three pytest cases (`test_search_returns_results`, `test_search_empty_results`, `test_search_price_filter`) before moving on.

* suggest_outfit: I'll give Claude the **Tool 2 block** plus the wardrobe schema (the `items` list and each item's fields) and ask it to implement the function using Groq's `llama-3.3-70b-versatile`. I'll explicitly require the empty-wardrobe branch (general styling advice) from my Error Handling table.
* Expected output: a function that returns a non-empty styling string in both the populated and empty-wardrobe cases.
* Verification: I'll test with `get_example_wardrobe()` (expects named pieces in the output) and `get_empty_wardrobe()` (expects general advice, no crash, non-empty string).


* create_fit_card:  I'll give Claude the **Tool 3 block** and the caption style guidelines (casual tone, item name/price/platform mentioned once each, varied output). I'll require the empty-outfit guard from my Error Handling table.
* Expected output: A 2–4 sentence caption string, plus an error-message string when `outfit` is empty.
* Verification: I'll run it 3× on the same input to confirm outputs vary (raising temperature if they're identical), and call it with `outfit=""` to confirm it returns an error string instead of raising.


**Milestone 4 — Planning loop and state management:**

I'll give Claude the **Architecture diagram**, the **Planning Loop section** (Steps 1–6 with the `results == []` branch), and the **State Management section** (the session dict fields), along with the `run_agent()` docstring/TODO from agent.py. I'll ask it to implement `run_agent()` exactly to that flow.

* Expected output: A loop that parses the query, branches on the search result, stores each tool's output in the correct session field, and returns early with an `error` message when search returns `[]`.
* Verification before trusting it: I'll check that the generated code (a) branches on the search result rather than calling all three tools unconditionally, (b) writes to the documented session keys, and (c) does NOT call suggest_outfit when results are empty. Then I'll run `python agent.py` and confirm the happy-path query populates all fields while the "designer ballgown size XXS under $5" query
sets `session["error"]` and leaves `fit_card` as None. I'll also paste the same spec sections to Claude for `handle_query()` in app.py and verify it maps the session dict to the three output panels and shows the error in panel 1 on the error path.

---

**Note on overrides:** Anything Claude generates that diverges from these specs (wrong parameter names, missing failure branch, calling tools out of order) I'll revise by hand to match planning.md before committing. I'll record at least two of these revisions in the README's AI Usage section as required.


## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1: Parse the query**
The planning loop first calls a parsing step that extracts structured filters from the free-text query. Using regex/string parsing it pulls:
* `max_price` → 30.0 (from "under $30")
* `size` → None (no size mentioned)
* `description` → "vintage graphic tee" (the descriptive keywords)
These are stored in `session["parsed"]`.

**Step 2: search_listings**
The loop calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. It loads all listings, drops anything over $30 (e.g., the $38 Levi's lst_001 is excluded), then scores each remaining listing by keyword overlap against the title, description, and style_tags.
Returned (sorted by relevance, best first):
  1. lst_002 "Y2K Baby Tee — Butterfly Print" — $18, depop, excellent condition (matches "vintage" + "graphic tee" tags → score 3)
  2. lst_006 "Graphic Tee — 2003 Tour Bootleg Style" — $24, depop, good (also score 3; ranked second by stable sort order)
The full list is stored in `session["search_results"]`.

**Step 3 — Select the item**
The loop checks that `search_results` is non-empty. It is, so it sets `session["selected_item"] = search_results[0]` — the Y2K Baby Tee ($18). Because results were found, the agent does NOT enter the error branch and proceeds.


**Step 4: suggest_outfit**
The loop calls `suggest_outfit(selected_item=<bootleg tee>, wardrobe=<example wardrobe>)`.
The wardrobe is non-empty (10 items), so the LLM is given the tee plus named wardrobe pieces and asked for specific combinations. It returns something like:
"Pair the Y2K butterfly baby tee with your baggy dark-wash straight-leg jeans and chunky white sneakers for a playful 2000s streetwear look. Layer the cropped black denim jacket over it and add the black crossbody bag to finish."
Stored in `session["outfit_suggestion"]`.

**Step 5: create_fit_card**
The loop calls `create_fit_card(outfit=<suggestion>, new_item=<bootleg tee>)`. The outfit string is non-empty, so the LLM generates a casual, shareable caption that names the item, price, and platform once each:
"Found this y2k butterfly baby tee on depop for $18 and I'm obsessed. styled it with my baggy jeans + chunky sneakers and a cropped denim jacket. Pure 2000's energy. Full fit loading in stories"
Stored in `session["fit_card"]`.


**Final output to user:**
The Gradio UI populates all three panels:
* Top listing found: "Graphic Tee — 2003 Tour Bootleg Style — $24, depop, good condition"
* Outfit idea: the styling suggestion from Step 4
* Your fit card: the shareable caption from Step 5
`session["error"]` remains None throughout, signaling a successful run.