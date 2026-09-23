"""
Agent HTTP endpoint.

The contract is fixed: intent, entities, draft, confidence, citations,
escalate. Answers must cite a source in the knowledge base rather than
returning free-floating text, and a guard on the inbound message id stops a
duplicate webhook delivery from producing a second draft for the same
message.

classify() is the swappable part: point it at any model or agent call and
the contract, the guard, and the eval harness in eval/ all stay the same.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

DATA_DIR = Path(__file__).parent.parent / "data"
KB = json.loads((DATA_DIR / "knowledge_base.json").read_text())
AVAILABILITY = json.loads((DATA_DIR / "availability.json").read_text())

app = FastAPI(title="Inbox Agent")

# In-memory redelivery guard. In production this is a durable row keyed on
# the inbound message id, checked before the agent is even called.
_seen_message_ids: dict[str, dict] = {}

# Intents that touch money, cancellations, or a legal requirement never
# auto-send, no matter what the confidence score says.
NEVER_AUTO_SEND = {"cancellation", "refund", "insurance_change", "payment_dispute"}

# Order matters: more specific intents are checked before the generic
# "availability" pattern, so "is the fuel dock open" doesn't get read as an
# availability question just because it contains the word "open".
RULES = [
    ("fuel", re.compile(r"\b(fuel|diesel|gas dock|gasoline)\b", re.I), ["fuel"]),
    ("hours", re.compile(r"\b(hours|open until|what time|close)\b", re.I), ["hours"]),
    ("directions", re.compile(r"\b(directions|how do i get|address|located)\b", re.I), ["directions"]),
    ("cancellation", re.compile(r"\b(cancel|refund)\b", re.I), ["cancellation_policy"]),
    ("insurance_change", re.compile(r"\b(insurance|liability|certificate of insurance|coi)\b", re.I), ["insurance_requirement"]),
    ("rate_card", re.compile(r"\b(rate|price|cost|how much|per night|per foot)\b", re.I), ["rate_card"]),
    ("availability", re.compile(r"\b(availab|vacan|any (slip|site|spot)|do you have any)\b", re.I), ["rate_card"]),
]


class InboundEmail(BaseModel):
    message_id: str
    subject: str
    body: str
    sender: str


class AgentResponse(BaseModel):
    intent: str
    entities: dict
    draft: str
    confidence: float
    citations: list[str]
    escalate: bool
    duplicate: bool = False


def classify(text: str) -> tuple[str, list[str], float]:
    for intent, pattern, citation_keys in RULES:
        if pattern.search(text):
            return intent, citation_keys, 0.86
    return "unclassified", [], 0.31


def build_draft(intent: str, citation_keys: list[str], entities: dict) -> str:
    if intent == "availability":
        avail = AVAILABILITY["slips"]["transient"]
        return (
            f"Thanks for reaching out! As of {AVAILABILITY['as_of'][:10]} we have "
            f"{avail['open']} of {avail['total']} transient slips open. "
            f"Rates: {KB['rate_card']['text']} Let us know your boat length and dates "
            f"and we'll confirm."
        )
    if intent in KB:
        return f"Thanks for asking. {KB[intent]['text']}"
    return (
        "Thanks for your message. A member of our office team will follow up "
        "shortly, we want to make sure you get an accurate answer."
    )


@app.post("/agent/respond", response_model=AgentResponse)
def respond(email: InboundEmail) -> AgentResponse:
    # Redelivery guard: same message id twice returns the cached response
    # and never generates a second draft. This is the piece that stops a
    # webhook retry from sending a duplicate reply.
    if email.message_id in _seen_message_ids:
        cached = dict(_seen_message_ids[email.message_id])
        cached["duplicate"] = True
        return AgentResponse(**cached)

    intent, citation_keys, confidence = classify(f"{email.subject} {email.body}")
    citations = [KB[k]["source"] for k in citation_keys if k in KB]
    draft = build_draft(intent, citation_keys, {})

    escalate = (
        intent in NEVER_AUTO_SEND
        or intent == "unclassified"
        or confidence < 0.6
        or (intent not in ("availability",) and not citations and intent != "unclassified")
    )

    result = {
        "intent": intent,
        "entities": {},
        "draft": draft,
        "confidence": confidence,
        "citations": citations,
        "escalate": escalate,
        "duplicate": False,
    }
    _seen_message_ids[email.message_id] = result
    return AgentResponse(**result)


@app.get("/healthz")
def healthz():
    return {"ok": True, "seen_message_ids": len(_seen_message_ids)}
