# Offer Context (Frontend → Backend) Testing

## Request Shape

Frontend should call `/v1/chat-stream` and include an `offer_context` object in the request JSON:

```json
{
  "message": "I did not get my reward",
  "offer_id": "703596",
  "offer_context": { "offer": {}, "postback_reward": [], "retention_reward": null, "shareable_reward": null }
}
```

`offer_id` is optional if `offer_context.offer.oid` is present.

## Local Testing (curl)

### 1) Save payload to a file

Create a file `payload.json`:

```json
{
  "message": "I did not get my reward",
  "offer_context": {
    "offer": {
      "oid": "703596",
      "tags": ["MULTI_REWARD", "GAMING"],
      "status": {
        "user_status": "ONGOING",
        "offer_status": "ACTIVE",
        "progress": 0.1,
        "expires_in": 172790,
        "expires_at": 1776325275,
        "started_at": 1776152475
      }
    },
    "postback_reward": [
      {
        "reward_id": 1440378,
        "label": "TEST",
        "status": "ONGOING",
        "payout": { "amount": 372.42, "currency": "sikka" },
        "started_at": 1776152475
      }
    ],
    "retention_reward": {
      "reward_id": 1440379,
      "label": "Retention",
      "status": "LOCKED",
      "payout": { "amount": 22.34, "currency": "sikka" },
      "retention_status": [
        { "day": 1, "status": "LOCKED", "payout": { "amount": 7.44, "currency": "sikka" } },
        { "day": 2, "status": "LOCKED", "payout": { "amount": 7.44, "currency": "sikka" } },
        { "day": 3, "status": "LOCKED", "payout": { "amount": 7.44, "currency": "sikka" } }
      ]
    },
    "shareable_reward": null
  }
}
```

### 2) Call the streaming endpoint

```bash
curl -N -X POST http://127.0.0.1:8080/v1/chat-stream \
  -H 'Content-Type: application/json' \
  --data-binary @payload.json
```

### 3) What to expect

- You will receive NDJSON lines:
  - Many lines like: `{"delta":"..."}`
  - Then either:
    - `{"event":"end","action":{"type":"escalate_to_agent","payload":{}}}` (escalation)
    - or `{"event":"csat",...}` then `{"event":"end"}` (normal completion)

## WebSocket Testing

Send the same fields in your websocket message payload:

```json
{
  "message": "How much time for reward?",
  "offer_context": { ... }
}
```

