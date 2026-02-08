from nightingale.types import FixPlan, VerificationResult
from nightingale.core.sandbox import Sandbox

class VerificationAgent:
    def __init__(self):
        pass

    def verify(self, sandbox: Sandbox, plan: FixPlan) -> VerificationResult:
        """
        Executes the verification steps in the sandbox.
        """
        combined_logs = ""
        success = True
        
        for cmd in plan.verification_steps:
            code, stdout, stderr = sandbox.run_command(cmd)
            combined_logs += f"CMD: {cmd}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}\n"
            if code != 0:
                success = False
                break
        
        return VerificationResult(
            success=success,
            input_hash="hash(plan)", # placeholder
            output_log=combined_logs,
            duration_ms=0 # placeholder
        )
