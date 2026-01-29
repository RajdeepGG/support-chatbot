MOCK_OFFERS_DB = {
    925599: {
        "offer_id": 925599,
        "title": "Woodblock Puzzle Game",
        "user_status": "COMPLETED",
        "verification_status": "UNDER_VERIFICATION",
        "estimated_time_minutes": 8,
        "difficulty": "easy"
    },
    111222: {
        "offer_id": 111222,
        "title": "Sea Block",
        "user_status": "ONGOING",
        "verification_status": None,
        "estimated_time_minutes": 5,
        "difficulty": "easy"
    },
    333444: {
        "offer_id": 333444,
        "title": "Carrom Pool: Disc Game ",
        "user_status": "EXPIRED",
        "verification_status": None,
        "estimated_time_minutes": 15,
        "difficulty": "medium"
    }
}

def get_offer_details(offer_id):
    try:
        oid = int(offer_id)
        return MOCK_OFFERS_DB.get(oid)
    except (ValueError, TypeError):
        return None

def get_offer_status(offer_id: int):
    return get_offer_details(offer_id)


def get_offer_by_title(title: str):
    for offer in MOCK_OFFERS_DB.values():
        if offer["title"].lower() == title.lower():
            return offer
    return None

def resolve_offer_id_by_title(title: str):
    for offer_id, offer in MOCK_OFFERS_DB.items():
        if offer["title"].lower() == title.lower():
            return offer_id
    return None

def get_recommended_offers(exclude_offer_id=None, limit=2):
    difficulty_weight = {"easy": 0, "medium": 1, "hard": 2}
    offers = []
    for offer in MOCK_OFFERS_DB.values():
        if exclude_offer_id and offer["offer_id"] == exclude_offer_id:
            continue
        if offer.get("user_status") == "EXPIRED":
            continue
        time_min = offer.get("estimated_time_minutes", 999)
        diff_w = difficulty_weight.get(offer.get("difficulty", "medium"), 1)
        score = time_min + diff_w * 10
        offers.append((score, offer))
    offers.sort(key=lambda x: x[0])
    return [o for _, o in offers[:limit]]
