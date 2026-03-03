# app/inference.py

import re

# ── Cuisine keyword sets ──

INDIAN_CUISINES = {
    "north indian", "south indian", "mughlai", "biryani", "punjabi",
    "rajasthani", "gujarati", "hyderabadi", "kerala", "bengali",
    "lucknowi", "awadhi", "chettinad", "andhra", "goan",
}
CHINESE_CUISINES = {
    "chinese", "asian", "thai", "tibetan", "japanese", "sushi",
    "korean", "vietnamese", "pan-asian",
}
ITALIAN_CUISINES = {"italian", "pizzas", "pastas", "continental", "european"}
CAFE_CUISINES = {"cafe", "beverages", "coffee", "tea", "bakery", "snacks"}
FAST_FOOD_CUISINES = {"burgers", "fast food", "american", "wraps", "rolls", "sandwiches"}
DESSERT_CUISINES = {"desserts", "ice cream", "bakery", "sweets", "cakes"}
STREET_CUISINES = {"street food", "chaat", "pav bhaji", "vada pav"}

# ── Name-based keyword sets ──

CAFE_KEYWORDS = ["cafe", "coffee", "chai", "tea", "brew", "roast", "espresso", "latte"]
BAKERY_KEYWORDS = ["bakery", "cake", "bake", "patisserie", "sweet"]
QSR_KEYWORDS = ["pizza", "burger", "wrap", "roll", "fries", "fried", "99", "story", "domino"]
CLOUD_KEYWORDS = ["kitchen", "cloud", "box", "bowl", "meals", "home"]
DHABA_KEYWORDS = ["dhaba", "bhojnalaya", "thali"]

# ── Industry gross margin benchmarks (India F&B) ──

MARGIN_MAP = {
    "QSR": 65,
    "Fast Casual": 62,
    "Cafe": 68,
    "Casual Dining": 58,
    "Fine Dining": 62,
    "Bakery & Desserts": 70,
    "Cloud Kitchen": 72,
    "Dhaba/Street Food": 60,
}

# ── Visit frequency benchmarks (per month for a regular customer) ──

FREQUENCY_MAP = {
    "QSR": 5.0,
    "Fast Casual": 3.5,
    "Cafe": 4.0,
    "Casual Dining": 2.0,
    "Fine Dining": 0.75,
    "Bakery & Desserts": 3.0,
    "Cloud Kitchen": 3.5,
    "Dhaba/Street Food": 5.0,
}


# ══════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════

def infer_restaurant_attributes(restaurant_info: dict, menu_items: list[dict]) -> dict:
    """
    Main entry point: takes restaurant metadata + parsed menu items,
    returns a dict with all 6 inferred fields.
    """
    print("\n🧠 Running rule-based inference...")

    cuisines = restaurant_info.get("cuisines", [])
    cost_str = restaurant_info.get("costForTwoMessage", "")
    name = restaurant_info.get("name", "")
    veg_only = restaurant_info.get("veg", False)

    cost_for_two = _extract_cost_for_two(cost_str)

    # Average item price from menu
    prices = [item["Price"] for item in menu_items if item.get("Price") and item["Price"] > 0]
    avg_item_price = sum(prices) / len(prices) if prices else 0

    # Run classifiers
    cuisine_type = classify_cuisine_type(cuisines)
    price_range = classify_price_range(cost_for_two)
    business_category = classify_business_category(cuisines, cost_for_two, name, avg_item_price, veg_only)
    visit_frequency = estimate_visit_frequency(business_category, cost_for_two)
    gross_margin = estimate_gross_margin(business_category, cuisine_type)
    ambiance = estimate_ambiance(business_category, cost_for_two, cuisines)

    result = {
        "business_category": business_category,
        "cuisine_type": cuisine_type,
        "price_range": price_range,
        "estimated_visit_frequency_per_month": visit_frequency,
        "gross_margin_percent": gross_margin,
        "ambiance": ambiance,
    }

    print(f"   📊 Avg item price: ₹{avg_item_price:.0f}")
    print(f"   📊 Cost for two: ₹{cost_for_two}")
    print(f"   📊 Cuisines: {', '.join(cuisines)}")
    print(f"   📊 Veg only: {veg_only}")
    print("   ✅ Inference complete!")

    return result


# ══════════════════════════════════════════════
#  CLASSIFIERS
# ══════════════════════════════════════════════

