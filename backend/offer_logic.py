def get_offer_faq_query(offer: dict) -> str:
    """
    Returns a search query tuned to the specific status of the offer.
    This helps the RAG system find the most relevant FAQ entry.
    """
    status = offer.get("user_status")
    verification = offer.get("verification_status")

    if status == "ONGOING":
        return "What is an Ongoing Offer?"

    if status == "COMPLETED":
        if verification == "UNDER_VERIFICATION":
            return "Why is my offer status under verification?"
        # If verified, they might be asking about money/wallet
        return "When will the Rewards be added to my wallet?"

    if status == "EXPIRED":
        return "Why offer status show as expired?"

    # Default fallback
    return "I did not get my reward"
