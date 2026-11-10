"""Constrain token generation with a regular-expression DFA."""


from ..regex.state import DFA
from .token_index import TokenIndex


class RegexConstraint:
    """Constrain token generation with a regex-backed DFA.

    The pattern is compiled when the constraint is created. The tokenizer is
    attached separately because it belongs to the decoder, not the regex.
    Candidate tokens are checked without changing the DFA; the DFA advances
    only when ``consume_token`` commits a selected token.
    """

    def __init__(self, pattern: str):
        self.pattern = pattern
        self.dfa = DFA(pattern)
        self._token_index: TokenIndex | None = None

    def bind(self, tokenizer) -> None:
        """Attach a tokenizer for vocabulary lookup.

        Parameters
        ----------
        tokenizer
            Tokenizer whose vocabulary will be checked against the DFA.
        """
        self._token_index = TokenIndex(tokenizer)

    def valid_token_ids(self) -> list[int]:
        """Return token IDs that can continue the regex match.

        Returns
        -------
        list[int]
            Sorted vocabulary IDs whose full decoded text is valid.
        """
        token_index = self._require_bound()
        valid_token_ids = []

        for token_id, text in token_index.entries(self.dfa.valid_symbols()):
            if self._can_consume(text):
                valid_token_ids.append(token_id)

        return sorted(valid_token_ids)

    def consume_token(self, token_id: int) -> None:
        """Commit a generated token to the regex DFA.

        Parameters
        ----------
        token_id
            Vocabulary ID selected by the decoder.
        """
        text = self._require_bound().text(token_id)
        for symbol in text:
            self.dfa.transition(self.dfa.current_state, symbol)

    def is_complete(self) -> bool:
        """Return whether the regex DFA is in an accepting state."""
        self._require_bound()
        return self.dfa.current_state in self.dfa.accepting_states

    def _can_consume(self, text: str) -> bool:
        state = self.dfa.current_state
        for symbol in text:
            state = self.dfa.transitions.get(state, {}).get(symbol)
            if state is None:
                return False
        return True

    def _require_bound(self) -> TokenIndex:
        if self._token_index is None:
            raise RuntimeError("RegexConstraint must be bound to a tokenizer")
        return self._token_index