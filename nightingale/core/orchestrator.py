"""
Nightingale Orchestrator
Main pipeline controller with reflective reasoning
"""
import uuid
import time
from datetime import datetime
from typing import Optional, Dict, Any

from nightingale.types import (
    IncidentEvent, FixPlan, VerificationResult, MetricsData,
    ConfidenceFactors, AttemptRecord, IncidentReport, DecisionType
)
from nightingale.core.context import RepositoryContextLoader
from nightingale.core.sandbox import Sandbox
from nightingale.core.workflow_parser import WorkflowParser
from nightingale.core.logger import logger
from nightingale.core.gemini_client import get_gemini_client
from nightingale.agents.marathon import MarathonAgent, ReflectiveReasoningLoop
from nightingale.agents.verifier import VerificationAgent
from nightingale.analysis.confidence import ConfidenceScorer, ResolutionEngine
from nightingale.analysis.reporter import EscalationReporter
from nightingale.config import config


class Orchestrator:
    """
    Main pipeline orchestrator with reflective reasoning loop.
    
    Pipeline:
    1. Load Context → Parse repo and workflows
    2. Reflective Loop → Up to 3 fix attempts
    3. Score → Weighted confidence calculation
    4. Decide → Resolve or escalate
    5. Report → Comprehensive incident report
    """
    
    def __init__(self):
        self.marathon = MarathonAgent()
        self.verifier = VerificationAgent()
        self.scorer = ConfidenceScorer()
        self.resolver = ResolutionEngine()
        self.reporter = EscalationReporter()
        
        # Metrics
        self.metrics: Optional[MetricsData] = None
    
    def process_incident(self, event: IncidentEvent) -> IncidentReport:
        """
        Process an incident through the full pipeline.
        
        Args:
            event: Incident to process
            
        Returns:
            IncidentReport with results
        """
        start_time = time.time()
        
        # Initialize metrics
        self.metrics = MetricsData(
            incident_id=event.id,
            started_at=datetime.now()
        )
        
        logger.incident_start(event.id, event.type.value, event.repository_path)
        
        # 1. Load Context
        logger.info("Loading repository context...", incident_id=event.id, component="orchestrator")
        context_loader = RepositoryContextLoader(event.repository_path)
        
        # Get file count for blast radius calculation
        try:
            all_files = context_loader.list_files()
            total_files = len(all_files)
            self.scorer = ConfidenceScorer(total_files)
        except Exception:
            total_files = 100  # Default
        
        # 2. Parse workflows for test commands
        logger.info("Parsing GitHub Actions workflows...", incident_id=event.id, component="orchestrator")
        workflow_parser = WorkflowParser(event.repository_path)
        test_commands = workflow_parser.get_test_commands()
        logger.info(f"Found test commands: {test_commands}", incident_id=event.id, component="workflow")
        
        # 3. Run reflective reasoning loop
        reasoning_loop = ReflectiveReasoningLoop(self.marathon)
        
        # Create sandbox once
        sandbox_id = f"sandbox_{event.id}_{uuid.uuid4().hex[:8]}"
        sandbox = Sandbox(event.repository_path, sandbox_id)
        
        final_plan: Optional[FixPlan] = None
        final_result: Optional[VerificationResult] = None
        attempts: list[AttemptRecord] = []
        
        def verify_callback(plan: FixPlan) -> VerificationResult:
            """Callback for verification in the loop."""
            self.metrics.sandbox_runs += 1
            
            # Setup fresh sandbox
            sandbox.setup()
            
            # Override verification steps with dynamic commands
            if test_commands:
                plan.verification_steps = test_commands
            
            # Apply the fix
            sandbox.apply_diffs(plan.files_to_change)
            self.metrics.files_modified = len(plan.files_to_change)
            
            # Run verification
            return self.verifier.verify(sandbox, plan)
        
        try:
            final_plan, attempts = reasoning_loop.run(event, context_loader, verify_callback)
            
            if final_plan and attempts:
                final_result = attempts[-1].verification_result
            
            self.metrics.total_attempts = len(attempts)
            
        finally:
            # Cleanup sandbox
            if config.get("cleanup_sandbox", True):
                sandbox.cleanup()
        
        # Get Gemini client metrics
        try:
            client = get_gemini_client()
            client_metrics = client.get_metrics()
            self.metrics.total_api_calls = client_metrics["total_calls"]
            self.metrics.total_tokens_used = client_metrics["total_tokens"]
        except Exception:
            pass
        
        # 4. Calculate confidence
        if final_plan and final_result:
            confidence, factors = self.scorer.calculate(
                final_plan,
                final_result,
                final_plan.attempt_number
            )
        else:
            confidence = 0.0
            factors = ConfidenceFactors()
        
        logger.confidence_score(event.id, confidence, factors.model_dump())
        
        # 5. Make decision
        decision = self.resolver.decide(confidence, factors)
        logger.decision(event.id, decision, confidence)
        
        # 6. Generate report
        self.metrics.total_duration_ms = int((time.time() - start_time) * 1000)
        self.metrics.completed_at = datetime.now()
        self.metrics.final_decision = DecisionType.RESOLVE if decision == "resolve" else DecisionType.ESCALATE
        self.metrics.final_confidence = confidence
        
        if final_plan and final_result:
            report = self.reporter.generate_report(
                event=event,
                plan=final_plan,
                result=final_result,
                confidence=confidence,
                factors=factors,
                decision=decision,
                attempts=attempts,
                metrics=self.metrics
            )
        else:
            # All attempts failed
            empty_plan = FixPlan(
                rationale="All fix attempts failed",
                root_cause="Unable to determine",
                files_to_change=[],
                verification_steps=[],
                confidence_score=0.0
            )
            empty_result = VerificationResult(
                success=False,
                input_hash="",
                output_log="All attempts exhausted",
                duration_ms=0
            )
            report = self.reporter.generate_report(
                event=event,
                plan=empty_plan,
                result=empty_result,
                confidence=0.0,
                factors=ConfidenceFactors(),
                decision="escalate",
                attempts=attempts,
                metrics=self.metrics
            )
        
        # Display metrics
        logger.metrics_summary({
            "attempts": self.metrics.total_attempts,
            "api_calls": self.metrics.total_api_calls,
            "tokens": self.metrics.total_tokens_used,
            "duration_ms": self.metrics.total_duration_ms
        })
        
        print("\n" + report.report_text)
        
        return report
    
    def run(self):
        """Main loop placeholder for webhook mode."""
        pass