def classify_cuisine_type(cuisines: list[str]) -> str:
    """Classify into a primary cuisine type based on Swiggy cuisine tags."""
    if not cuisines:
        return "Multi-Cuisine"

    c_set = {c.lower() for c in cuisines}

    matches = [
        (len(c_set & INDIAN_CUISINES), "Indian"),
        (len(c_set & CHINESE_CUISINES), "Asian"),
        (len(c_set & ITALIAN_CUISINES), "Italian-Continental"),
        (len(c_set & CAFE_CUISINES), "Cafe"),
        (len(c_set & FAST_FOOD_CUISINES), "Fast Food"),
        (len(c_set & DESSERT_CUISINES), "Bakery & Desserts"),
        (len(c_set & STREET_CUISINES), "Street Food"),
    ]
    matches.sort(key=lambda x: x[0], reverse=True)

    if matches[0][0] == 0:
        return "Multi-Cuisine"

    # Combine top two if close
    if len(matches) > 1 and matches[1][0] > 0 and matches[0][0] - matches[1][0] <= 1:
        return f"{matches[0][1]} / {matches[1][1]}"

    return matches[0][1]


def classify_price_range(cost_for_two: int) -> str:
    if cost_for_two <= 0:
        return "Unknown"
    elif cost_for_two < 300:
        return "Budget (below ₹300 for two)"
    elif cost_for_two < 800:
        return "Mid-Range (₹300-₹800 for two)"
    elif cost_for_two < 1500:
        return "Premium (₹800-₹1500 for two)"
    else:
        return "Luxury (above ₹1500 for two)"


def classify_business_category(
    cuisines: list[str],
    cost_for_two: int,
    name: str,
    avg_item_price: float,
    veg_only: bool,
) -> str:
    """Classify the business type using name keywords, cuisines, and price signals."""
    c_lower = [c.lower() for c in cuisines] if cuisines else []
    name_lower = name.lower()

    # Keyword-first checks
    if any(k in name_lower for k in CAFE_KEYWORDS) or "cafe" in c_lower:
        return "Cafe"
    if any(k in name_lower for k in BAKERY_KEYWORDS) or set(c_lower) <= {"bakery", "desserts", "cakes", "sweets"}:
        return "Bakery & Desserts"
    if any(k in name_lower for k in DHABA_KEYWORDS):
        return "Dhaba/Street Food"

    # Price-based
    if cost_for_two < 300:
        return "QSR" if (any(k in name_lower for k in QSR_KEYWORDS) or avg_item_price < 150) else "Fast Casual"
    elif cost_for_two < 500:
        return "QSR" if (any(k in name_lower for k in QSR_KEYWORDS) or avg_item_price < 200) else "Fast Casual"
    elif cost_for_two < 800:
        return "Fast Casual" if avg_item_price < 300 else "Casual Dining"
    elif cost_for_two < 1500:
        return "Casual Dining"
    else:
        return "Fine Dining"


# ══════════════════════════════════════════════
#  ESTIMATORS
# ══════════════════════════════════════════════

def estimate_visit_frequency(business_category: str, cost_for_two: int) -> float:
    """Estimated monthly visits for a regular customer."""
    base = FREQUENCY_MAP.get(business_category, 2.0)

    if cost_for_two < 300:
        base *= 1.2
    elif cost_for_two > 1000:
        base *= 0.7

    return round(base, 1)


def estimate_gross_margin(business_category: str, cuisine_type: str) -> int:
    """Estimated gross margin % based on category + cuisine adjustments."""
    base = MARGIN_MAP.get(business_category, 60)

    if "Italian" in cuisine_type or "Pizza" in cuisine_type:
        base += 3
    elif "Indian" in cuisine_type:
        base -= 2
    elif "Cafe" in cuisine_type:
        base += 5
    elif "Bakery" in cuisine_type or "Desserts" in cuisine_type:
        base += 3

    return min(max(base, 40), 80)


def estimate_ambiance(business_category: str, cost_for_two: int, cuisines: list[str]) -> str:
    """Estimated ambiance style."""
    c_lower = [c.lower() for c in cuisines] if cuisines else []

    ambiance_map = {
        "Fine Dining": "Premium & Upscale",
        "QSR": "Quick Service",
        "Dhaba/Street Food": "Traditional & Heritage",
        "Bakery & Desserts": "Cozy & Intimate",
        "Cloud Kitchen": "Quick Service",
        "Fast Casual": "Casual & Lively",
    }

    if business_category in ambiance_map:
        return ambiance_map[business_category]

    if business_category == "Cafe":
        return "Trendy & Modern" if cost_for_two > 600 else "Cozy & Intimate"

    if business_category == "Casual Dining":
        if cost_for_two > 800:
            return "Trendy & Modern"
        if any(c in c_lower for c in ["italian", "continental", "european"]):
            return "Trendy & Modern"
        if any(c in c_lower for c in ["north indian", "mughlai", "punjabi"]):
            return "Family-Friendly"
        return "Casual & Lively"

    return "Casual & Lively"


# ── Private helpers ──

def _extract_cost_for_two(cost_str: str) -> int:
    """Parse '₹600 FOR TWO' → 600"""
    if not cost_str:
        return 0
    match = re.search(r"[\d,]+", cost_str.replace(",", ""))
    return int(match.group()) if match else 0
