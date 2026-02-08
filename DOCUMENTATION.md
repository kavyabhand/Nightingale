# Nightingale System Documentation

## Architecture

### 1. Core Components

-   **`nightingale.types`**: Defines the domain model (`IncidentEvent`, `FixPlan`, `VerificationResult`).
-   **`nightingale.core.orchestrator`**: The central brain that coordinates agents and tools.
-   **`nightingale.core.sandbox`**: A safe execution environment that clones the repo and allows reversible changes.

### 2. Agents

#### Marathon Agent (Reasoning)
-   **Model:** Gemini 3 Pro
-   **Role:** Long-horizon reasoning. It reads the code, understands the error logs, and generates a multi-step `FixPlan`. It determines *why* something failed and *how* to fix it safely.
-   **Output:** A structured plan containing file diffs, verification commands, and a risk assessment.

#### Verification Agent (Execution)
-   **Model:** Gemini 3 Flash (Abstracted/Simulated)
-   **Role:** High-speed execution. It runs the commands specified in the plan within the sandbox.
-   **Output:** Pass/Fail signals and raw logs.

### 3. Analysis Modules

-   **Confidence Scorer**: Calculates a score $[0.0, 1.0]$ based on:
    -   Test pass/fail status.
    -   Complexity of the fix (lines of code changed).
    -   Consistency of the reasoning.
-   **Resolution Engine**: Compares confidence against a threshold ($0.85$) to decide between `RESOLVE` and `ESCALATE`.
-   **Escalation Reporter**: Formats the findings into a clear, actionable Markdown report for human engineers.

## orchestration Flow

1.  **Ingest**: `IncidentListener` receives a webhook or log event.
2.  **Context Load**: `RepositoryContextLoader` fetches the state of the repo at the failing commit.
3.  **Analyze**: `MarathonAgent` reviews the logs and code to generate a `FixPlan`.
4.  **Sandbox**: A temporary directory is created, and the repo is cloned.
5.  **Apply**: The fix (code changes) is applied to the sandbox.
6.  **Verify**: `VerificationAgent` runs the verification steps (e.g., `pytest`).
7.  **Score**: The result is scored for confidence.
8.  **Decide**: The system output its final decision and report.

## Future Work

-   Integration with GitHub Apps for real webhook handling.
-   Support for multi-modal inputs (screenshots of UI failures).
-   Fine-tuned models for specific codebases.
