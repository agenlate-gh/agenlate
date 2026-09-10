"""The margin, for Phase 2.

Nothing in the MVP calls this. During the free Beta users pay OpenRouter
directly with their own key, so the company is not in the payment path and
there is nothing to mark up. It exists now because the ledger's unit of account
has to be right from the first row: changing what a stored figure means, after
there are rows that mean the other thing, is a migration nobody wants.

The one rule that matters is what the multiplier is applied to. It multiplies
the cost the provider reported, never a price derived from token counts.
OpenRouter bills some things per call rather than per token — web search is
priced per result — so a token-derived figure misses real spending and breaks
whenever their pricing changes.
"""

from __future__ import annotations

MARGIN_MIN = 1.10
MARGIN_MAX = 1.20
DEFAULT_MARGIN = 1.20


class MarginError(ValueError):
    """The multiplier is outside the agreed range."""


def apply_margin(cost_usd: float | None, multiplier: float = DEFAULT_MARGIN) -> float | None:
    """Return what to charge for a request that cost ``cost_usd``.

    A pure function: no clock, no database, no configuration lookup. Billing
    arithmetic that cannot be reproduced from its inputs is billing arithmetic
    nobody can audit.

    ``None`` in, ``None`` out. An unpriced request has no known cost, so it has
    no defensible price either — returning zero would give the request away,
    and inventing a figure would charge for a guess. The caller has to decide
    what to do about it, which is the point.
    """
    if not MARGIN_MIN <= multiplier <= MARGIN_MAX:
        raise MarginError(
            f"multiplier {multiplier} is outside the agreed range "
            f"{MARGIN_MIN}–{MARGIN_MAX}"
        )
    if cost_usd is None:
        return None
    if cost_usd < 0:
        raise MarginError("cost cannot be negative")
    return cost_usd * multiplier


def margin_amount(cost_usd: float | None, multiplier: float = DEFAULT_MARGIN) -> float | None:
    """The revenue portion alone — what is charged minus what it cost."""
    charged = apply_margin(cost_usd, multiplier)
    if charged is None or cost_usd is None:
        return None
    return charged - cost_usd
