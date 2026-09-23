#!/usr/bin/env python3
"""
Replays a labeled test set against a running agent endpoint and prints a
pass rate per intent -- the number that gates a promotion from drafts-only
to auto-send. See promptfooconfig.yaml for the same replay as a promptfoo
config, for setups where that tool is preferred over a plain script.
"""
import csv
import json
import sys
import urllib.request
from pathlib import Path

SERVER = "http://127.0.0.1:8000/agent/respond"
CSV_PATH = Path(__file__).parent / "labeled_set.csv"


def call_agent(row: dict) -> dict:
    payload = {
        "message_id": row["message_id"],
        "subject": row["subject"],
        "body": row["body"],
        "sender": row["sender"],
    }
    req = urllib.request.Request(
        SERVER, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def main():
    rows = list(csv.DictReader(CSV_PATH.open()))
    results = []
    for row in rows:
        agent = call_agent(row)
        intent_ok = agent["intent"] == row["expected_intent"]
        citation_ok = (row["requires_citation"] == "false") or bool(agent["citations"])
        escalate_ok = agent["escalate"] == (row["requires_escalate"] == "true")
        passed = intent_ok and citation_ok and escalate_ok
        results.append({"id": row["message_id"], "intent": row["expected_intent"], "pass": passed,
                         "detail": agent})

    total = len(results)
    passed = sum(r["pass"] for r in results)
    print(f"\n{'ID':<6} {'INTENT':<18} {'RESULT'}")
    print("-" * 40)
    for r in results:
        mark = "PASS" if r["pass"] else "FAIL"
        print(f"{r['id']:<6} {r['intent']:<18} {mark}")
        if not r["pass"]:
            print(f"       got: {r['detail']}")

    by_intent: dict[str, list[bool]] = {}
    for r in results:
        by_intent.setdefault(r["intent"], []).append(r["pass"])

    print(f"\nPer-intent pass rate:")
    for intent, outcomes in sorted(by_intent.items()):
        rate = 100 * sum(outcomes) / len(outcomes)
        print(f"  {intent:<18} {sum(outcomes)}/{len(outcomes)}  ({rate:.0f}%)")

    overall = 100 * passed / total
    print(f"\nOverall: {passed}/{total} ({overall:.0f}%)")

    GATE = 90
    if overall < GATE:
        print(f"\nBELOW GATE ({GATE}%) -- nothing gets promoted to auto-send.")
        sys.exit(1)
    else:
        print(f"\nAt or above gate ({GATE}%).")


if __name__ == "__main__":
    main()
