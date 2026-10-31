"""Map tokenizer vocabulary entries onto valid DFA transitions."""


from typing import Protocol

from .state import DFA


class Constraint(Protocol):
    """Define the state operations required by the decoder."""

    def bind(self, tokenizer) -> None:
        """Attach the tokenizer used to map text continuations to token IDs."""
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


class DFAConstraint:
    """Constrain token generation using a DFA and tokenizer vocabulary.

    Candidate tokens are checked without changing the DFA. The DFA advances
    only when ``consume_token`` commits a token selected by the decoder.

    Examples
    --------
    >>> constraint = DFAConstraint(DFA("yes|no"), tokenizer)
    >>> constraint.valid_token_ids()
    [ ... ]
    """

    def __init__(self, dfa: DFA, tokenizer):
        self.dfa = dfa
        self.tokenizer = tokenizer
        self._tokens_by_first_symbol: dict[str, list[tuple[int, str]]] = {}
        self._token_text_by_id: dict[int, str] = {}
        self._index_vocabulary()

    def valid_token_ids(self) -> list[int]:
        """Return token IDs whose full text is valid from the current state.

        Returns
        -------
        list[int]
            Sorted vocabulary IDs that can be consumed completely.
        """
        valid_symbols = self.dfa.valid_symbols()
        valid_token_ids = []

        for symbol in valid_symbols:
            for token_id, text in self._tokens_by_first_symbol.get(symbol, []):
                if self._can_consume(text):
                    valid_token_ids.append(token_id)

        return sorted(valid_token_ids)

    def consume_token(self, token_id: int) -> None:
        """Advance the DFA through a generated token's decoded text.

        Parameters
        ----------
        token_id
            Vocabulary ID selected by the decoder.
        """
        text = self._token_text_by_id[token_id]
        for symbol in text:
            self.dfa.transition(self.dfa.current_state, symbol)

    def is_complete(self) -> bool:
        """Return whether the DFA currently accepts the generated text."""
        return self.dfa.current_state in self.dfa.accepting_states

    def _can_consume(self, text: str) -> bool:
        state = self.dfa.current_state
        for symbol in text:
            state = self.dfa.transitions.get(state, {}).get(symbol)
            if state is None:
                return False
        return True

    def _index_vocabulary(self) -> None:
        """Decode the vocabulary once and group tokens by their first symbol."""
        for token_id in self.tokenizer.get_vocab().values():
            text = self.tokenizer.decode(
                [token_id],
                skip_special_tokens=False,
                clean_up_tokenization_spaces=False,
            )
            if not text:
                continue

            self._token_text_by_id[token_id] = text
            self._tokens_by_first_symbol.setdefault(text[0], []).append((token_id, text))


class RegexConstraint:
    """Bridge a regex DFA to the decoder's token-level constraint protocol.

    The pattern is compiled when the constraint is created. The tokenizer is
    attached separately because it belongs to the decoder, not the regex.
    """

    def __init__(self, pattern: str):
        self.pattern = pattern
        self.dfa = DFA(pattern)
        self._constraint: DFAConstraint | None = None

    def bind(self, tokenizer) -> None:
        """Attach a tokenizer for vocabulary lookup.

        Parameters
        ----------
        tokenizer
            Tokenizer whose vocabulary will be checked against the DFA.
        """
        self._constraint = DFAConstraint(self.dfa, tokenizer)

    def valid_token_ids(self) -> list[int]:
        """Return token IDs that can continue the regex match."""
        return self._require_bound().valid_token_ids()

    def consume_token(self, token_id: int) -> None:
        """Commit a generated token to the regex DFA.

        Parameters
        ----------
        token_id
            Vocabulary ID selected by the decoder.
        """
        self._require_bound().consume_token(token_id)

    def is_complete(self) -> bool:
        """Return whether the regex DFA is in an accepting state."""
        return self._require_bound().is_complete()

    def _require_bound(self) -> DFAConstraint:
        if self._constraint is None:
            raise RuntimeError("RegexConstraint must be bound to a tokenizer")
        return self._constraint