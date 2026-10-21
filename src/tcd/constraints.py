from .state import DFA


class DFAConstraint:
    """Find tokenizer tokens whose decoded text can advance a DFA."""

    def __init__(self, dfa: DFA, tokenizer):
        self.dfa = dfa
        self.tokenizer = tokenizer
        self._tokens_by_first_symbol: dict[str, list[tuple[int, str]]] = {}
        self._token_text_by_id: dict[int, str] = {}
        self._index_vocabulary()

    def valid_token_ids(self) -> list[int]:
        """Return token IDs that consume valid text from the current DFA state."""
        valid_symbols = self.dfa.valid_symbols()
        valid_token_ids = []

        for symbol in valid_symbols:
            for token_id, text in self._tokens_by_first_symbol.get(symbol, []):
                if self._can_consume(text):
                    valid_token_ids.append(token_id)

        return sorted(valid_token_ids)

    def consume_token(self, token_id: int) -> None:
        """Commit a generated token by consuming its decoded characters."""
        text = self._token_text_by_id[token_id]
        for symbol in text:
            self.dfa.transition(self.dfa.current_state, symbol)

    def is_complete(self) -> bool:
        """Return whether the DFA is currently in an accepting state."""
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