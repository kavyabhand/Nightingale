"""
Nightingale FastAPI Webhook API
GitHub Actions CI event listener
"""
import hmac
import hashlib
import asyncio
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from nightingale.types import IncidentEvent, IncidentType, PipelineStep
from nightingale.core.orchestrator import Orchestrator
from nightingale.core.logger import logger
from nightingale.config import config


# FastAPI app
app = FastAPI(
    title="Nightingale CI Webhook",
    description="Autonomous CI/CD repair agent webhook listener",
    version="0.1.0"
)


class WebhookResponse(BaseModel):
    """Standard webhook response."""
    status: str
    message: str
    incident_id: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    timestamp: str


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify GitHub webhook signature.
    
    Args:
        payload: Raw request body
        signature: X-Hub-Signature-256 header
        secret: Webhook secret
        
    Returns:
        True if valid
    """
    if not signature or not secret:
        return True  # Skip if not configured
    
    expected = "sha256=" + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)


def parse_github_workflow_event(payload: dict) -> Optional[IncidentEvent]:
    """
    Parse GitHub workflow_run event into IncidentEvent.
    
    Args:
        payload: GitHub webhook payload
        
    Returns:
        IncidentEvent or None if not a failure
    """
    workflow_run = payload.get("workflow_run", {})
    
    # Only process failures
    conclusion = workflow_run.get("conclusion")
    if conclusion != "failure":
        return None
    
    repository = payload.get("repository", {})
    
    # Extract logs URL (would need GitHub API to fetch actual logs)
    logs_url = workflow_run.get("logs_url", "")
    
    event = IncidentEvent(
        id=f"gh-{workflow_run.get('id', 'unknown')}",
        type=IncidentType.PIPELINE_FAILURE,
        timestamp=datetime.now(),
        repository_path=repository.get("full_name", ""),
        commit_sha=workflow_run.get("head_sha", "HEAD"),
        branch=workflow_run.get("head_branch", "main"),
        failed_steps=[
            PipelineStep(
                name=workflow_run.get("name", "unknown"),
                status="failure",
                logs=f"Workflow failed. Logs: {logs_url}",
                duration_ms=None
            )
        ],
        metadata={
            "source": "github_webhook",
            "workflow_name": workflow_run.get("name"),
            "run_number": workflow_run.get("run_number"),
            "actor": workflow_run.get("actor", {}).get("login"),
            "logs_url": logs_url
        },
        workflow_file=workflow_run.get("path")
    )
    
    return event


def parse_github_check_run_event(payload: dict) -> Optional[IncidentEvent]:
    """
    Parse GitHub check_run event into IncidentEvent.
    
    Args:
        payload: GitHub webhook payload
        
    Returns:
        IncidentEvent or None if not a failure
    """
    check_run = payload.get("check_run", {})
    
    # Only process failures
    conclusion = check_run.get("conclusion")
    if conclusion not in ["failure", "timed_out"]:
        return None
    
    repository = payload.get("repository", {})
    
    event = IncidentEvent(
        id=f"gh-check-{check_run.get('id', 'unknown')}",
        type=IncidentType.TEST_FAILURE,
        timestamp=datetime.now(),
        repository_path=repository.get("full_name", ""),
        commit_sha=check_run.get("head_sha", "HEAD"),
        branch=check_run.get("check_suite", {}).get("head_branch", "main"),
        failed_steps=[
            PipelineStep(
                name=check_run.get("name", "unknown"),
                status="failure",
                logs=check_run.get("output", {}).get("text", "Check run failed"),
                duration_ms=None
            )
        ],
        metadata={
            "source": "github_webhook",
            "check_name": check_run.get("name"),
            "conclusion": conclusion
        }
    )
    
    return event


async def process_incident_async(event: IncidentEvent):
    """
    Process incident in background.
    
    Args:
        event: Incident to process
    """
    try:
        orchestrator = Orchestrator()
        # Run synchronously in thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, orchestrator.process_incident, event)
    except Exception as e:
        logger.error(f"Background incident processing failed: {e}", incident_id=event.id)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        timestamp=datetime.now().isoformat()
    )


@app.post("/webhook/github", response_model=WebhookResponse)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None)
):
    """
    GitHub webhook endpoint.
    
    Handles:
    - workflow_run events (CI pipeline failures)
    - check_run events (check suite failures)
    """
    # Get raw body for signature verification
    body = await request.body()
    
    # Verify signature if secret is configured
    webhook_secret = config.get("webhook.secret", "")
    if webhook_secret:
        if not verify_github_signature(body, x_hub_signature_256 or "", webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse payload
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Handle different event types
    event: Optional[IncidentEvent] = None
    
    if x_github_event == "workflow_run":
        event = parse_github_workflow_event(payload)
    elif x_github_event == "check_run":
        event = parse_github_check_run_event(payload)
    elif x_github_event == "ping":
        return WebhookResponse(
            status="ok",
            message="Pong! Webhook is configured correctly."
        )
    else:
        return WebhookResponse(
            status="ignored",
            message=f"Event type '{x_github_event}' not handled"
        )
    
    if not event:
        return WebhookResponse(
            status="ignored",
            message="Event was not a failure, skipping"
        )
    
    # Queue for background processing
    logger.info(f"Received incident from GitHub: {event.id}", incident_id=event.id)
    background_tasks.add_task(process_incident_async, event)
    
    return WebhookResponse(
        status="accepted",
        message="Incident queued for processing",
        incident_id=event.id
    )


@app.post("/incident", response_model=WebhookResponse)
async def submit_incident(
    incident: IncidentEvent,
    background_tasks: BackgroundTasks
):
    """
    Direct incident submission endpoint.
    
    Accepts an IncidentEvent directly for testing or integration.
    """
    logger.info(f"Received direct incident: {incident.id}", incident_id=incident.id)
    background_tasks.add_task(process_incident_async, incident)
    
    return WebhookResponse(
        status="accepted",
        message="Incident queued for processing",
        incident_id=incident.id
    )


def run_webhook_server(host: str = "0.0.0.0", port: int = 8000):
    """
    Run the webhook server.
    
    Args:
        host: Host to bind to
        port: Port to listen on
    """
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_webhook_server()
