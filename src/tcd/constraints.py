"""Map tokenizer vocabulary entries onto valid DFA transitions."""


from typing import Protocol

from .json_parser import JsonParserState
from .schema import SchemaNode, compile_schema
from .state import DFA
from .token_index import TokenIndex


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


class JSONSchemaConstraint:
    """Constrain token generation with an incremental JSON Schema parser."""

    def __init__(self, schema: SchemaNode | dict[str, object]):
        self.schema = compile_schema(schema) if isinstance(schema, dict) else schema
        self._parser = JsonParserState(self.schema)
        self._token_index: TokenIndex | None = None

    def bind(self, tokenizer) -> None:
        """Attach a tokenizer for vocabulary lookup.

        Parameters
        ----------
        tokenizer
            Tokenizer whose vocabulary will be checked against the parser.
        """
        self._token_index = TokenIndex(tokenizer)

    def valid_token_ids(self) -> list[int]:
        """Return token IDs whose text can continue the JSON document."""
        token_index = self._require_bound()
        valid_token_ids = []
        for token_id, text in token_index.entries(self._parser.valid_symbols()):
            if self._parser.can_consume(text):
                valid_token_ids.append(token_id)
        return sorted(valid_token_ids)

    def consume_token(self, token_id: int) -> None:
        """Commit a generated token to the JSON parser.

        Parameters
        ----------
        token_id
            Vocabulary ID selected by the decoder.
        """
        self._parser.consume(self._require_bound().text(token_id))

    def is_complete(self) -> bool:
        """Return whether the JSON document is complete and schema-valid."""
        self._require_bound()
        return self._parser.is_complete()

    def _require_bound(self) -> TokenIndex:
        if self._token_index is None:
            raise RuntimeError("JSONSchemaConstraint must be bound to a tokenizer")
        return self._token_index