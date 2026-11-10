"""Define the behavior required by decoder constraints."""

from typing import Protocol


class Constraint(Protocol):
    """Define the state operations required by the decoder."""

    def bind(self, tokenizer) -> None:
        """Attach the tokenizer used to map continuations to token IDs."""
        ...

    def valid_token_ids(self) -> list[int]:
        """Return token IDs that can continue the current constraint state."""
        ...

    def consume_token(self, token_id: int) -> None:
        """Commit a selected token to the constraint state."""
        ...

    def is_complete(self) -> bool:
        """Return whether the generated text is complete and valid."""
        ...