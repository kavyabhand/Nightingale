"""
Nightingale Demo Scenario
Runs the full autonomous agent on a simulated CI failure
"""
import os
import time
from datetime import datetime

from nightingale.types import IncidentEvent, IncidentType, PipelineStep
from nightingale.core.orchestrator import Orchestrator
from nightingale.core.logger import logger, console
from nightingale.config import config


def run_demo(record_mode: bool = False):
    """Run the demo scenario with a broken test."""

    console.print("""
[bold cyan]
    NIGHTINGALE
    Autonomous CI SRE Agent
    Powered by Gemini 3
[/bold cyan]
    """)

    repo_path = os.path.abspath(config.get("demo.repo_path", "."))
    console.print(f"[dim]Target Repository: {repo_path}[/dim]")
    if record_mode:
        console.print("[bold yellow][record-mode] Replaying cached API responses[/bold yellow]")
    console.print()

    incident_event = IncidentEvent(
        id=f"demo-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        type=IncidentType.TEST_FAILURE,
        timestamp=datetime.now(),
        repository_path=repo_path,
        commit_sha="HEAD",
        branch="main",
        failed_steps=[
            PipelineStep(
                name="pytest",
                status="failure",
                logs="""
============================= test session starts ==============================
platform linux -- Python 3.10.0, pytest-7.0.0
collected 2 items

demo_repo/test_app.py .F                                                  [100%]

=================================== FAILURES ===================================
________________________________ test_subtract _________________________________

    def test_subtract():
        # This test is intentionally broken
>       assert subtract(2, 2) == 1
E       AssertionError: assert 0 == 1
E        +  where 0 = subtract(2, 2)

demo_repo/test_app.py:12: AssertionError
=========================== short test summary info ============================
FAILED demo_repo/test_app.py::test_subtract - AssertionError: assert 0 == 1
========================= 1 failed, 1 passed in 0.12s =========================
""",
                duration_ms=120
            )
        ],
        metadata={"trigger": "demo", "source": "manual"}
    )

    console.print("[bold red]CI FAILURE DETECTED[/bold red]")
    console.print("[dim]Dispatching Nightingale Agent...[/dim]\n")

    time.sleep(0.3)

    orchestrator = Orchestrator()
    report = orchestrator.process_incident(incident_event)

    console.print("\n[bold green]Demo Complete[/bold green]")

    if report.decision.value == "resolve":
        console.print("[green]The agent successfully resolved the issue.[/green]")
    else:
        console.print("[yellow]The agent escalated the issue for human review.[/yellow]")

    return report


if __name__ == "__main__":
    run_demo()
