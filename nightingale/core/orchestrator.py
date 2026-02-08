import logging
import uuid
import time
from nightingale.types import IncidentEvent, FixPlan, VerificationResult
from nightingale.core.listener import IncidentListener
from nightingale.core.context import RepositoryContextLoader
from nightingale.core.sandbox import Sandbox
from nightingale.agents.marathon import MarathonAgent
from nightingale.agents.verifier import VerificationAgent
from nightingale.analysis.confidence import ConfidenceScorer
from nightingale.analysis.resolution import ResolutionEngine
from nightingale.analysis.reporter import EscalationReporter
from nightingale.config import config

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self):
        self.listener = IncidentListener()
        self.marathon = MarathonAgent()
        self.verifier = VerificationAgent()
        self.scorer = ConfidenceScorer()
        self.resolver = ResolutionEngine()
        self.reporter = EscalationReporter()

    def process_incident(self, event: IncidentEvent):
        logger.info(f"Processing incident {event.id}")

        # 1. Load Context
        logger.info("Loading repository context...")
        context_loader = RepositoryContextLoader(event.repository_path)
        
        # 2. Reason & Plan (Marathon)
        logger.info("Analyzing incident with Marathon Agent...")
        plan = self.marathon.analyze(event, context_loader)
        logger.info(f"Plan generated: {plan.rationale}")

        # 3. Sandbox Setup
        sandbox_id = f"sandbox_{event.id}_{uuid.uuid4().hex[:8]}"
        sandbox = Sandbox(event.repository_path, sandbox_id)
        
        try:
            logger.info(f"Setting up sandbox: {sandbox_id}")
            sandbox.setup()
            
            # 4. Apply Fix
            logger.info("Applying fix to sandbox...")
            sandbox.apply_diffs(plan.files_to_change)
            
            # 5. Verify (Verifier)
            logger.info("Verifying fix...")
            result = self.verifier.verify(sandbox, plan)
            logger.info(f"Verification success: {result.success}")
            
            # 6. Score
            confidence = self.scorer.calculate(plan, result)
            logger.info(f"Confidence score: {confidence}")
            
            # 7. Decide
            decision = self.resolver.decide(confidence)
            logger.info(f"Decision: {decision}")
            
            # 8. Report
            report = self.reporter.generate_report(event, plan, result, confidence, decision)
            print(report) # Output for demo/cli
            
            return {
                "id": event.id,
                "decision": decision,
                "confidence": confidence,
                "report": report
            }
            
        finally:
            logger.info("Cleaning up sandbox...")
            # sandbox.cleanup() # Keep for inspection in demo? Maybe flag controlled.
            if config.get("cleanup_sandbox", True):
                 sandbox.cleanup()

    def run(self):
        """Main loop."""
        # For demo, we might just process one event or listen
        # event = self.listener.listen()
        # if event:
        #     self.process_incident(event)
        pass
