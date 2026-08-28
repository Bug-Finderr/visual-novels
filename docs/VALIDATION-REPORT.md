# Validation Report

**Project:** StoryPlex — AI-generated visual novels
**Date of this run:** 28 August 2026
**Environment:** macOS (Darwin 25.6.0), Python 3.14.6, PostgreSQL 16.15 (Docker), Node 18+

This report records what was actually run and what it produced. Raw console output for every suite
is in [`evidence/`](evidence/) and can be regenerated with the commands shown.

---

## 1. Summary

| Suite | Checks | Result |
|---|---:|---|
| Billing and credits | 68 | **PASS** |
| Generation admission control | 17 | **PASS** |
| Model availability | 8 | **PASS** |
| Story graph | 3 scenarios | **PASS** |
| **Total** | **93 + 3** | **All passing** |

```
verify_billing            68 checks   ALL CHECKS PASSED ✅
verify_generation_queue   17 checks   ALL CHECKS PASSED ✅
verify_models              8 checks   ALL MODELS OK ✅
verify_storygraph          3 scenarios ALL CHECKS PASSED ✅
```

Every script exits non-zero on failure. Evidence files are the unedited output of the run above.

---

## 2. Defects found and fixed during validation

The point of writing these suites was to find real problems. They did. Each of the following was a
genuine defect in code already running in production.

### 2.1 Double-spend / double-generation race (critical)

**Found by:** TC-3.
**Defect:** `start_generation` read the session status, then wrote it — a TOCTOU window in which two
concurrent requests both passed the check and both launched a pipeline.
**Impact:** duplicated Gemini spend, and once billing existed, an unpriced second generation.
**Fix:** the status claim and the credit debit became conditional writes inside one transaction
(`UPDATE … WHERE status IN ('created','error')`, `UPDATE … WHERE balance + delta >= 0`), so the
loser observes `rowcount 0`.
**Verified:** 8 concurrent attempts, exactly one winner, one debit, one ledger row.

### 2.2 Refund did not reclaim credits (critical, financial)

**Found by:** review while writing TC-9, prompted by asking what happens after a dashboard refund.
**Defect:** refunds are issued from the Cashfree dashboard; the application never learned of them.
A refunded customer kept their credits — money back *and* the stories.
**Fix:** `REFUND_STATUS_WEBHOOK` now reclaims credits in proportion to the amount refunded.
**Verified:** TC-9.1–9.6, TC-10.1–10.5.

### 2.3 Refund clawback could exceed the amount granted

**Found by:** TC-9.4, while writing the tests for 2.2.
**Defect:** each refund was capped proportionally but the *cumulative* total was not, so two full
refunds against one order reclaimed 10 credits for a 5-credit pack, driving an honest customer to a
false −3.
**Fix:** reclaims are capped against what remains reclaimable on the order.
**Verified:** a second, distinct refund past 100% now reclaims nothing.

### 2.4 Declined payments reported as "still confirming"

**Found by:** user report, then pinned by TC-11.
**Defect:** a declined attempt leaves the *order* `ACTIVE` (the customer may retry it). Only
`EXPIRED`/`TERMINATED` were treated as failure, so a decline fell through to polling and was
reported as pending — the opposite of what happened.
**Fix:** when the order is still `ACTIVE`, the payment *attempts* are queried and the newest mapped
to `failed` / `abandoned` / `pending`.
**Verified:** TC-11.1–11.8, including that a later `SUCCESS` is never reported as failed.

### 2.5 Unbounded generation concurrency (critical, availability)

**Found by:** capacity analysis during validation.
**Defect:** pipelines were dispatched with `asyncio.create_task` and no admission control. Each peaks
near 500 MB against a 2 GB instance with a ~129 MB baseline, so roughly the 4th simultaneous
generation exhausted memory — and an OOM killed every in-flight generation and the web service.
**Fix:** a semaphore (`MAX_CONCURRENT_GENERATIONS`, default 3); beyond it generations queue and the
player is shown their position.
**Verified:** TC-12 to TC-15, including that a crashing pipeline releases its slot.

### 2.6 Retired models broke generation

**Found by:** `verify_models.py` on first run.
**Defect:** `gemini-2.5-pro` and `gemini-2.5-flash` returned `404 … no longer available to new
users`. Generation was broken in production while billing was live.
**Fix:** migrated to the Gemini 3.x line and made model ids env-overridable
(`MODEL_STORY`/`MODEL_DIALOGUE`/`MODEL_IMAGE`), so the next retirement is a config change.
**Verified:** all three configured models called for real (TC-16).

