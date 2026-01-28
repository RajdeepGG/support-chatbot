def determine_priority(user_message: str) -> str:
    message = user_message.lower()

    high_keywords = [
        "payment",  "money", "charged",
        "deducted", "failed transaction"
    ]

    medium_keywords = [
        "login", "error", "crash",
        "not working", "issue", "bug","refund"
    ]

    for word in high_keywords:
        if word in message:
            return "HIGH"

    for word in medium_keywords:
        if word in message:
            return "MEDIUM"

    return "LOW"
