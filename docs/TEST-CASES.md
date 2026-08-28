# Test Cases

Every test case in the project, what it proves, and how to reproduce it.

Testing here is organised around **the things that are expensive to get wrong**: money, concurrency,
and external models. Each suite runs against a real PostgreSQL database — only the external paid
services (payment gateway, LLM) are stubbed, and only where a real call would spend money without
adding confidence.

## Running everything

```bash
cd server
./.venv/bin/python scripts/verify_billing.py           # 68 checks
./.venv/bin/python scripts/verify_generation_queue.py  # 17 checks
./.venv/bin/python scripts/verify_models.py            #  8 checks
STORYGEN_ENGINE=graph ./.venv/bin/python scripts/verify_storygraph.py   # 3 scenarios
```

**93 automated checks.** Raw output from the recorded run is in [`evidence/`](evidence/).

Each script exits non-zero on failure, so all four are CI-ready as-is.

---

## Suite 1 — Billing and credits
`scripts/verify_billing.py` · 68 checks · real Postgres, gateway stubbed

The money paths. Stubbing the gateway is deliberate: the properties worth proving (can two
concurrent spends both win? can a replayed webhook credit twice?) are database properties, and only
appear under real transactions.

### TC-1: Free signup grant

| # | Case | Expected |
|---|---|---|
| 1.1 | First read of a new user's credit account | Balance = 2 (`FREE_STORY_CREDITS`) |
| 1.2 | Grant size recorded on the account | `free_granted` = 2 |
| 1.3 | Account read repeatedly | Balance still 2 — no re-grant |
| 1.4 | Ledger after repeated reads | Exactly one `signup_grant` row |

*Why:* the grant is lazy (on first touch, not at signup) so pre-existing accounts are backfilled.
That makes accidental re-granting the obvious failure mode.

### TC-2: Balance floor and ledger integrity

| # | Case | Expected |
|---|---|---|
| 2.1 | Spend 1 of 2 credits | Balance = 1 |
| 2.2 | Attempt to spend 5 with 1 held | Refused (returns `None`) |
| 2.3 | Balance after a refused spend | Unchanged at 1 |
| 2.4 | Ledger contents | Grant + accepted spend only; the refusal is not recorded |
| 2.5 | Newest ledger row | Carries the running balance |

### TC-3: Concurrent generation — the double-spend race

| # | Case | Expected |
|---|---|---|
| 3.1 | 8 concurrent `/generate` on one session, 1 credit held | Exactly **1** succeeds |
| 3.2 | Credits spent | Exactly 1 |
| 3.3 | Ledger debit rows | Exactly 1 |
| 3.4 | Final session status | `generating` |

*Why:* the original code did check-then-set on session status — a TOCTOU race where two concurrent
requests both passed the check and both started a pipeline. The fix makes the status claim and the
debit conditional writes inside one transaction, so the loser sees `rowcount 0`.

### TC-4: Insufficient credits rolls back cleanly

| # | Case | Expected |
|---|---|---|
| 4.1 | `/generate` with balance 0 | Raises `_InsufficientCredits` |
| 4.2 | Session status afterwards | Still `created`, **not** `generating` |

*Why:* if the status claim survived a failed payment, the user would own a session permanently
wedged in `generating` that could never be retried.

### TC-5: Webhook signature verification

| # | Case | Expected |
|---|---|---|
| 5.1 | Correct HMAC-SHA256 signature | Accepted |
| 5.2 | Body altered by one byte | Rejected |
| 5.3 | Timestamp altered | Rejected |
| 5.4 | Malformed signature | Rejected |
| 5.5 | Valid signature from a different secret | Rejected |

### TC-6: Settlement idempotency

| # | Case | Expected |
|---|---|---|
| 6.1 | First settle of a paid order | Credits granted |
| 6.2 | Balance | Rises by the pack's credits |
| 6.3 | Second settle of the same order | No-op |
| 6.4 | Balance after replay | Unchanged |
| 6.5 | Purchase ledger rows | Exactly one |
| 6.6 | `lifetime_purchased` | Counted once |
| 6.7 | **6 concurrent settles** of one order | Exactly one credits |

