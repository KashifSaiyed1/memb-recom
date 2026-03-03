# app/cities.py

# Major Indian cities with lat/lng coordinates
# Used to resolve city name → coordinates for Swiggy search

CITY_COORDINATES = {
    # ── Metro Cities ──
    "mumbai": {"lat": "19.0760", "lng": "72.8777", "label": "Mumbai, Maharashtra"},
    "delhi": {"lat": "28.7041", "lng": "77.1025", "label": "Delhi"},
    "new delhi": {"lat": "28.6139", "lng": "77.2090", "label": "New Delhi"},
    "bangalore": {"lat": "12.9716", "lng": "77.5946", "label": "Bangalore, Karnataka"},
    "bengaluru": {"lat": "12.9716", "lng": "77.5946", "label": "Bengaluru, Karnataka"},
    "hyderabad": {"lat": "17.3850", "lng": "78.4867", "label": "Hyderabad, Telangana"},
    "chennai": {"lat": "13.0827", "lng": "80.2707", "label": "Chennai, Tamil Nadu"},
    "kolkata": {"lat": "22.5726", "lng": "88.3639", "label": "Kolkata, West Bengal"},
    "ahmedabad": {"lat": "23.0225", "lng": "72.5714", "label": "Ahmedabad, Gujarat"},
    "pune": {"lat": "18.5204", "lng": "73.8567", "label": "Pune, Maharashtra"},

    # ── Tier 1 Cities ──
    "jaipur": {"lat": "26.9124", "lng": "75.7873", "label": "Jaipur, Rajasthan"},
    "lucknow": {"lat": "26.8467", "lng": "80.9462", "label": "Lucknow, Uttar Pradesh"},
    "chandigarh": {"lat": "30.7333", "lng": "76.7794", "label": "Chandigarh"},
    "indore": {"lat": "22.7196", "lng": "75.8577", "label": "Indore, Madhya Pradesh"},
    "bhopal": {"lat": "23.2599", "lng": "77.4126", "label": "Bhopal, Madhya Pradesh"},
    "nagpur": {"lat": "21.1458", "lng": "79.0882", "label": "Nagpur, Maharashtra"},
    "surat": {"lat": "21.1702", "lng": "72.8311", "label": "Surat, Gujarat"},
    "vadodara": {"lat": "22.3072", "lng": "73.1812", "label": "Vadodara, Gujarat"},
    "baroda": {"lat": "22.3072", "lng": "73.1812", "label": "Vadodara, Gujarat"},
    "rajkot": {"lat": "22.3039", "lng": "70.8022", "label": "Rajkot, Gujarat"},
    "gandhinagar": {"lat": "23.2156", "lng": "72.6369", "label": "Gandhinagar, Gujarat"},
    "kochi": {"lat": "9.9312", "lng": "76.2673", "label": "Kochi, Kerala"},
    "cochin": {"lat": "9.9312", "lng": "76.2673", "label": "Kochi, Kerala"},
    "thiruvananthapuram": {"lat": "8.5241", "lng": "76.9366", "label": "Thiruvananthapuram, Kerala"},
    "trivandrum": {"lat": "8.5241", "lng": "76.9366", "label": "Thiruvananthapuram, Kerala"},
    "coimbatore": {"lat": "11.0168", "lng": "76.9558", "label": "Coimbatore, Tamil Nadu"},
    "visakhapatnam": {"lat": "17.6868", "lng": "83.2185", "label": "Visakhapatnam, Andhra Pradesh"},
    "vizag": {"lat": "17.6868", "lng": "83.2185", "label": "Visakhapatnam, Andhra Pradesh"},
    "vijayawada": {"lat": "16.5062", "lng": "80.6480", "label": "Vijayawada, Andhra Pradesh"},

    # ── Tier 2 Cities ──
    "gurgaon": {"lat": "28.4595", "lng": "77.0266", "label": "Gurgaon, Haryana"},
    "gurugram": {"lat": "28.4595", "lng": "77.0266", "label": "Gurugram, Haryana"},
    "noida": {"lat": "28.5355", "lng": "77.3910", "label": "Noida, Uttar Pradesh"},
    "ghaziabad": {"lat": "28.6692", "lng": "77.4538", "label": "Ghaziabad, Uttar Pradesh"},
    "faridabad": {"lat": "28.4089", "lng": "77.3178", "label": "Faridabad, Haryana"},
    "navi mumbai": {"lat": "19.0330", "lng": "73.0297", "label": "Navi Mumbai, Maharashtra"},
    "thane": {"lat": "19.2183", "lng": "72.9781", "label": "Thane, Maharashtra"},
    "patna": {"lat": "25.6093", "lng": "85.1376", "label": "Patna, Bihar"},
    "ranchi": {"lat": "23.3441", "lng": "85.3096", "label": "Ranchi, Jharkhand"},
    "bhubaneswar": {"lat": "20.2961", "lng": "85.8245", "label": "Bhubaneswar, Odisha"},
    "mysore": {"lat": "12.2958", "lng": "76.6394", "label": "Mysore, Karnataka"},
    "mysuru": {"lat": "12.2958", "lng": "76.6394", "label": "Mysuru, Karnataka"},
    "mangalore": {"lat": "12.9141", "lng": "74.8560", "label": "Mangalore, Karnataka"},
    "dehradun": {"lat": "30.3165", "lng": "78.0322", "label": "Dehradun, Uttarakhand"},
    "amritsar": {"lat": "31.6340", "lng": "74.8723", "label": "Amritsar, Punjab"},
    "ludhiana": {"lat": "30.9010", "lng": "75.8573", "label": "Ludhiana, Punjab"},
    "kanpur": {"lat": "26.4499", "lng": "80.3319", "label": "Kanpur, Uttar Pradesh"},
    "varanasi": {"lat": "25.3176", "lng": "82.9739", "label": "Varanasi, Uttar Pradesh"},
    "agra": {"lat": "27.1767", "lng": "78.0081", "label": "Agra, Uttar Pradesh"},
    "udaipur": {"lat": "24.5854", "lng": "73.7125", "label": "Udaipur, Rajasthan"},
    "jodhpur": {"lat": "26.2389", "lng": "73.0243", "label": "Jodhpur, Rajasthan"},
    "nashik": {"lat": "20.0063", "lng": "73.7895", "label": "Nashik, Maharashtra"},
    "aurangabad": {"lat": "19.8762", "lng": "75.3433", "label": "Aurangabad, Maharashtra"},
    "goa": {"lat": "15.2993", "lng": "74.1240", "label": "Goa"},
    "panaji": {"lat": "15.4909", "lng": "73.8278", "label": "Panaji, Goa"},
    "pondicherry": {"lat": "11.9416", "lng": "79.8083", "label": "Pondicherry"},
    "puducherry": {"lat": "11.9416", "lng": "79.8083", "label": "Puducherry"},
    "guwahati": {"lat": "26.1445", "lng": "91.7362", "label": "Guwahati, Assam"},
    "siliguri": {"lat": "26.7271", "lng": "88.3953", "label": "Siliguri, West Bengal"},
    "raipur": {"lat": "21.2514", "lng": "81.6296", "label": "Raipur, Chhattisgarh"},
}


def get_city_coordinates(city: str) -> dict | None:
    """
    Look up lat/lng for a city name (case-insensitive).
    Returns {"lat": "...", "lng": "...", "label": "..."} or None.
    """
    return CITY_COORDINATES.get(city.strip().lower())


def get_all_cities() -> list[str]:
    """Return a sorted list of all supported city names."""
    # Deduplicate by label (e.g., bangalore/bengaluru → one entry)
    seen = set()
    cities = []
    for key, val in CITY_COORDINATES.items():
        label = val["label"]
        if label not in seen:
            seen.add(label)
            cities.append(label)
    return sorted(cities)
