from nightingale.types import FixPlan, VerificationResult

class ConfidenceScorer:
    def calculate(self, plan: FixPlan, result: VerificationResult) -> float:
        """
        Calculates a confidence score [0.0 - 1.0].
        """
        base_score = plan.confidence_score
        
        if not result.success:
            return 0.0
            
        # Adjust based on verification output (e.g., did we see "passed"?)
        if "passed" in result.output_log or "OK" in result.output_log:
            base_score += 0.1
        
        # Penalize high risk
        if plan.risk_level == "high":
            base_score -= 0.2
            
        return min(max(base_score, 0.0), 1.0)
