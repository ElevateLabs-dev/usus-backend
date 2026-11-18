"""
Prices used to turn token counts into dollars.

OpenAI's Standard prices in US dollars per 1M tokens: input, cached input and
output (https://developers.openai.com/api/docs/pricing). Models with a short
and a long context price use the short context one (up to 272K input tokens),
which covers every request a training session makes.

Dated model names (gpt-4.1-mini-2025-04-14) use the price of their base name.
A model that is not listed is still recorded, without a cost.
"""

from decimal import Decimal

# model: (input, cached input, output); cached None = no cached price
_PER_MILLION: dict[str, tuple[str, str | None, str]] = {
    "gpt-6.2-astra": ("8.00", "0.40", "40.00"),
    "gpt-6.2-sol": ("2.00", "0.10", "10.00"),
    "gpt-6-astra": ("10.00", "1.00", "50.00"),
    "gpt-6.1-sol": ("2.00", "0.10", "10.00"),
    "gpt-6.1-terra": ("1.00", "0.05", "5.00"),
    "gpt-6-luna": ("0.10", "0.01", "0.50"),
    "gpt-6-sol": ("2.00", "0.20", "10.00"),
    "gpt-5.6-sol": ("4.00", "0.40", "20.00"),
    "gpt-5.6-terra": ("2.00", "0.20", "12.00"),
    "gpt-5.6-luna": ("0.20", "0.02", "1.20"),
    "gpt-5.5": ("5.00", "0.50", "30.00"),
    "gpt-5.5-pro": ("30.00", None, "180.00"),
    "gpt-5.4": ("2.50", "0.25", "15.00"),
    "gpt-5.4-pro": ("30.00", None, "180.00"),
    "gpt-5.4-mini": ("0.75", "0.075", "4.50"),
    "gpt-5.4-nano": ("0.20", "0.02", "1.25"),
    "gpt-5.2": ("1.75", "0.175", "14.00"),
    "gpt-5.2-pro": ("21.00", None, "168.00"),
    "gpt-5.1": ("1.25", "0.125", "10.00"),
    "gpt-5": ("1.25", "0.125", "10.00"),
    "gpt-5-mini": ("0.25", "0.025", "2.00"),
    "gpt-5-nano": ("0.05", "0.005", "0.40"),
    "gpt-5-pro": ("15.00", None, "120.00"),
    "gpt-4.1": ("2.00", "0.50", "8.00"),
    "gpt-4.1-mini": ("0.40", "0.10", "1.60"),
    "gpt-4o": ("2.50", "1.25", "10.00"),
    "gpt-4o-mini": ("0.15", "0.075", "0.60"),
    "o3-pro": ("20.00", None, "80.00"),
    "o3": ("2.00", "0.50", "8.00"),
}

_MILLION = Decimal(1_000_000)


def llm_cost(
    model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0
) -> Decimal | None:
    """
    The cost of one request, or None if the model's price is not known.

    input_tokens includes the cached ones (as OpenAI reports it); those are
    charged at the cached input price.
    """
    name = model.lower()
    matches = [
        base for base in _PER_MILLION if name == base or name.startswith(f"{base}-")
    ]
    if not matches:
        return None
    input_price, cached_price, output_price = _PER_MILLION[max(matches, key=len)]
    cached = min(max(cached_tokens, 0), input_tokens) if cached_price else 0
    return (
        Decimal(input_tokens - cached) * Decimal(input_price)
        + Decimal(cached) * Decimal(cached_price or 0)
        + Decimal(output_tokens) * Decimal(output_price)
    ) / _MILLION
