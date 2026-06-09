# v8 / Day 29 — Run failure report (observability for an unattended cron)

**Goal:** the pipeline's per-stage guards keep the daily run alive, but they also
mean a dying piece — a broken channel post, a dead source, failing email — only
shows up in GitHub Actions logs nobody reads. Close the gap: collect every guarded
failure during the run and **DM a summary to the owner** at the end, so silent
degradation becomes a same-day Telegram ping instead of a weeks-later surprise.

---

## 1. Failure collector in `main.py`

- A module-level `_failures: list[str]` plus a `_fail(stage, exc)` helper that
  prints (as before) *and* records `"stage: exc"`. Every existing guarded
  `except` switches from a bare `print` to `_fail(...)`: source fetches,
  dashboard build, Dutch build / audio / persist, waitlist post, Telegram and
  email delivery, dev.to cross-post.
- The old `main()` body becomes `_run()`; the new `main()` wraps it:

```python
def main() -> None:
    try:
        _run()
    except Exception as exc:
        _fail("run", exc)   # hard crash is reported too...
        raise               # ...and re-raised so the Actions run still goes red
    finally:
        _report()           # covers early returns (quiet day, no gap) as well
```

- `_report()` no-ops when there are no failures or `RUN_REPORT_ENABLED = False`;
  otherwise it sends one message listing every failure with the run date.

## 2. `telegram_sender.send_report(text)`

- Plain-text `sendMessage` to **`TELEGRAM_CHAT_ID` only — never the channel**
  (operational noise is not subscriber content), with the main bot token,
  trimmed to the 4096-char message cap. No-op when token/chat id are unset.
- Best-effort by design: if Telegram itself is down the report can't help, but
  partial failures (one source, one target, email) still reach the owner via
  the surviving DM path. `_report()` swallows its own send failure.

## 3. Surface partial Telegram delivery

`telegram_sender.send()` previously caught per-target failures internally, so a
misconfigured channel was invisible to `main()`. It still attempts **every**
target before giving up (isolation preserved), but now re-raises a single
`RuntimeError` naming the failed target(s) — which `main()`'s guard records
into the run report.

```python
RUN_REPORT_ENABLED = True   # False -> logs only (legacy behavior)
```

---

## Out of scope

- Retries/backoff for failed stages (the next daily run is the retry).
- Alerting channels beyond the owner DM (no email alert, no GitHub issue).
- Distinguishing transient from persistent failures — the owner reading one
  DM a day is the triage.
