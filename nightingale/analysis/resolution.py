class ResolutionEngine:
    def decide(self, confidence_score: float) -> str:
        """
        Decides whether to 'resolve' or 'escalate'.
        """
        THRESHOLD = 0.85
        if confidence_score >= THRESHOLD:
            return "resolve"
        return "escalate"
