"""Per-row cost. Local models have no token bill, but the GPU box isn't free:
wall time x an hourly rate, plus token prices if a hosted model is swapped in.
Stored per row, so "which templates are expensive" and "what will a re-run
cost" are queries, not guesses."""
from __future__ import annotations

import os

COMPUTE_USD_PER_HOUR = float(os.environ.get("COMPUTE_USD_PER_HOUR", "0.35"))
USD_PER_M_INPUT = float(os.environ.get("USD_PER_M_INPUT", "0"))
USD_PER_M_OUTPUT = float(os.environ.get("USD_PER_M_OUTPUT", "0"))


def price(seconds: float, input_tokens: int, output_tokens: int) -> float:
    return round(seconds / 3600 * COMPUTE_USD_PER_HOUR
                 + input_tokens / 1e6 * USD_PER_M_INPUT
                 + output_tokens / 1e6 * USD_PER_M_OUTPUT, 6)
