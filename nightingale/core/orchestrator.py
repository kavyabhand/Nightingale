"""
Nightingale Orchestrator
Main pipeline controller with reflective reasoning
"""
import uuid
import time
import os
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
from nightingale.core.gemini_client import get_gemini_client, QuotaExhaustedError
from nightingale.agents.marathon import MarathonAgent, ReflectiveReasoningLoop
from nightingale.agents.verifier import VerificationAgent
from nightingale.analysis.confidence import ConfidenceScorer, ResolutionEngine
from nightingale.analysis.reporter import EscalationReporter
from nightingale.config import config


class Orchestrator:
    """
    Main pipeline orchestrator.

    Pipeline:
    1. Load Context
    2. Parse Workflows
    3. Reflective Loop (up to 3 Gemini-powered attempts)
    4. Score (weighted confidence)
    5. Decide (resolve or escalate)
    6. Report
    """

    def __init__(self):
        record_mode = os.getenv("NIGHTINGALE_RECORD_MODE") == "1"
        get_gemini_client(record_mode=record_mode)

        self.marathon = MarathonAgent()
        self.verifier = VerificationAgent()
        self.scorer = ConfidenceScorer()
        self.resolver = ResolutionEngine()
        self.reporter = EscalationReporter()
        self.metrics: Optional[MetricsData] = None

    def process_incident(self, event: IncidentEvent) -> IncidentReport:
        """Process a CI incident through the full pipeline."""
        start_time = time.time()

        self.metrics = MetricsData(
            incident_id=event.id,
            started_at=datetime.now()
        )

        logger.incident_start(event.id, event.type.value, event.repository_path)

        # 1. Load Context
        logger.info("Loading repository context...", incident_id=event.id, component="orchestrator")
        context_loader = RepositoryContextLoader(event.repository_path)

        try:
            all_files = context_loader.list_files()
            total_files = len(all_files)
            self.scorer = ConfidenceScorer(total_files)
        except Exception:
            total_files = 100

        # 2. Parse Workflows
        logger.info("Parsing workflows...", incident_id=event.id, component="orchestrator")
        workflow_parser = WorkflowParser(event.repository_path)
        test_commands = workflow_parser.get_test_commands()
        logger.info(f"Test commands: {test_commands}", incident_id=event.id, component="workflow")

        # 3. Reflective Reasoning Loop
        reasoning_loop = ReflectiveReasoningLoop(self.marathon)

        sandbox_id = f"sandbox_{event.id}_{uuid.uuid4().hex[:8]}"
        sandbox = Sandbox(event.repository_path, sandbox_id)

        final_plan: Optional[FixPlan] = None
        final_result: Optional[VerificationResult] = None
        attempts: list[AttemptRecord] = []

        def verify_callback(plan: FixPlan) -> VerificationResult:
            self.metrics.sandbox_runs += 1
            sandbox.setup()

            if test_commands:
                plan.verification_steps = test_commands

            sandbox.apply_diffs(plan.files_to_change)
            self.metrics.files_modified = len(plan.files_to_change)

            result = self.verifier.verify(sandbox, plan)
            logger.info(
                f"Verification took {result.duration_ms}ms",
                incident_id=event.id, component="verifier"
            )
            return result

        try:
            final_plan, attempts = reasoning_loop.run(event, context_loader, verify_callback)

            if final_plan and attempts:
                final_result = attempts[-1].verification_result

            self.metrics.total_attempts = len(attempts)

        except QuotaExhaustedError as e:
            logger.error(
                f"API quota exhausted — escalating: {e}",
                incident_id=event.id, component="orchestrator"
            )
            attempts = reasoning_loop.attempts if reasoning_loop else []
            self.metrics.total_attempts = len(attempts)

        except Exception as e:
            logger.error(
                f"Reasoning loop error — escalating: {e}",
                incident_id=event.id, component="orchestrator"
            )
            attempts = reasoning_loop.attempts if reasoning_loop else []
            self.metrics.total_attempts = len(attempts)

        finally:
            if config.get("cleanup_sandbox", True):
                sandbox.cleanup()

        # Collect Gemini metrics
        try:
            client = get_gemini_client()
            client_metrics = client.get_metrics()
            self.metrics.total_api_calls = client_metrics["total_calls"]
            self.metrics.total_tokens_used = client_metrics["total_tokens"]
        except Exception:
            pass

        # 4. Confidence
        if final_plan and final_result:
            confidence, factors = self.scorer.calculate(
                final_plan, final_result, final_plan.attempt_number
            )
        else:
            confidence = 0.0
            factors = ConfidenceFactors()

        logger.confidence_score(event.id, confidence, factors.model_dump())

        # 5. Decision
        decision = self.resolver.decide(confidence, factors)
        logger.decision(event.id, decision, confidence)

        # 6. Report
        self.metrics.total_duration_ms = int((time.time() - start_time) * 1000)
        self.metrics.completed_at = datetime.now()
        self.metrics.final_decision = DecisionType.RESOLVE if decision == "resolve" else DecisionType.ESCALATE
        self.metrics.final_confidence = confidence

        if decision == "resolve" and final_plan:
            logger.info("Decision is RESOLVE – applying fix to main repository...", incident_id=event.id, component="orchestrator")
            try:
                self._apply_fix_to_repo(event.repository_path, final_plan)
                logger.info("Fix applied to main repository successfully.", incident_id=event.id, component="orchestrator")
            except Exception as e:
                logger.error(f"Failed to apply fix to main repository: {e}", incident_id=event.id, component="orchestrator")

        if final_plan and final_result:
            report = self.reporter.generate_report(
                event=event, plan=final_plan, result=final_result,
                confidence=confidence, factors=factors, decision=decision,
                attempts=attempts, metrics=self.metrics
            )
        else:
            empty_plan = FixPlan(
                rationale="All fix attempts failed or API quota exhausted",
                root_cause="Unable to determine — escalated to human",
                files_to_change=[], verification_steps=[],
                confidence_score=0.0
            )
            empty_result = VerificationResult(
                success=False, input_hash="",
                output_log="Escalated due to exhausted attempts or API quota", duration_ms=0
            )
            report = self.reporter.generate_report(
                event=event, plan=empty_plan, result=empty_result,
                confidence=0.0, factors=ConfidenceFactors(), decision="escalate",
                attempts=attempts, metrics=self.metrics
            )

        # Display metrics
        logger.metrics_summary({
            "attempts": self.metrics.total_attempts,
            "api_calls": self.metrics.total_api_calls,
            "tokens_used": self.metrics.total_tokens_used,
            "duration_ms": self.metrics.total_duration_ms,
            "files_modified": self.metrics.files_modified,
            "sandbox_runs": self.metrics.sandbox_runs,
        })

        print("\n" + report.report_text)
        return report

    def _apply_fix_to_repo(self, repo_path: str, plan: FixPlan):
        """Apply the fix directly to the repository."""
        for diff in plan.files_to_change:
            file_path = os.path.join(repo_path, diff.file_path)
            
            if diff.change_type == "modify" or diff.change_type == "add":
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(diff.diff_content)
            elif diff.change_type == "delete":
                if os.path.exists(file_path):
                    os.remove(file_path)