*Why:* the webhook and the browser's return-URL verify both settle, and either can arrive first.
Guarded three ways — a `SELECT … FOR UPDATE` row lock, the `credited_at` stamp, and a UNIQUE
ledger key.

### TC-7: Amount verification

| # | Case | Expected |
|---|---|---|
| 7.1 | Gateway reports PAID for ₹1 on a ₹1,699 order | Not credited |
| 7.2 | Reported status | `amount_mismatch` |
| 7.3 | Balance | Untouched |
| 7.4 | Order status | `failed` |

### TC-8: Failure recording

| # | Case | Expected |
|---|---|---|
| 8.1 | `PAYMENT_FAILED_WEBHOOK` | Order status `failed` |
| 8.2 | `error_reason` / `error_code` | Stored on the order |
| 8.3 | `cf_payment_id` | Captured |
| 8.4 | `PAYMENT_USER_DROPPED_WEBHOOK` | Status `abandoned`, tracked apart from a decline |
| 8.5 | A late failure webhook for an order already paid | Status stays `paid` |
| 8.6 | That order's failure fields | Remain empty |

### TC-9: Refund clawback

| # | Case | Expected |
|---|---|---|
| 9.1 | Full refund of an unspent 5-credit pack | 5 credits reclaimed |
| 9.2 | Order status | `refunded` |
| 9.3 | Same refund id replayed | Reclaims nothing |
| 9.4 | A second, distinct refund past 100% | Reclaims nothing |
| 9.5 | Half refund of a 10-credit pack | 5 reclaimed, status `partially_refunded` |
| 9.6 | Refund with status `PENDING` | Nothing reclaimed yet |

*Why:* refunds are issued from the Cashfree dashboard, so the webhook is the only way the app learns
money went back. Without it a refunded customer keeps their credits.

### TC-10: Refund after the credits were spent

| # | Case | Expected |
|---|---|---|
| 10.1 | Refund 5 credits already spent on stories | 5 reclaimed |
| 10.2 | Resulting balance | **−5** — negative, not absorbed |
| 10.3 | Generation attempt at −5 | Blocked |
| 10.4 | Session after the blocked attempt | Still `created`, retryable |
| 10.5 | Buying 5 credits again | Balance returns to 0 |

*Why:* silently absorbing the shortfall would hand out free stories. A negative balance is the
honest record and blocks generation until the customer buys back in.

### TC-11: Declined payments are reported as declined

| # | Case | Expected |
|---|---|---|
| 11.1 | Order `ACTIVE` + latest attempt `FAILED` | Status `failed` |
| 11.2 | Decline reason | Returned for the UI to display |
| 11.3 | Order row | Marked `failed` |
| 11.4 | Credits | None granted |
| 11.5 | Attempt `USER_DROPPED` | Status `abandoned` |
| 11.6 | Attempt `PENDING` | Status `pending` |
| 11.7 | No attempts yet | Status `pending` |
| 11.8 | `FAILED` then `SUCCESS` | Not reported as failed |

*Why:* a declined attempt leaves the **order** `ACTIVE`, because the customer may retry it. Checking
order status alone reported a failed payment as "still being confirmed" — the opposite of the truth.

---

## Suite 2 — Generation admission control
`scripts/verify_generation_queue.py` · 17 checks · pipeline stubbed, no model spend

| # | Case | Expected |
|---|---|---|
| 12.1 | 9 concurrent starts, limit 3 | Peak concurrency never exceeds 3 |
| 12.2 | Same run | Peak reaches 3 — the allowance is fully used |
| 12.3 | Same run | All 9 eventually run; none starved |
| 12.4 | After completion | Queue and active set both empty |
| 13.1 | 6 starts, limit 3 | Exactly 3 reported as queued |
| 13.2 | Queue positions | `1, 2, 3` — contiguous, no gaps |
| 13.3 | Position 1 message | "you're next in line" |
| 13.4 | Position 3 message | "2 stories ahead of you" |
| 13.5 | Queued progress value | 0% (the bar is hidden for these) |
| 13.6 | After the first batch finishes | Queue drains |
| 13.7 | At the end | Queue empty |
| 14.1 | All 3 running pipelines crash | The 3 behind still run |
| 14.2 | After the crashes | No slot leaked |
| 14.3 | After the crashes | No ghost queue entries inflating positions |
| 14.4 | Crashed sessions | Reported as errors to their players |
| 15.1 | 6 starts | The first 3 submitted run first |
| 15.2 | Same run | The queued 3 run after, not before |

