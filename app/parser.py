# app/parser.py


def parse_menu(menu_json: dict) -> list[dict]:
    """
    Parse individual menu items from the Swiggy menu API response.
    Handles regular categories, nested subcategories, and groupedCard structures.

    Returns a list of dicts, each representing one menu item.
    """
    print("\n📋 Parsing menu...")
    menu_items: list[dict] = []

    data = menu_json.get("data", {})
    cards = data.get("cards", [])

    # Swiggy wraps menu inside groupedCard → cardGroupMap → REGULAR → cards
    grouped_card = _find_grouped_card(cards)

    if grouped_card:
        group_cards = grouped_card.get("cardGroupMap", {})
        regular = group_cards.get("REGULAR", {})
        if regular:
            menu_cards = regular.get("cards", [])
            for card in menu_cards:
                inner = card.get("card", {}).get("card", {})
                card_type = inner.get("@type", "")
                _process_card(inner, card_type, menu_items)
    else:
        # Fallback: iterate top-level cards
        for card in cards:
            inner = card.get("card", {}).get("card", {})
            card_type = inner.get("@type", "")
            _process_card(inner, card_type, menu_items)

    # Last resort: recursive deep search
    if not menu_items:
        print("🔍 Deep searching for menu items...")
        _find_items_recursive(menu_json, menu_items)

    print(f"✅ Total Items: {len(menu_items)}")
    return menu_items


# ── Internal helpers ──────────────────────────


def _find_grouped_card(cards: list) -> dict | None:
    """Locate the groupedCard container within the API response cards."""
    for card in cards:
        if "groupedCard" in card:
            return card["groupedCard"]
        inner = card.get("card", {}).get("card", {})
        if "groupedCard" in inner:
            return inner["groupedCard"]
    return None


def _process_card(inner: dict, card_type: str, menu_items: list):
    """Route a card to the right extraction logic based on its @type."""
    if "ItemCategory" in card_type:
        category = inner.get("title", "")
        for item in inner.get("itemCards", []):
            _extract_item(item, category, menu_items)

    elif "NestedItemCategory" in card_type:
        parent = inner.get("title", "")
        for sub in inner.get("categories", []):
            sub_cat = sub.get("title", "")
            for item in sub.get("itemCards", []):
                _extract_item(item, f"{parent} > {sub_cat}", menu_items)


def _extract_item(item: dict, category: str, menu_items: list):
    """Extract a single menu item's details."""
    info = item.get("card", {}).get("info", {})
    if not info:
        info = item.get("info", item)

    name = info.get("name")
    if not name:
        return

    price = info.get("price") or info.get("defaultPrice") or info.get("finalPrice")
    description = info.get("description", "")

    # Veg/Non-Veg classification
    is_veg = info.get("isVeg")
    veg_label = ""
    if is_veg == 1:
        veg_label = "Veg"
    elif is_veg == 0 or info.get("itemAttribute", {}).get("vegClassifier") == "NONVEG":
        veg_label = "Non-Veg"

    if price:
        price = price / 100

    menu_items.append({
        "Category": category,
        "Item Name": name,
        "Price": price,
        "Description": description,
        "Veg/Non-Veg": veg_label,
    })


def _find_items_recursive(obj, menu_items: list, category: str = "Unknown", depth: int = 0):
    """Recursively walk the entire JSON tree looking for menu item dicts."""
    if depth > 15:
        return

    if isinstance(obj, dict):
        if "name" in obj and ("price" in obj or "defaultPrice" in obj):
            _extract_item({"info": obj}, category, menu_items)
            return

        if obj.get("title") and ("itemCards" in obj or "categories" in obj):
            category = obj.get("title", category)

        for value in obj.values():
            _find_items_recursive(value, menu_items, category, depth + 1)

    elif isinstance(obj, list):
        for item in obj:
            _find_items_recursive(item, menu_items, category, depth + 1)
