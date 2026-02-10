"""
Nightingale Data Types
Production-grade Pydantic models with JSON schema validation
"""
from typing import List, Dict, Optional, Any, Literal
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from datetime import datetime
import hashlib
import json

# === Enums ===

class IncidentType(str, Enum):
    PIPELINE_FAILURE = "pipeline_failure"
    TEST_FAILURE = "test_failure"
    LINT_FAILURE = "lint_failure"
    BUILD_FAILURE = "build_failure"

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class DecisionType(str, Enum):
    RESOLVE = "resolve"
    ESCALATE = "escalate"
    ABORT = "abort"

# === Core Models ===

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
    workflow_file: Optional[str] = None

class FileDiff(BaseModel):
    file_path: str
    change_type: Literal["modify", "add", "delete"]
    diff_content: str
    
    def content_hash(self) -> str:
        return hashlib.sha256(self.diff_content.encode()).hexdigest()[:16]

# === Gemini Response Schema ===

class GeminiFixResponse(BaseModel):
    """Schema for validated Gemini API responses."""
    root_cause: str = Field(..., description="Root cause analysis")
    rationale: str = Field(..., description="Explanation of the fix approach")
    files_to_change: List[Dict[str, str]] = Field(..., description="List of file changes")
    verification_commands: List[str] = Field(..., description="Commands to verify fix")
    confidence: float = Field(ge=0.0, le=1.0, description="Self-assessed confidence")
    risk_assessment: str = Field(..., description="Risk level assessment")
    
    @field_validator('files_to_change')
    @classmethod
    def validate_files(cls, v):
        normalized = []
        for f in v:
            entry = dict(f)
            # Normalize field names from Gemini variation
            if 'file' in entry and 'file_path' not in entry:
                entry['file_path'] = entry.pop('file')
            if 'path' in entry and 'file_path' not in entry:
                entry['file_path'] = entry.pop('path')
            if 'type' in entry and 'change_type' not in entry:
                entry['change_type'] = entry.pop('type')
            if 'action' in entry and 'change_type' not in entry:
                entry['change_type'] = entry.pop('action')
            for alt in ['changes', 'patch', 'diff', 'code']:
                if alt in entry and 'content' not in entry:
                    entry['content'] = entry.pop(alt)
            # Normalize change_type values
            type_map = {'create': 'add', 'update': 'modify', 'remove': 'delete', 'edit': 'modify'}
            if 'change_type' in entry:
                entry['change_type'] = type_map.get(entry['change_type'], entry['change_type'])
            # Validate required fields
            if 'file_path' not in entry or 'change_type' not in entry or 'content' not in entry:
                raise ValueError("Each file must have file_path, change_type, and content")
            if entry['change_type'] not in ['modify', 'add', 'delete']:
                raise ValueError(f"Invalid change_type: {entry['change_type']}")
            normalized.append(entry)
        return normalized

# === Reasoning Trace ===

class ReasoningStep(BaseModel):
    """Single step in reasoning trace."""
    step_number: int
    action: str
    input_summary: str
    output_summary: str
    timestamp: datetime = Field(default_factory=datetime.now)
    duration_ms: int = 0
    tokens_used: int = 0

class ReasoningTrace(BaseModel):
    """Complete trace of agent reasoning."""
    incident_id: str
    attempt_number: int
    steps: List[ReasoningStep] = Field(default_factory=list)
    total_tokens: int = 0
    total_duration_ms: int = 0
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    def add_step(self, action: str, input_summary: str, output_summary: str, 
                 duration_ms: int = 0, tokens_used: int = 0):
        step = ReasoningStep(
            step_number=len(self.steps) + 1,
            action=action,
            input_summary=input_summary[:500],
            output_summary=output_summary[:500],
            duration_ms=duration_ms,
            tokens_used=tokens_used
        )
        self.steps.append(step)
        self.total_tokens += tokens_used
        self.total_duration_ms += duration_ms

# === Attempt Tracking ===

class AttemptRecord(BaseModel):
    """Record of a single fix attempt."""
    attempt_number: int
    fix_plan: Optional["FixPlan"] = None
    verification_result: Optional["VerificationResult"] = None
    reasoning_trace: Optional[ReasoningTrace] = None
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    failure_reason: Optional[str] = None

class VerificationResult(BaseModel):
    success: bool
    input_hash: str
    output_log: str
    duration_ms: int
    tests_passed: int = 0
    tests_failed: int = 0
    tests_total: int = 0
    exit_code: int = 0
    
    @property
    def pass_ratio(self) -> float:
        if self.tests_total == 0:
            return 1.0 if self.success else 0.0
        return self.tests_passed / self.tests_total

class FixPlan(BaseModel):
    rationale: str
    root_cause: str = ""
    files_to_change: List[FileDiff]
    verification_steps: List[str]
    confidence_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.MEDIUM
    attempt_number: int = 1
    previous_failure_context: Optional[str] = None
    
    def content_hash(self) -> str:
        content = json.dumps([f.model_dump() for f in self.files_to_change], sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

# === Confidence Scoring ===

class ConfidenceFactors(BaseModel):
    """All factors used in confidence calculation."""
    test_pass_ratio: float = Field(ge=0.0, le=1.0, default=0.0)
    inverse_blast_radius: float = Field(ge=0.0, le=1.0, default=1.0)
    attempt_penalty: float = Field(ge=0.0, le=1.0, default=1.0)
    risk_modifier: float = Field(ge=0.0, le=1.0, default=0.5)
    self_consistency_score: float = Field(ge=0.0, le=1.0, default=0.5)
    
    def weighted_score(self) -> float:
        """Calculate weighted confidence score."""
        return (
            0.35 * self.test_pass_ratio +
            0.25 * self.inverse_blast_radius +
            0.15 * self.attempt_penalty +
            0.15 * self.risk_modifier +
            0.10 * self.self_consistency_score
        )

# === Metrics ===

class MetricsData(BaseModel):
    """Performance and usage metrics."""
    incident_id: str
    total_attempts: int = 0
    total_api_calls: int = 0
    total_tokens_used: int = 0
    total_duration_ms: int = 0
    final_decision: Optional[DecisionType] = None
    final_confidence: float = 0.0
    files_modified: int = 0
    sandbox_runs: int = 0
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

# === Report ===

class IncidentReport(BaseModel):
    """Final incident resolution report."""
    incident_id: str
    decision: DecisionType
    confidence: float
    confidence_factors: ConfidenceFactors
    attempts: List[AttemptRecord]
    metrics: MetricsData
    final_plan: Optional[FixPlan] = None
    final_verification: Optional[VerificationResult] = None
    report_text: str = ""
    created_at: datetime = Field(default_factory=datetime.now)

# Update forward references
AttemptRecord.model_rebuild()
