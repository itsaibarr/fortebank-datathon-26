class UnknownDecisions:
    identity = {"fixture": "synthetic-only"}

    def ready(self):
        return True

    def propose(self, state, questions, *, deadline):
        return {
            key: {
                "choice": "unknown",
                "probabilities": {"satisfied": 0.0, "contradicted": 0.0, "unknown": 1.0},
            }
            for key in questions
        }
