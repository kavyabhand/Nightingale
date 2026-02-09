"""
Nightingale Marathon Agent
Multi-attempt reflective reasoning with Gemini 3
"""
import time
from typing import Optional, List, Dict, Any
from datetime import datetime

from nightingale.types import (
    IncidentEvent, FixPlan, FileDiff, RiskLevel,
    GeminiFixResponse, ReasoningTrace, AttemptRecord, VerificationResult
)
from nightingale.core.context import RepositoryContextLoader
from nightingale.core.gemini_client import get_gemini_client, GeminiClientError
from nightingale.core.logger import logger
from nightingale.config import config


class MarathonAgent:
    """
    Multi-attempt reflective reasoning agent using Gemini 3.
    
    Features:
    - Max 3 fix attempts
    - Feeds failure logs back for root cause revision
    - Tracks full reasoning trace
    - No simulation fallbacks - real API only
    """
    
    MAX_ATTEMPTS = 3
    
    def __init__(self):
        self.client = get_gemini_client()
        self.current_trace: Optional[ReasoningTrace] = None
    
    def analyze(
        self,
        event: IncidentEvent,
        context_loader: RepositoryContextLoader,
        attempt_number: int = 1,
        previous_failure: Optional[str] = None,
        previous_plan: Optional[FixPlan] = None
    ) -> FixPlan:
        """
        Analyze incident and generate fix plan using Gemini.
        
        Args:
            event: The incident to analyze
            context_loader: Repository context loader
            attempt_number: Current attempt number (1-3)
            previous_failure: Logs from previous failed attempt
            previous_plan: The plan that failed (for reflection)
            
        Returns:
            FixPlan with proposed changes
        """
        start_time = time.time()
        
        # Initialize reasoning trace
        self.current_trace = ReasoningTrace(
            incident_id=event.id,
            attempt_number=attempt_number
        )
        
        logger.attempt_start(event.id, attempt_number, self.MAX_ATTEMPTS)
        
        # Step 1: Gather context
        logger.reasoning_step(event.id, attempt_number, "Gathering repository context")
        context = self._gather_context(event, context_loader)
        
        # Step 2: Build prompt
        logger.reasoning_step(event.id, attempt_number, "Constructing analysis prompt")
        prompt = self._build_prompt(event, context, attempt_number, previous_failure, previous_plan)
        
        # Step 3: Call Gemini for structured response
        logger.reasoning_step(event.id, attempt_number, "Calling Gemini for analysis")
        try:
            response = self.client.generate_structured(
                prompt=prompt,
                response_model=GeminiFixResponse,
                model="pro",
                incident_id=event.id
            )
        except GeminiClientError as e:
            logger.error(f"Gemini API failed: {e}", incident_id=event.id)
            raise
        
        # Step 4: Convert to FixPlan
        logger.reasoning_step(event.id, attempt_number, "Building fix plan")
        fix_plan = self._response_to_plan(response, event, attempt_number, previous_failure)
        
        # Log the plan
        logger.show_fix_plan(fix_plan.rationale, fix_plan.files_to_change)
        
        # Update trace
        duration_ms = int((time.time() - start_time) * 1000)
        self.current_trace.total_duration_ms = duration_ms
        self.current_trace.completed_at = datetime.now()
        
        return fix_plan
    
    def _gather_context(
        self,
        event: IncidentEvent,
        context_loader: RepositoryContextLoader
    ) -> Dict[str, Any]:
        """Gather relevant repository context."""
        context = {
            "files": [],
            "recent_commits": [],
            "failed_file_content": None
        }
        
        # List files in repo
        try:
            all_files = context_loader.list_files()
            # Prioritize Python files and test files
            priority_files = [f for f in all_files if f.endswith('.py')]
            context["files"] = priority_files[:20]  # Limit for context window
        except Exception as e:
            logger.warning(f"Could not list files: {e}")
        
        # Get recent commits
        try:
            context["recent_commits"] = context_loader.get_recent_commits(3)
        except Exception as e:
            logger.warning(f"Could not get commits: {e}")
        
        # Try to get content of likely failing file
        if event.failed_steps:
            # Parse logs to find failing file
            logs = event.failed_steps[-1].logs or ""
            for f in context.get("files", []):
                if f in logs:
                    try:
                        content = context_loader.get_file_content(f)
                        context["failed_file_content"] = {
                            "path": f,
                            "content": content[:3000]  # Limit size
                        }
                        break
                    except Exception:
                        pass
        
        return context
    
    def _build_prompt(
        self,
        event: IncidentEvent,
        context: Dict[str, Any],
        attempt_number: int,
        previous_failure: Optional[str],
        previous_plan: Optional[FixPlan]
    ) -> str:
        """Build the analysis prompt for Gemini."""
        
        # Base prompt
        prompt = f"""You are an expert SRE and software engineer. Analyze the following CI/CD failure and provide a fix.

## Incident Details
- **ID**: {event.id}
- **Type**: {event.type.value}
- **Repository**: {event.repository_path}
- **Branch**: {event.branch}
- **Commit**: {event.commit_sha}

## Failed Step
"""
        
        if event.failed_steps:
            step = event.failed_steps[-1]
            prompt += f"""- **Step Name**: {step.name}
- **Status**: {step.status}
- **Logs**:
```
{step.logs or 'No logs available'}
```
"""
        
        # Add file context
        prompt += f"""
## Repository Files
{', '.join(context.get('files', [])[:15])}

"""
        
        # Add failing file content if available
        if context.get("failed_file_content"):
            fc = context["failed_file_content"]
            prompt += f"""## Relevant File Content
**{fc['path']}**:
```python
{fc['content']}
```

"""
        
        # Add reflection context for retries
        if attempt_number > 1 and previous_failure and previous_plan:
            prompt += f"""
## CRITICAL: Previous Attempt Failed
This is attempt {attempt_number}/{self.MAX_ATTEMPTS}. Your previous fix did NOT work.

**Previous Rationale**: {previous_plan.rationale}
**Previous Root Cause Analysis**: {previous_plan.root_cause}

**Verification Failure Logs**:
```
{previous_failure[-2000:]}
```

You MUST:
1. Re-analyze the root cause - your previous analysis was incorrect or incomplete
2. Propose a DIFFERENT fix approach
3. Be more careful about the exact error in the logs
"""
        
        prompt += """
## Your Task
1. Identify the ROOT CAUSE of the failure
2. Propose a MINIMAL fix that resolves the issue
3. Specify exact file changes needed
4. Provide verification commands

Be precise and conservative. Only change what's necessary."""
        
        return prompt
    
    def _response_to_plan(
        self,
        response: GeminiFixResponse,
        event: IncidentEvent,
        attempt_number: int,
        previous_failure: Optional[str]
    ) -> FixPlan:
        """Convert Gemini response to FixPlan."""
        
        # Convert file changes
        files_to_change = []
        for f in response.files_to_change:
            files_to_change.append(FileDiff(
                file_path=f["file_path"],
                change_type=f["change_type"],
                diff_content=f["content"]
            ))
        
        # Map risk level
        risk_map = {
            "low": RiskLevel.LOW,
            "medium": RiskLevel.MEDIUM,
            "high": RiskLevel.HIGH,
            "critical": RiskLevel.CRITICAL
        }
        risk = risk_map.get(response.risk_assessment.lower(), RiskLevel.MEDIUM)
        
        return FixPlan(
            rationale=response.rationale,
            root_cause=response.root_cause,
            files_to_change=files_to_change,
            verification_steps=response.verification_commands,
            confidence_score=response.confidence,
            risk_level=risk,
            attempt_number=attempt_number,
            previous_failure_context=previous_failure
        )
    
    def get_trace(self) -> Optional[ReasoningTrace]:
        """Get the current reasoning trace."""
        return self.current_trace


