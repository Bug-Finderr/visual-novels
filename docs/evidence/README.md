# Test Evidence

Unedited console output from the verification suites, captured on the date recorded in the
[Validation Report](../VALIDATION-REPORT.md).

| File | Suite | Checks |
|---|---|---:|
| `verify_billing.txt` | Billing, credits, refunds | 68 |
| `verify_generation_queue.txt` | Generation admission control | 17 |
| `verify_models.txt` | Live Gemini model availability | 8 |
| `verify_storygraph.txt` | Story generation graph | 3 scenarios |

Regenerate any of these:

```bash
cd server
./.venv/bin/python scripts/verify_billing.py           > ../docs/evidence/verify_billing.txt
./.venv/bin/python scripts/verify_generation_queue.py  > ../docs/evidence/verify_generation_queue.txt
./.venv/bin/python scripts/verify_models.py            > ../docs/evidence/verify_models.txt
STORYGEN_ENGINE=graph ./.venv/bin/python scripts/verify_storygraph.py > ../docs/evidence/verify_storygraph.txt
```

Requires the local Postgres running (`docker compose up -d`). `verify_models.py` makes real API
calls and costs a few rupees; the others spend nothing.
