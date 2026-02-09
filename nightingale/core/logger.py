"""
Nightingale Logging System
Structured logging with timestamps, reasoning traces, and metrics
"""
import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields if present
        if hasattr(record, 'incident_id'):
            log_data['incident_id'] = record.incident_id
        if hasattr(record, 'attempt'):
            log_data['attempt'] = record.attempt
        if hasattr(record, 'component'):
            log_data['component'] = record.component
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms
        if hasattr(record, 'tokens'):
            log_data['tokens'] = record.tokens
            
        return json.dumps(log_data)

class NightingaleLogger:
    """Enhanced logger with structured output and rich console display."""
    
    def __init__(self, name: str = "nightingale", log_file: Optional[Path] = None):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()
        
        # Rich console handler for pretty output
        rich_handler = RichHandler(
            console=console,
            show_time=True,
            show_path=False,
            rich_tracebacks=True,
            markup=True
        )
        rich_handler.setLevel(logging.INFO)
        self.logger.addHandler(rich_handler)
        
        # File handler for structured JSON logs
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(StructuredFormatter())
            file_handler.setLevel(logging.DEBUG)
            self.logger.addHandler(file_handler)
    
    def _log_with_context(self, level: int, msg: str, **kwargs):
        """Log with additional context fields."""
        extra = {k: v for k, v in kwargs.items() if v is not None}
        self.logger.log(level, msg, extra=extra)
    
    def info(self, msg: str, **kwargs):
        self._log_with_context(logging.INFO, msg, **kwargs)
    
    def debug(self, msg: str, **kwargs):
        self._log_with_context(logging.DEBUG, msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        self._log_with_context(logging.WARNING, msg, **kwargs)
    
    def error(self, msg: str, **kwargs):
        self._log_with_context(logging.ERROR, msg, **kwargs)
    
    def critical(self, msg: str, **kwargs):
        self._log_with_context(logging.CRITICAL, msg, **kwargs)
    
    # === Specialized Logging Methods ===
    
    def incident_start(self, incident_id: str, incident_type: str, repo: str):
        """Log incident processing start."""
        console.print(Panel(
            f"[bold cyan]Incident ID:[/] {incident_id}\n"
            f"[bold cyan]Type:[/] {incident_type}\n"
            f"[bold cyan]Repository:[/] {repo}",
            title="🚨 [bold red]CI FAILURE DETECTED[/]",
            border_style="red"
        ))
        self.info(f"Processing incident {incident_id}", 
                  incident_id=incident_id, component="orchestrator")
    
    def attempt_start(self, incident_id: str, attempt: int, max_attempts: int):
        """Log fix attempt start."""
        console.print(f"\n[bold yellow]━━━ Attempt {attempt}/{max_attempts} ━━━[/]")
        self.info(f"Starting attempt {attempt}/{max_attempts}", 
                  incident_id=incident_id, attempt=attempt, component="marathon")
    
    def reasoning_step(self, incident_id: str, attempt: int, step: str, details: str = ""):
        """Log a reasoning step."""
        console.print(f"  [dim]├─[/] [cyan]{step}[/] {details}")
        self.debug(f"Reasoning: {step}", 
                   incident_id=incident_id, attempt=attempt, component="reasoning")
    
    def api_call(self, incident_id: str, model: str, tokens: int, duration_ms: int):
        """Log Gemini API call."""
        console.print(f"  [dim]├─[/] [magenta]API Call:[/] {model} ({tokens} tokens, {duration_ms}ms)")
        self.debug(f"API call to {model}", 
                   incident_id=incident_id, tokens=tokens, duration_ms=duration_ms, component="gemini")
    
    def verification_result(self, incident_id: str, success: bool, 
                           passed: int, failed: int, total: int):
        """Log verification result."""
        status = "[green]✓ PASSED[/]" if success else "[red]✗ FAILED[/]"
        console.print(f"  [dim]├─[/] [bold]Verification:[/] {status} ({passed}/{total} tests)")
        self.info(f"Verification {'passed' if success else 'failed'}: {passed}/{total}",
                  incident_id=incident_id, component="verifier")
    
    def confidence_score(self, incident_id: str, score: float, factors: Dict[str, float]):
        """Log confidence calculation."""
        color = "green" if score >= 0.85 else "yellow" if score >= 0.6 else "red"
        console.print(f"  [dim]├─[/] [bold]Confidence:[/] [{color}]{score:.2%}[/]")
        for name, value in factors.items():
            console.print(f"  [dim]│   └─[/] {name}: {value:.2f}")
        self.info(f"Confidence: {score:.2%}", incident_id=incident_id, component="scoring")
    
    def decision(self, incident_id: str, decision: str, confidence: float):
        """Log final decision."""
        if decision == "resolve":
            console.print(Panel(
                f"[bold green]AUTO-RESOLVING[/]\nConfidence: {confidence:.2%}",
                title="✅ Decision",
                border_style="green"
            ))
        else:
            console.print(Panel(
                f"[bold yellow]ESCALATING TO HUMAN[/]\nConfidence: {confidence:.2%}",
                title="⚠️ Decision",
                border_style="yellow"
            ))
        self.info(f"Decision: {decision}", incident_id=incident_id, component="resolution")
    
    def show_fix_plan(self, rationale: str, files: list):
        """Display fix plan details."""
        console.print(f"\n  [bold]Fix Plan:[/]")
        console.print(f"  [dim]├─[/] [italic]{rationale}[/]")
        for f in files:
            console.print(f"  [dim]├─[/] 📄 {f.file_path} [{f.change_type}]")
    
    def show_code_diff(self, file_path: str, content: str, language: str = "python"):
        """Display code with syntax highlighting."""
        syntax = Syntax(content, language, theme="monokai", line_numbers=True)
        console.print(Panel(syntax, title=f"📝 {file_path}", border_style="blue"))
    
    def metrics_summary(self, metrics: Dict[str, Any]):
        """Display metrics summary."""
        console.print(Panel(
            f"[bold]Attempts:[/] {metrics.get('attempts', 0)}\n"
            f"[bold]API Calls:[/] {metrics.get('api_calls', 0)}\n"
            f"[bold]Tokens Used:[/] {metrics.get('tokens', 0)}\n"
            f"[bold]Duration:[/] {metrics.get('duration_ms', 0)}ms",
            title="📊 Metrics",
            border_style="cyan"
        ))

# Global logger instance
logger = NightingaleLogger()