class ReflectiveReasoningLoop:
    """
    Orchestrates multi-attempt reasoning with reflection.
    """
    
    def __init__(self, agent: MarathonAgent):
        self.agent = agent
        self.attempts: List[AttemptRecord] = []
    
    def run(
        self,
        event: IncidentEvent,
        context_loader: RepositoryContextLoader,
        verify_callback
    ) -> tuple[Optional[FixPlan], List[AttemptRecord]]:
        """
        Run the reflective reasoning loop.
        
        Args:
            event: Incident to fix
            context_loader: Repository context
            verify_callback: Function(sandbox, plan) -> VerificationResult
            
        Returns:
            (successful_plan, all_attempts) or (None, all_attempts) if all failed
        """
        previous_failure = None
        previous_plan = None
        
        for attempt_num in range(1, self.agent.MAX_ATTEMPTS + 1):
            record = AttemptRecord(
                attempt_number=attempt_num,
                started_at=datetime.now()
            )
            
            try:
                # Generate fix plan
                plan = self.agent.analyze(
                    event=event,
                    context_loader=context_loader,
                    attempt_number=attempt_num,
                    previous_failure=previous_failure,
                    previous_plan=previous_plan
                )
                record.fix_plan = plan
                record.reasoning_trace = self.agent.get_trace()
                
                # Verify the fix
                result = verify_callback(plan)
                record.verification_result = result
                record.completed_at = datetime.now()
                
                if result.success:
                    self.attempts.append(record)
                    return plan, self.attempts
                else:
                    # Prepare for next attempt
                    previous_failure = result.output_log
                    previous_plan = plan
                    record.failure_reason = "Verification failed"
                    
            except Exception as e:
                record.failure_reason = str(e)
                record.completed_at = datetime.now()
                previous_failure = str(e)
            
            self.attempts.append(record)
        
        # All attempts exhausted
        return None, self.attempts
