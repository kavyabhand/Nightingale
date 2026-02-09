# Nightingale Architecture

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NIGHTINGALE ARCHITECTURE                           │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │  GitHub Actions │
                              │  CI/CD Pipeline │
                              └────────┬────────┘
                                       │ webhook (failure)
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  API LAYER                                                                    │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │  FastAPI Webhook Server (/webhook/github)                              │  │
│  │  - Signature verification                                               │  │
│  │  - Event parsing (workflow_run, check_run)                             │  │
│  │  - Background task queuing                                              │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼ IncidentEvent
┌──────────────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR                                                                 │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │  1. Context Loading     → RepositoryContextLoader (git)                │  │
│  │  2. Workflow Parsing    → WorkflowParser (dynamic test cmds)           │  │
│  │  3. Reflective Loop     → MarathonAgent + VerificationAgent            │  │
│  │  4. Confidence Scoring  → ConfidenceScorer (weighted formula)          │  │
│  │  5. Decision Engine     → ResolutionEngine (resolve/escalate)          │  │
│  │  6. Report Generation   → EscalationReporter                           │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          ▼                            ▼                            ▼
┌─────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────┐
│  MARATHON AGENT     │  │  VERIFICATION AGENT     │  │  GEMINI CLIENT      │
│                     │  │                         │  │                     │
│  • Multi-attempt    │  │  • Sandbox execution    │  │  • Rate limiting    │
│  • Reflective loop  │  │  • Test output parsing  │  │  • Retry w/ backoff │
│  • Context building │  │  • Pass/fail counting   │  │  • JSON validation  │
│  • Prompt crafting  │  │                         │  │  • Pydantic models  │
└─────────────────────┘  └─────────────────────────┘  └─────────────────────┘
          │                            │                            │
          └────────────────────────────┼────────────────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────┐
                    │           SANDBOX                 │
                    │  ┌────────────────────────────┐  │
                    │  │  Isolated copy of repo     │  │
                    │  │  - Apply diffs             │  │
                    │  │  - Run tests               │  │
                    │  │  - Capture output          │  │
                    │  └────────────────────────────┘  │
                    └──────────────────────────────────┘
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          ▼                            ▼                            ▼
┌─────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────┐
│  BLAST RADIUS       │  │  CONFIDENCE SCORER      │  │  RESOLUTION ENGINE  │
│  ANALYZER           │  │                         │  │                     │
│  • File count ratio │  │  Weighted formula:      │  │  Threshold: 85%     │
│  • Risk levels      │  │  35% test_pass_ratio    │  │                     │
│  • File criticality │  │  25% blast_radius       │  │  ≥85% → RESOLVE     │
│                     │  │  15% attempt_penalty    │  │  <85% → ESCALATE    │
│                     │  │  15% risk_modifier      │  │                     │
│                     │  │  10% self_consistency   │  │                     │
└─────────────────────┘  └─────────────────────────┘  └─────────────────────┘

```

## Component Descriptions

### API Layer
- **FastAPI Server**: Receives GitHub webhooks, validates signatures, queues incidents

### Core Pipeline
- **Orchestrator**: Main controller coordinating all components
- **RepositoryContextLoader**: Git integration for file access
- **WorkflowParser**: Extracts test commands from `.github/workflows/`

### Agents
- **MarathonAgent**: Gemini-powered reasoning with 3-attempt reflective loop
- **VerificationAgent**: Runs tests and parses results

### Analysis
- **BlastRadiusAnalyzer**: Calculates change impact
- **ConfidenceScorer**: Weighted multi-factor scoring
- **ResolutionEngine**: Resolve vs escalate decision

### Infrastructure
- **GeminiClient**: API client with retries and validation
- **Sandbox**: Isolated test environment
- **Logger**: Structured logging with Rich console output

## Data Flow

```
Incident → Parse → Context → [Analyze → Fix → Test]×3 → Score → Decide → Report
                              └─── Reflective Loop ───┘
```
