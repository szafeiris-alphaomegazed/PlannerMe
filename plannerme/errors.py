class PlannerMeError(RuntimeError):
    """Base error for user-facing PlannerMe failures."""


class PlannerUsError(PlannerMeError):
    """Raised when PlannerUs rejects a request or returns invalid data."""
