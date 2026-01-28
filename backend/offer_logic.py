def get_offer_faq_query(offer: dict) -> str:
    if offer["user_status"] == "ONGOING":
        return "offer ongoing reward delay"

    if offer["user_status"] == "COMPLETED" and offer["verification_status"] == "UNDER_VERIFICATION":
        return "offer completed under verification reward delay"

    if offer["user_status"] == "EXPIRED":
        return "offer expired reward"

    return "offer reward issue"
