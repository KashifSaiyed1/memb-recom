# app/extractor.py


def extract_restaurant_info(menu_json: dict) -> dict:
    """
    Extract restaurant-level metadata (name, cuisines, rating, etc.)
    from the Swiggy menu API response.
    """
    info = {}
    cards = menu_json.get("data", {}).get("cards", [])

    for card in cards:
        inner = card.get("card", {}).get("card", {})
        rest_info = inner.get("info", {})
        if rest_info.get("name"):
            info = {
                "name": rest_info.get("name", ""),
                "cuisines": rest_info.get("cuisines", []),
                "costForTwoMessage": rest_info.get("costForTwoMessage", ""),
                "avgRating": rest_info.get("avgRating", ""),
                "totalRatingsString": rest_info.get("totalRatingsString", ""),
                "areaName": rest_info.get("areaName", ""),
                "city": rest_info.get("city", ""),
                "locality": rest_info.get("locality", ""),
                "veg": rest_info.get("veg", False),
                "sla": rest_info.get("sla", {}),
                "feeDetails": rest_info.get("feeDetails", {}),
            }
            break

    return info
