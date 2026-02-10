# Nightingale — Demo Script

## Introduction

"Hi, I'm [Name], and this is **Nightingale** — an autonomous CI repair agent powered by Gemini 3.

When your CI pipeline breaks, Nightingale detects the failure, uses Gemini 3 to reason about the root cause, generates a fix, verifies it in an isolated sandbox, and decides whether to auto-resolve or escalate — all without human intervention.

Let me show you."

---

## Step 1 — Show the Bug

> Open `demo_repo/test_app.py` in your editor side-by-side with the terminal.

"Here's our codebase. Two functions — `add` and `subtract` — and two tests. `test_add` is correct, but look at line 12:"

```python
def test_subtract():
    # This test is intentionally broken
    assert subtract(2, 2) == 1  # ❌ BUG — 2 minus 2 is 0, not 1
```

"This is the kind of bug someone pushes at 2 AM. Let's see Nightingale fix it."

---

## Step 2 — Verify API

> Run: `python main.py --verify-api`

When you see:
```
  API reachable:  YES
  SDK:            google-genai v1.62.0
  Model:          models/gemini-3-flash-preview
```

"We're connected to Gemini 3 — the official google-genai SDK, using `models/gemini-3-flash-preview`. Now let's trigger the agent."

---

## Step 3 — Run the Demo

> Run: `python main.py --demo`

### When the banner appears:
```
    NIGHTINGALE
    Autonomous CI SRE Agent
    Powered by Gemini 3
```
"Nightingale starts up."

### When you see:
```
CI FAILURE DETECTED
Dispatching Nightingale Agent...
```
"A CI failure has been detected — pytest found a failing test. The agent picks it up automatically."

### When you see:
```
INFO     Gemini client initialized
INFO       SDK:   google-genai v1.62.0
INFO       Model: models/gemini-3-flash-preview
```
"The Gemini client initializes with the flash preview model."

### When the incident box appears:
```
╭─── CI FAILURE DETECTED ───╮
│ Incident ID: demo-...     │
│ Type: test_failure         │
╰────────────────────────────╯
```
"It creates an incident — type `test_failure`, linked to our repository."

### When you see:
```
━━━ Attempt 1/3 ━━━
├─ Gathering repository context
├─ Constructing analysis prompt
├─ Calling Gemini for analysis
├─ API Call: models/gemini-3-flash-preview (~4800 tokens, ~24s)
```
"The Marathon agent starts its first attempt. It gathers the repo context — files, commits, test content — then sends everything to Gemini 3 with the failure logs. That's about 4800 tokens processed."

### When the fix plan appears:
```
Fix Plan:
├─ Corrected the assertion in test_subtract to expect 0
├─ demo_repo/test_app.py
```
"Gemini identified the root cause — the expected value in the assertion is wrong. It generates a one-line fix."

### When you see the sandbox:
```
INFO     [SANDBOX] Original repo hash: fa88a0ef...
INFO     [SANDBOX] Created sandbox at .sandbox/...
INFO     [SANDBOX] Applied 1 file change(s)
```
"The fix is applied in an isolated sandbox first — a full copy of the repo that's SHA-256 hashed before and after to guarantee zero contamination."

### When you see:
```
├─ Verification: PASSED (2/2 tests)
INFO     Verification passed: 2/2
```
"Pytest runs inside the sandbox. Both tests pass! The fix works."

### When the confidence table appears:
```
┃ Factor                 ┃ Raw Score ┃ Weight ┃ Contribution ┃
│ Test Pass Ratio        │     1.000 │    35% │       0.3500 │
│ Inverse Blast Radius   │     0.974 │    25% │       0.2434 │
│ Attempt Penalty        │     1.000 │    15% │       0.1500 │
│ Risk Modifier          │     0.400 │    15% │       0.0600 │
│ Self Consistency Score │     1.000 │    10% │       0.1000 │
│ TOTAL                  │           │        │ 0.9034 (90%) │
```
"The confidence engine scores the fix across five weighted factors. Test pass ratio: perfect. Blast radius: minimal. First attempt. Total confidence: **90.3 percent**."

### When you see:
```
╭─── Decision ───╮
│ AUTO-RESOLVING  │
│ Confidence: 90% │
╰─────────────────╯
INFO     Decision: resolve
INFO     Decision is RESOLVE – applying fix to main repository...
```
"90 percent exceeds our threshold. Decision: **AUTO-RESOLVE**.

**Watch the editor on the right:**"

> **POINT AT THE EDITOR NOW.** The file `test_app.py` will update automatically.

```diff
- assert subtract(2, 2) == 1
+ assert subtract(2, 2) == 0
```

"There! The fix is applied to the main repository automatically."

### When you see:
```
Demo Complete
The agent successfully resolved the issue.
```
"Done."

---

## Step 4 — Wrap Up

"To recap — Nightingale detected a broken test, used Gemini 3 to reason about the root cause, verified the fix safely in a sandbox, scored it at 90 percent confidence, and **automatically patched the code** in seconds.

And if the first fix had failed, the reflective loop would retry with a different approach.

This is Nightingale — autonomous CI repair, powered by Gemini 3. Thank you."

---

## Checklist

- [ ] `demo_repo/test_app.py` has `== 1` (Broken)
- [ ] `$env:GEMINI_API_KEY` is set
- [ ] Run `python main.py --verify-api` once to check
- [ ] Start recording
