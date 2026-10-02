from quantlab.db import transaction
from quantlab.models import WorkflowEvent


def record_event(
    run_id: int, node: str, status: str, message: str, attempt: int = 1, payload: dict | None = None
) -> None:
    """Each event commits on its own so the UI sees progress immediately."""
    with transaction() as s:
        s.add(
            WorkflowEvent(
                workflow_run_id=run_id,
                node=node,
                status=status,
                attempt=attempt,
                message=message,
                payload=payload,
            )
        )
