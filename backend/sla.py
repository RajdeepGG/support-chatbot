from datetime import datetime, timedelta

def assign_sla(priority: str):
    now = datetime.utcnow()

    if priority == "HIGH":
        return {
            "first_response_minutes": 5,
            "resolution_hours": 2,
            "first_response_due": now + timedelta(minutes=5),
            "resolution_due": now + timedelta(hours=2)
        }

    if priority == "MEDIUM":
        return {
            "first_response_minutes": 30,
            "resolution_hours": 6,
            "first_response_due": now + timedelta(minutes=30),
            "resolution_due": now + timedelta(hours=6)
        }

    return {
        "first_response_minutes": 120,
        "resolution_hours": 24,
        "first_response_due": now + timedelta(hours=2),
        "resolution_due": now + timedelta(hours=24)
    }
