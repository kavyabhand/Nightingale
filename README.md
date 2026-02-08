# Nightingale: The Autonomous On-Call SRE

**Target:** Google DeepMind Gemini 3 Hackathon (Action Era, Vibe Engineering)  
**Tagline:** The Autonomous On-Call SRE for CI/CD Failures

## Overview

Nightingale is an autonomous agentic system designed to replace the need for "3am on-call engineers" for release-blocking CI/CD failures. It detects pipeline failures, reasons over the repository using long-horizon analysis, identifies root causes, applies fixes in a sandbox, verifying them, and either auto-resolves the incident or escalates with a precise diagnostic report.

## Value Proposition

-   **Zero-Touch Resolution:** Automatically fixes flaky tests, dependency mismatches, and configuration errors.
-   **Risk-Aware:** Only applies fixes in a sandbox and computes a calibrated confidence score.
-   **Explainable:** Every decision is backed by a rationale and verifiable evidence.
-   **24/7 Availability:** Never sleeps, ensuring pipelines are always green.

## Architecture

Nightingale is built on a modular architecture:
1.  **Incident Listener:** Ingests failure signals.
2.  **Repo Context Loader:** Prepares the codebase for analysis.
3.  **Marathon Agent (Gemini 3 Pro):** Reasons about the failure and plans a fix.
4.  **Verification Agent (Gemini 3 Flash):** Executes the fix and validates it in a sandbox.
5.  **Orchestrator:** Manages the entire lifecycle.

## How to Run the Demo

Nightingale comes with a self-contained demo scenario that simulates a broken CI pipeline.

### Prerequisites

-   Python 3.10+
-   `pip install -r requirements.txt`

### Run Demo

```bash
python3 main.py --demo
```

**What to expect:**
1.  Nightingale detects a test failure in `demo_repo/test_app.py`.
2.  It spins up a sandbox environment.
3.  The Marathon Agent analyzes the failure (assertion error).
4.  It applies a fix to the code.
5.  The Verification Agent runs `pytest` in the sandbox.
6.  Tests pass, and Nightingale outputs a **RESOLVE** decision with high confidence.

## Safety Guarantees

-   **Sandboxing:** No changes are made to the actual repository without explicit approval or configuration.
-   **Confidence Scoring:** Low-confidence fixes represent valid hypotheses but are strictly escalated for human review.
