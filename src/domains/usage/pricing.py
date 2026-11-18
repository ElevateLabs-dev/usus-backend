"""
Prices used to turn token counts into dollars.

US dollars per million tokens (input, output), from the providers' public
price lists. Dated model names (gpt-4.1-mini-2025-04-14) use the price of
their base name. A model that is not listed is still recorded, without a cost.
"""

from decimal import Decimal

_PER_MILLION: dict[str, tuple[str, str]] = {
    "gpt-4.1": ("2.00", "8.00"),
    "gpt-4.1-mini": ("0.40", "1.60"),
    "gpt-4.1-nano": ("0.10", "0.40"),
    "gpt-4o": ("2.50", "10.00"),
    "gpt-4o-mini": ("0.15", "0.60"),
    "gpt-5": ("1.25", "10.00"),
    "gpt-5-mini": ("0.25", "2.00"),
    "gpt-5-nano": ("0.05", "0.40"),
}

_MILLION = Decimal(1_000_000)


def llm_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    """The cost of one request, or None if the model's price is not known."""
    name = model.lower()
    matches = [
        base for base in _PER_MILLION if name == base or name.startswith(f"{base}-")
    ]
    if not matches:
        return None
    input_price, output_price = _PER_MILLION[max(matches, key=len)]
    return (
        Decimal(input_tokens) * Decimal(input_price)
        + Decimal(output_tokens) * Decimal(output_price)
    ) / _MILLION
