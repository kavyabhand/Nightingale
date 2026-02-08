import os
import time
from nightingale.types import IncidentEvent, IncidentType, PipelineStep
from nightingale.core.orchestrator import Orchestrator
from nightingale.config import config

def run_demo():
    print("=== Nightingale Demo: Broken CI/CD Pipeline ===\n")
    
    repo_path = os.path.abspath(config.get("demo.repo_path", "."))
    print(f"Target Repository: {repo_path}")
    
    # Simulate an event based on the broken repo
    # In a real run, this comes from a listener
    incident_event = IncidentEvent(
        id="demo-incident-001",
        type=IncidentType.TEST_FAILURE,
        repository_path=repo_path,
        commit_sha="HEAD",
        branch="main",
        failed_steps=[
             PipelineStep(
                 name="pytest", 
                 status="failure", 
                 logs="E   assert 0 == 1\nE    +  where 0 = subtract(2, 2)",
                 duration_ms=1200
             )
        ],
        metadata={"trigger": "push"}
    )
    
    print("\n[!] Detected CI Failure! Dispatching Nightingale Agent...")
    orchestrator = Orchestrator()
    orchestrator.process_incident(incident_event)

if __name__ == "__main__":
    run_demo()
