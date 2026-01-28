MOCK_OFFERS_DB = {
    925599: {
        "offer_id": 925599,
        "title": "Netclan Explorer",
        "user_status": "COMPLETED",
        "verification_status": "UNDER_VERIFICATION"
    },
    111222: {
        "offer_id": 111222,
        "title": "Cool Gaming App",
        "user_status": "ONGOING",
        "verification_status": None
    },
    333444: {
        "offer_id": 333444,
        "title": "Shopping Cashback",
        "user_status": "EXPIRED",
        "verification_status": None
    }
}

def get_offer_status(offer_id: int):
    return MOCK_OFFERS_DB.get(offer_id)


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


