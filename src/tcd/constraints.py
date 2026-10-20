from .state import DFA


class DFAConstraint:
    """Find tokenizer tokens whose decoded text can advance a DFA."""

    def __init__(self, dfa: DFA, tokenizer):
        self.dfa = dfa
        self.tokenizer = tokenizer

    def valid_token_ids(self) -> list[int]:
        """Return token IDs that consume valid text from the current DFA state."""
        valid_symbols = self.dfa.valid_symbols()
        valid_token_ids = []

        for token_id in self.tokenizer.get_vocab().values(): 
            # this is actually crazy approch 😂 (what if i have billions of vocab)
            # do i want to loop over all?? lmao. we mount regardless 😂
            text = self.tokenizer.decode(
                [token_id],
                skip_special_tokens=False,
                clean_up_tokenization_spaces=False,
            )
            if text and text[0] in valid_symbols and self._can_consume(text):
                valid_token_ids.append(token_id)

        return sorted(valid_token_ids)

    def consume_token(self, token_id: int) -> None:
        """Commit a generated token by consuming its decoded characters."""
        text = self.tokenizer.decode(
            [token_id],
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        )
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