*Why:* a pipeline peaks near 500 MB against a 2 GB instance. Without a cap, the 4th simultaneous
generation OOM'd the instance and killed every other in-flight story. TC-14 matters most — a queue
that wedges on the first error would be worse than no queue.

---

## Suite 3 — Model availability
`scripts/verify_models.py` · 8 checks · **live API calls, costs a few rupees**

| # | Case | Expected |
|---|---|---|
| 16.1 | Story model reachable | Responds |
| 16.2 | Story model output | Usable |
| 16.3 | Dialogue model reachable | Responds |
| 16.4 | Dialogue model output | Usable |
| 16.5 | Image model | Returns image bytes |
| 16.6 | Generated background flatness | Border spread < 25 |
| 16.7 | Generated background hue | In the magenta family |
| 16.8 | After chroma-key removal | 40–95% transparent |

*Why:* Google retires models on its own schedule. When `gemini-2.5-pro` began returning
`404 no longer available`, generation broke in production with billing live. This suite turns that
into a pre-flight check. Checks 16.6–16.8 go further than reachability: they confirm the model still
produces the flat chroma-key background the sprite cutout depends on.

**Run this after any model change, and after any generation outage.**

---

## Suite 4 — Story graph
`scripts/verify_storygraph.py` · 3 scenarios · LLM mocked, no quota spent

| # | Case | Expected |
|---|---|---|
| 17.1 | Full graph run: plot → world → characters → chapter → memory → assemble | Valid story contract |
| 17.2 | Memory gate with a deliberately broken first chapter | Revision loop runs, output repaired |
| 17.3 | `generate_world` with `STORYGEN_ENGINE=graph` | Routes to the graph engine and tags the result |

---

## Manual test cases

Cases that need a human or a real browser.

| # | Case | Steps | Expected |
|---|---|---|---|
| M-1 | Google sign-in | Click Sign in → complete Google consent | Returns signed in; `/me` shows the user |
| M-2 | End-to-end generation | Create a story, wait | Reaches `ready`; playable with art and voices |
| M-3 | Live progress | Watch the loading page | SSE progress advances through named phases |
| M-4 | Queue display | Start 4 generations at once | 4th shows its queue position, then starts |
| M-5 | Successful payment | Buy the ₹199 pack, sandbox UPI `testsuccess@gocash` | Returns to success page; balance +1; ledger row |
| M-6 | Failed payment | Same, with `testfailure@gocash` | Failure page with reason; balance unchanged |
| M-7 | Out of credits | Generate with balance 0 | 402 handled as a top-up prompt, not a raw error |
| M-8 | Publish / unpublish | Toggle in library | Appears in / disappears from Explore |
| M-9 | Missing sprite fallback | Request an expression never generated | Serves `neutral.png`, not a 404 |
| M-10 | Cross-device session | Sign in on a second device | Library and credits match |

---

## What is not covered

Stated plainly, because a test plan that claims total coverage is not credible:

- **No unit tests for pure helpers.** Coverage is concentrated on integration behaviour, where this
  project's real defects have been.
- **No frontend component tests.** UI is verified manually (M-1 to M-10).
- **No load testing.** Capacity is derived from measured per-pipeline memory against instance size,
  not from a sustained load run.
- **Story quality is not automatically assessed.** Generated prose and art are judged by reading and
  looking; the suites verify the pipeline produces well-formed output, not that it is good.
- **The live payment gateway is stubbed** in automated tests. The real integration is exercised
  manually against Cashfree's sandbox (M-5, M-6).
