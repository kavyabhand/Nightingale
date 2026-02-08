from nightingale.types import IncidentEvent, FixPlan, VerificationResult

class EscalationReporter:
    def generate_report(self, event: IncidentEvent, plan: FixPlan, result: VerificationResult, score: float, decision: str) -> str:
        return f"""
# Nightingale Incident Report

**Status**: {decision.upper()}
**Confidence**: {score:.2f}

## Incident Details
- **ID**: {event.id}
- **Type**: {event.type}
- **Repo**: {event.repository_path}

## Diagnosis & Plan
**Rationale**: {plan.rationale}

## Verification
**Success**: {result.success}
**Logs**:
```
{result.output_log[-500:]} # Last 500 chars
```
"""
