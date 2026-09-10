"""Usage recording and, for Phase 2, the margin.

Recording is live from the first Beta request. Billing is not: during the free
Beta users pay OpenRouter directly and the company is not in the payment path.
Keeping the two apart is why the margin function exists but is wired to
nothing.
"""

from .margin import DEFAULT_MARGIN, MARGIN_MAX, MARGIN_MIN, MarginError, apply_margin, margin_amount
from .recorder import UsageContext, UsageSummary, record, summarise, to_event

__all__ = [
    "DEFAULT_MARGIN",
    "MARGIN_MAX",
    "MARGIN_MIN",
    "MarginError",
    "UsageContext",
    "UsageSummary",
    "apply_margin",
    "margin_amount",
    "record",
    "summarise",
    "to_event",
]