### 2.7 Support contact address did not exist

**Found by:** pre-deployment check of the published policy pages.
**Defect:** the refund and privacy pages listed `support@storyplex.app`; the domain has no MX
records, so that mailbox could not receive mail — while the refund policy promised a reply within 3
working days.
**Fix:** changed to an address verified to resolve (MX records confirmed).

---

## 3. Performance and cost measurements

### 3.1 Selective asset generation

Measured on a complete end-to-end generation, comparing the fixed catalogue against generating only
what the produced script references.

| Asset | Before | After | Reduction |
|---|---:|---:|---:|
| Expression sprites | 40 | 18 | **55%** |
| Scene backgrounds | 12 | 7 | **42%** |
| Total images (incl. cover) | 53 | 26 | **51%** |

The pipeline was reordered so dialogue text is generated *before* images; the generated text is then
scanned for the (character, expression) pairs and scene ids actually used. A runtime fallback serves
the neutral sprite for any expression never pre-rendered, verified byte-identical to the real file.

### 3.2 Memory

| Measurement | Value | Method |
|---|---:|---|
| Application baseline | **129 MB** | `ru_maxrss` after importing the full app |
| Peak per generation pipeline | **~500 MB** | 13 sprite tasks at 6-way concurrency |
| Instance limit | 2048 MB | Render Standard |
| Derived safe concurrency | **3** | `(2048 − 129) / ~500` with headroom |

Before this work the baseline was ~750 MB, because the background-removal library loaded an ONNX
model at import. Replacing it with a numpy/PIL chroma-key cut the baseline to 129 MB and removed the
recurring OOM crashes.

### 3.3 Generation cost per story

| Component | Before | After |
|---|---:|---:|
| Images | ₹182 (53 × $0.039) | **₹77** (26 × $0.0336) |
| Text | ~₹24 | **~₹10** |
| **Total** | **~₹206** | **~₹87** |

A **~58% reduction**, from two independent changes: selective asset generation (§3.1) and migrating
to cheaper current models (§2.6).

### 3.4 Request throughput

| Measurement | Value |
|---|---:|
| 50 concurrent health requests | 64 ms total |
| 50 concurrent database-backed requests | 147 ms total |

Reading and browsing are not the constraint; generation is.

---

## 4. Image model comparison

Conducted while selecting the cheapest viable image model. The sprite pipeline requires a flat
chroma-key background it can key out, so cost alone was not sufficient grounds to choose.

| Model | Price/image | Border RGB (target: magenta) | Flat magenta background |
|---|---:|---|---:|
| `gemini-3.1-flash-lite-image` | **$0.0336** | ~(247, 14, 239) | **3/3** |
| `gemini-2.5-flash-image` | $0.039 | ~(230, 30, 140) | 0/3 |

The adaptive border-median sampler tolerates the pink drift, so the older model was not generally
broken. However one sample framed the magenta fill inside a white border, which defeats the sampler
entirely — the background survived and part of the character was erased. The selected model did not
exhibit this in any sample, and is cheaper.

**Limitation:** three samples per model. Sufficient to choose between them, not sufficient to state a
failure rate.

---

## 5. Validation limitations

- **Sample sizes are small.** The image comparison used 3 samples per model; the cost measurements
  come from one full generation each. Directionally sound, not statistically rigorous.
- **Load testing was not performed.** Concurrency limits are derived from measured per-pipeline
  memory against instance size, not from a sustained load run.
- **The payment gateway is stubbed** in automated tests; the live integration was exercised manually
  against Cashfree's sandbox.
- **Story quality is not automatically assessed.** The suites confirm well-formed output, not good
  writing or art.
- **Single-environment.** All measurements are from one macOS development machine and one Render
  Standard instance.

---

## 6. Conclusion

All 93 automated checks and 3 graph scenarios pass. Seven defects were found and fixed during
validation, four of them affecting money or availability directly. Cost per story fell ~58% and the
recurring out-of-memory failures were eliminated.

The system is functional and deployed. The most significant known risk is not a code defect but an
operational one: the production database remains on a free tier that expires 30 days after creation
and now holds financial records.
