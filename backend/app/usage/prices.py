"""API list prices, $ per million tokens. Transcripts record tokens, not dollars.

Claude: checked against Claude Code's own per-session cost (cost-state records): its token
counts priced with these rates match the cost it reports to within a few percent.
OpenAI (Codex): the Standard tier, short-context column, from
developers.openai.com/api/docs/pricing. Codex's context window (258,400) is under the 272K
long-context threshold, so the long-context rates never apply.
Gemini (Gemini CLI): paid tier Standard, from ai.google.dev/gemini-api/docs/pricing. Some are
introductory and rise later (gemini-4-argon on 2026-12-01; the 3.6/3.8 flash models on
2027-01-01): update these then, since history is priced at query time. The >200K-prompt tier
of the pro models isn't modelled. Caching is implicit, so there's no write price.
Override or add models under [pricing] in eyrie.toml.
"""
import re

from pydantic import BaseModel

PRICES_UPDATED = "2026-10-20"


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

def _openai(input: float, cached: float, output: float, cache_write: float | None = None) -> ModelPrice:
    # Codex rows store uncached input, cached input as cache_read, and cache writes as 5m.
    w = input if cache_write is None else cache_write
    return ModelPrice(input=input, output=output, cache_write_5m=w, cache_write_1h=w, cache_read=cached)


DEFAULT_PRICES |= {
    "gpt-6-astra": _openai(10, 1.0, 50, 12.5),
    "gpt-6.1-sol": _openai(2, 0.10, 10, 2.5),
    "gpt-6-sol": _openai(2, 0.20, 10, 2.5),
    "gpt-6-luna": _openai(0.10, 0.01, 0.50, 0.125),
    "gpt-5.6-sol": _openai(4, 0.40, 20, 5),
    "gpt-5.6-terra": _openai(2, 0.20, 12, 2.5),
    "gpt-5.5": _openai(5, 0.50, 30),
    "gpt-5.4": _openai(2.5, 0.25, 15),
}

def _gemini(input: float, output: float, cached: float) -> ModelPrice:
    return ModelPrice(input=input, output=output, cache_write_5m=input, cache_write_1h=input, cache_read=cached)


DEFAULT_PRICES |= {
    "gemini-4-argon": _gemini(2.00, 10.00, 0.10),
    "gemini-3.8-flash": _gemini(0.75, 3.75, 0.075),
    "gemini-3.6-flash": _gemini(0.75, 3.75, 0.075),
    "gemini-3.5-flash-lite": _gemini(0.30, 2.50, 0.03),
    "gemini-3.1-pro-preview": _gemini(2.00, 12.00, 0.20),
    "gemini-3.1-flash-lite": _gemini(0.25, 1.50, 0.025),
    "gemini-3-flash-preview": _gemini(0.50, 3.00, 0.05),
    "gemini-2.5-pro": _gemini(1.25, 10.00, 0.125),
    "gemini-2.5-flash": _gemini(0.30, 2.50, 0.03),
    "gemini-2.5-flash-lite": _gemini(0.10, 0.40, 0.01),
}

_SUFFIX = re.compile(r"(\[[^\]]*\]|-\d{8})$")


def normalize_model(model: str) -> str:
    """claude-opus-4-6[1m] -> claude-opus-4-6, claude-haiku-4-5-20251001 -> claude-haiku-4-5"""
    while True:
        stripped = _SUFFIX.sub("", model)
        if stripped == model:
            return model
        model = stripped
