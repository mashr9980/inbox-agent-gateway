#!/usr/bin/env python3
"""
Proves the redelivery guard: the same message id hitting the agent twice
(a webhook retry) must never produce a second draft.
"""
import json
import urllib.request

SERVER = "http://127.0.0.1:8000/agent/respond"


def call(message_id: str):
    payload = {
        "message_id": message_id,
        "subject": "Do you have any open slips this weekend?",
        "body": "Hi, do you have any transient slips open for Fri-Sun?",
        "sender": "guest1@example.com",
    }
    req = urllib.request.Request(
        SERVER, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


if __name__ == "__main__":
    first = call("gmail-thread-abc123")
    second = call("gmail-thread-abc123")  # simulates a webhook retry
    print("First delivery: ", json.dumps(first, indent=2))
    print("\nSecond delivery (same message id):", json.dumps(second, indent=2))
    assert first["duplicate"] is False, "first call should not be flagged duplicate"
    assert second["duplicate"] is True, "retried delivery must be flagged duplicate"
    print("\nPASS: retried webhook did not generate a second draft.")
