"""Constrain token generation with an incremental JSON Schema parser."""

from ..json_parser.schema import SchemaNode, compile_schema
from ..json_parser.state import JsonParserState
from .token_index import TokenIndex


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