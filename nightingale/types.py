from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

class IncidentType(str, Enum):
    PIPELINE_FAILURE = "pipeline_failure"
    TEST_FAILURE = "test_failure"
    LINT_FAILURE = "lint_failure"
    BUILD_FAILURE = "build_failure"

class PipelineStep(BaseModel):
    name: str
    status: str
    logs: Optional[str] = None
    duration_ms: Optional[int] = None

class IncidentEvent(BaseModel):
    id: str
    type: IncidentType
    timestamp: datetime = Field(default_factory=datetime.now)
    repository_path: str
    commit_sha: str
    branch: str
    failed_steps: List[PipelineStep]
    metadata: Dict[str, Any] = Field(default_factory=dict)

class FileDiff(BaseModel):
    file_path: str
    change_type: str  # "modify", "add", "delete"
    diff_content: str

class VerificationResult(BaseModel):
    success: bool
    input_hash: str
    output_log: str
    duration_ms: int

class FixPlan(BaseModel):
    rationale: str
    files_to_change: List[FileDiff]
    verification_steps: List[str]
    confidence_score: float = 0.0
    risk_level: str  # "low", "medium", "high"
