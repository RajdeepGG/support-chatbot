from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
import re
from typing import Any, Dict, List, Optional, Tuple


def _safe_get(d: Any, *keys: str, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur.get(k)
    return cur


def _fmt_ts(ts: Optional[int]) -> str:
    if not ts:
        return ""
    try:
        t = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%I:%M %p")
        return t.lstrip("0")
    except Exception:
        return ""


def _fmt_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return ""
    try:
        s = int(seconds)
    except Exception:
        return ""
    if s < 0:
        s = 0
    mins = s // 60
    hrs = mins // 60
    days = hrs // 24
    if days > 0:
        rem_hrs = hrs % 24
        return f"{days}d {rem_hrs}h"
    if hrs > 0:
        rem_mins = mins % 60
        return f"{hrs}h {rem_mins}m"
    return f"{mins}m"


def _is_completed(status: str) -> bool:
    s = (status or "").strip().upper()
    return s in {"COMPLETED", "CREDITED", "PAID", "REWARDED"}


def _parse_time_claim_seconds(user_msg: str) -> Optional[int]:
    s = (user_msg or "").lower()
    vals: List[int] = []
    for m in re.finditer(r"\b(\d+)\s*(hours?|hrs?)\b", s):
        try:
            vals.append(int(m.group(1)) * 3600)
        except Exception:
            pass
    for m in re.finditer(r"\b(\d+)\s*(days?)\b", s):
        try:
            vals.append(int(m.group(1)) * 86400)
        except Exception:
            pass
    if "72 hour" in s or "72hours" in s:
        vals.append(72 * 3600)
    if "48 hour" in s or "48hours" in s:
        vals.append(48 * 3600)
    if not vals:
        return None
    return max(vals)


@dataclass
class RewardStatus:
    kind: str
    label: str
    status: str
    amount: Optional[float] = None
    currency: str = ""
    started_at: Optional[int] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class OfferSummary:
    oid: str
    title: str
    is_multi_reward: bool
    user_status: str
    offer_status: str
    progress: Optional[float]
    started_at: Optional[int]
    expires_in: Optional[int]
    expires_at: Optional[int]
    rewards: List[RewardStatus]

    def pending_rewards(self) -> List[RewardStatus]:
        return [r for r in self.rewards if not _is_completed(r.status)]

    def completed_rewards(self) -> List[RewardStatus]:
        return [r for r in self.rewards if _is_completed(r.status)]


def summarize_offer_context(offer_context: Dict[str, Any]) -> Optional[OfferSummary]:
    if not isinstance(offer_context, dict):
        return None
    offer = offer_context.get("offer") or {}
    if not isinstance(offer, dict):
        return None
    oid = str(offer.get("oid") or "")
    title = str(offer.get("title") or "")
    tags = offer.get("tags") or []
    tagset = {str(t).strip().upper() for t in tags if t}
    is_multi = "MULTI_REWARD" in tagset

    status = offer.get("status") or {}
    user_status = str(status.get("user_status") or offer.get("user_status") or "").upper()
    offer_status = str(status.get("offer_status") or offer.get("offer_status") or "").upper()
    progress = status.get("progress")
    started_at = status.get("started_at")
    expires_in = status.get("expires_in")
    expires_at = status.get("expires_at")

    rewards: List[RewardStatus] = []
    postbacks = offer_context.get("postback_reward") or []
    if isinstance(postbacks, list):
        for r in postbacks:
            if not isinstance(r, dict):
                continue
            payout = r.get("payout") or {}
            rewards.append(
                RewardStatus(
                    kind="postback",
                    label=str(r.get("label") or f"reward_{r.get('reward_id') or ''}").strip(),
                    status=str(r.get("status") or "").upper(),
                    amount=(payout.get("amount") if isinstance(payout, dict) else None),
                    currency=str(_safe_get(payout, "currency", default="") or ""),
                    started_at=r.get("started_at"),
                    details={"reward_id": r.get("reward_id")},
                )
            )

    retention = offer_context.get("retention_reward")
    if isinstance(retention, dict):
        payout = retention.get("payout") or {}
        rewards.append(
            RewardStatus(
                kind="retention",
                label=str(retention.get("label") or f"retention_{retention.get('reward_id') or ''}").strip(),
                status=str(retention.get("status") or "").upper(),
                amount=(payout.get("amount") if isinstance(payout, dict) else None),
                currency=str(_safe_get(payout, "currency", default="") or ""),
                started_at=retention.get("started_at"),
                details={"retention_status": retention.get("retention_status") or []},
            )
        )

    return OfferSummary(
        oid=oid,
        title=title,
        is_multi_reward=is_multi,
        user_status=user_status,
        offer_status=offer_status,
        progress=progress if isinstance(progress, (int, float)) else None,
        started_at=started_at if isinstance(started_at, int) else None,
        expires_in=expires_in if isinstance(expires_in, int) else None,
        expires_at=expires_at if isinstance(expires_at, int) else None,
        rewards=rewards,
    )


def offer_context_prompt(summary: OfferSummary) -> str:
    bits = []
    if summary.oid:
        bits.append(f"Offer ID: {summary.oid}")
    if summary.title:
        bits.append(f"Offer title: {summary.title}")
    bits.append(f"Multi-reward: {'yes' if summary.is_multi_reward else 'no'}")
    if summary.user_status:
        bits.append(f"User status: {summary.user_status}")
    if summary.offer_status:
        bits.append(f"Offer status: {summary.offer_status}")
    if summary.progress is not None:
        bits.append(f"Progress: {round(summary.progress * 100, 1)}%")
    st = _fmt_ts(summary.started_at)
    if st:
        bits.append(f"Started at: {st}")
    ex = _fmt_duration(summary.expires_in)
    if ex:
        bits.append(f"Expires in: {ex}")

    if summary.rewards:
        for r in summary.rewards[:6]:
            p = ""
            if r.amount is not None and r.currency:
                p = f" ({r.amount} {r.currency})"
            bits.append(f"Reward: {r.label} - {r.status}{p}")
    return "\n".join(bits).strip()


def classify_offer_intent(user_msg: str) -> str:
    s = (user_msg or "").lower()
    if detect_topic(s) in {"offer_status", "offer_reward_crediting"}:
        if any(w in s for w in ["status", "ongoing", "completed", "expired", "active", "inactive", "progress", "started", "start time", "expires", "expiry"]):
            return "status"
        return "reward"
    if detect_topic(s) in {"support_contact", "ticket"}:
        return "ticket"
    return "unknown"


def detect_topic(user_msg: str) -> str:
    s = (user_msg or "").lower()
    if any(k in s for k in ["gift card", "giftcard", "xoxoday", "redemption", "redeemed", "merchant", "redeem a gift"]):
        return "gift_card"
    if any(k in s for k in ["referral", "refer", "invite", "referral code", "bonus", "friend"]):
        return "referral"
    payout_keys = [
        "upi", "bank", "withdraw", "withdrawal", "payout", "transfer", "money not transferred", "redeem coins",
        "payout processing", "processing payout", "payout failed", "failed payout", "transfer failed", "payment pending"
    ]
    if any(k in s for k in payout_keys):
        return "payout"
    if any(
        k in s
        for k in [
            "crash",
            "crashed",
            "crashing",
            "crach",
            "not loading",
            "freeze",
            "freezing",
            "stuck",
            "glitch",
            "keeps closing",
            "closing automatically",
            "update the app",
            "update app",
        ]
    ):
        return "app_issue"
    if any(k in s for k in ["survey", "survey options"]):
        return "survey"
    if any(k in s for k in ["suspicious environment", "developer option", "developer options", "developer mode", "clone app", "cloned app"]):
        return "device_integrity"
    if any(k in s for k in ["account hold", "on hold", "blocked", "vpn", "policy violation", "proxy"]):
        return "account_hold"
    if any(k in s for k in ["customer care", "support number", "phone number", "timing", "timings", "contact support", "reach support", "raise a ticket", "support ticket"]):
        return "support_contact"
    if any(k in s for k in ["refund", "in-app purchase", "transaction"]):
        return "refund"
    if any(k in s for k in ["expired", "ongoing", "completed", "offer status", "offer is", "progress", "started", "start time", "expires", "expiry"]):
        return "offer_status"
    if any(
        k in s
        for k in [
            "under verification",
            "pending",
            "verification",
            "reward not",
            "reward not credited",
            "reward not received",
            "not credited",
            "not received",
            "not get",
            "did not get",
            "didn't get",
            "not getting",
            "points not credited",
            "coins not credited",
            "reward pending",
            "rewards pending",
        ]
    ):
        return "offer_reward_crediting"
    if re.search(r"\b(\d+)\s*(hours?|hrs?|days?)\b", s) and any(k in s for k in ["already", "more than", "over", "exceed", "exceeded", "since"]):
        return "offer_reward_crediting"
    return "unknown"


def offer_aware_response(summary: OfferSummary, user_msg: str) -> Optional[str]:
    topic = detect_topic(user_msg)
    if topic not in {"offer_status", "offer_reward_crediting"}:
        return None
    intent = classify_offer_intent(user_msg)
    now_ts = int(time.time())
    elapsed_s = None
    if summary.started_at:
        try:
            elapsed_s = max(0, now_ts - int(summary.started_at))
        except Exception:
            elapsed_s = None
    time_claim_s = _parse_time_claim_seconds(user_msg)
    verify_min_s = 48 * 3600
    verify_max_s = 72 * 3600

    def _reward_elapsed(r: RewardStatus) -> Optional[int]:
        if r.started_at is None:
            return None
        try:
            return max(0, now_ts - int(r.started_at))
        except Exception:
            return None

    def _pending_postback() -> List[RewardStatus]:
        return [r for r in summary.rewards if r.kind == "postback" and not _is_completed(r.status)]

    if summary.offer_status and summary.offer_status != "ACTIVE":
        return "This offer is not active right now. Please check the offer status in the app and raise a ticket from the app if you need help."

    if summary.user_status == "EXPIRED":
        ex = _fmt_ts(summary.expires_at)
        when = f" (expired at {ex})" if ex else ""
        return "Rewards cannot be credited once an offer expires" + when + ". Please try another active offer or raise a ticket from the app if you believe this is incorrect."

    if topic == "offer_reward_crediting":
        pending_postbacks = _pending_postback()

        if summary.user_status == "ONGOING" and pending_postbacks:
            lines = ["Your offer is ongoing. Please complete the remaining steps to receive rewards."]
            if summary.is_multi_reward:
                lines.append("- This is a multi-reward offer. Coins are credited per reward after each step is completed and verified.")
            for r in pending_postbacks[:4]:
                t = _reward_elapsed(r)
                ttxt = f" (started { _fmt_duration(t) } ago)" if t is not None else ""
                lines.append(f"- Pending reward: {r.label} ({r.status}){ttxt}")
            retention = next((r for r in summary.rewards if r.kind == "retention"), None)
            if retention and retention.status == "LOCKED":
                lines.append("- Retention rewards unlock day-wise. Complete the daily steps as they unlock.")
            lines.append("- Once you complete a reward step, verification typically takes 48–72 hours.")
            return "\n".join(lines).strip()

        if summary.user_status == "COMPLETED":
            lines = ["Your offer is marked completed."]
            if elapsed_s is not None:
                lines.append(f"- Time since offer started: {_fmt_duration(elapsed_s)} (started at {_fmt_ts(summary.started_at)})")
            if elapsed_s is not None and elapsed_s >= verify_max_s:
                lines.append("- It has exceeded 72 hours. Please raise a ticket from the app with screenshots.")
            else:
                lines.append("- Rewards are typically credited within 48–72 hours after completion.")
                lines.append("- If it exceeds 72 hours, raise a ticket from the app with screenshots.")
            return "\n".join(lines).strip()

    if topic == "offer_reward_crediting" and time_claim_s and elapsed_s is not None:
        started = _fmt_ts(summary.started_at)
        elapsed = _fmt_duration(elapsed_s)
        timing_line = f"- Time since offer started: {elapsed}" + (f" (started at {started})" if started else "")

        if summary.is_multi_reward and summary.pending_rewards():
            lines = [
                "This is a multi-reward offer. Coins are credited for each reward after you complete its steps.",
                timing_line,
                "- Pending/locked rewards must be completed/unlocked before coins can be credited.",
            ]
            if elapsed_s >= verify_max_s:
                lines.append("- If you have completed the required steps and it has exceeded 72 hours, raise a ticket from the app with screenshots.")
            elif elapsed_s >= verify_min_s:
                lines.append("- Verification can take up to 72 hours after completing each reward.")
            else:
                lines.append("- Verification usually takes 48–72 hours after completing each reward.")
            return "\n".join(lines).strip()

        if elapsed_s >= verify_max_s:
            return (
                "It has exceeded 72 hours.\n"
                f"{timing_line}\n"
                "- If you have completed the required steps and the reward is still not credited, raise a ticket from the app with screenshots."
            )
        if elapsed_s >= verify_min_s:
            return (
                "It may still be under verification.\n"
                f"{timing_line}\n"
                "- Verification can take up to 72 hours after completion. If it exceeds 72 hours, raise a ticket from the app."
            )
        return (
            "It may still be under verification.\n"
            f"{timing_line}\n"
            "- Verification usually takes 48–72 hours after completion. If it exceeds 72 hours, raise a ticket from the app."
        )

    if summary.is_multi_reward and intent in {"reward", "status"}:
        pending = summary.pending_rewards()
        completed = summary.completed_rewards()
        lines = ["This is a multi-reward offer. Coins are credited for each reward after you complete its steps."]
        if completed:
            lines.append("Completed rewards:")
            for r in completed[:4]:
                lines.append(f"- {r.label}: {r.status}")
        if pending:
            lines.append("Pending/locked rewards:")
            for r in pending[:6]:
                lines.append(f"- {r.label}: {r.status}")
        retention = next((r for r in summary.rewards if r.kind == "retention"), None)
        if retention and retention.details:
            rs = retention.details.get("retention_status")
            if isinstance(rs, list) and any(isinstance(x, dict) and str(x.get("status") or "").upper() == "LOCKED" for x in rs):
                lines.append("Retention rewards unlock day-wise. Complete Day 1, Day 2, and Day 3 steps as they unlock.")
        return "\n".join(lines).strip()

    if summary.user_status == "COMPLETED" and intent == "reward":
        return (
            "Your offer is completed but the reward is not credited.\n"
            "- Advertisers typically verify completion within 48–72 hours.\n"
            "- Keep the app/game installed and active during this window.\n"
            "- If it exceeds 72 hours, raise a ticket from the app with screenshots."
        )

    if summary.user_status == "ONGOING" and intent in {"status", "reward"}:
        lines = ["Your offer is ongoing."]
        if summary.progress is not None:
            lines.append(f"- Progress: {round(summary.progress * 100, 1)}%")
        st = _fmt_ts(summary.started_at)
        if st:
            lines.append(f"- Started at: {st}")
        ex = _fmt_duration(summary.expires_in)
        if ex:
            lines.append(f"- Expires in: {ex}")
        if summary.is_multi_reward and summary.pending_rewards():
            lines.append("- Complete all pending rewards to receive coins for those rewards.")
        return "\n".join(lines).strip()

    return None
