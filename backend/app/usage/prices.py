"""Claude API list prices, $ per million tokens. Transcripts record tokens, not dollars.

Checked against Claude Code's own per-session cost (cost-state records): its token counts
priced with these rates match the cost it reports to within a few percent. Override or
add models under [pricing] in eyrie.toml.
"""
import re

from pydantic import BaseModel

PRICES_UPDATED = "2026-10-06"


class ModelPrice(BaseModel):
    input: float
    output: float
    cache_write_5m: float
    cache_write_1h: float
    cache_read: float


def _std(input: float, output: float, cache_read: float | None = None) -> ModelPrice:
    # Cache writes are 1.25x input (5-minute TTL) or 2x (1-hour); reads are 0.1x unless the
    # model has its own read price.
    return ModelPrice(input=input, output=output, cache_write_5m=input * 1.25, cache_write_1h=input * 2,
                      cache_read=input * 0.1 if cache_read is None else cache_read)


DEFAULT_PRICES: dict[str, ModelPrice] = {
    "claude-fable-5-1": _std(10, 50, 0.25),
    "claude-fable-5": _std(10, 50, 1.0),
    "claude-opus-5-5": _std(4, 20, 0.20),
    "claude-opus-5": _std(5, 25),
    "claude-opus-4-8": _std(5, 25),
    "claude-opus-4-7": _std(5, 25),
    "claude-opus-4-6": _std(5, 25),
    "claude-sonnet-5-5": _std(2, 10, 0.20),
    "claude-sonnet-5": _std(2, 10),
    "claude-sonnet-4-6": _std(3, 15),
    "claude-haiku-5-5": _std(0.10, 0.50),
    "claude-haiku-4-5": _std(1, 5),
}

_SUFFIX = re.compile(r"(\[[^\]]*\]|-\d{8})$")


def normalize_model(model: str) -> str:
    """claude-opus-4-6[1m] -> claude-opus-4-6, claude-haiku-4-5-20251001 -> claude-haiku-4-5"""
    while True:
        stripped = _SUFFIX.sub("", model)
        if stripped == model:
            return model
        model = stripped
