# inbox-agent-gateway

A small reference implementation for a customer-inbox agent: a fixed JSON
contract, a citation requirement so answers trace back to a real source, a
guard against duplicate webhook deliveries, and an evaluation harness that
replays a labeled test set against the running endpoint and reports a
pass rate per intent.

The intent classifier itself is swappable — the piece that stays constant
across whatever generates the reply is the contract and the checks around it.

## What's here

```
app/server.py               agent HTTP endpoint: intent, entities, draft,
                             confidence, citations, escalate
data/knowledge_base.json    source-of-truth facts, each with a citation key
data/availability.json      sample data the agent queries as a tool
eval/labeled_set.csv        labeled test rows
eval/run_eval.py            replays the set, prints pass rate per intent
eval/promptfooconfig.yaml   the same replay as a promptfoo config
eval/redelivery_guard_check.py   proves a retried webhook writes once
```

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.server:app --port 8000 &

.venv/bin/python3 eval/run_eval.py
.venv/bin/python3 eval/redelivery_guard_check.py

# or, with promptfoo installed:
npx promptfoo eval -c eval/promptfooconfig.yaml
```

## Why it's built this way

Money, cancellation, and account-permission intents never auto-send,
regardless of confidence score — see `NEVER_AUTO_SEND` in `app/server.py`.
Every fact the agent states carries a citation back to
`knowledge_base.json`, so an answer with no citation is treated as
unsafe to send on its own. The redelivery guard keys on the inbound
message id, so a webhook firing twice never produces a second draft.

---
Muhammad Aashir Tariq · AI engineer, solo, 5+ years, 50+ apps shipped.
