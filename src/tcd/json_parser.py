"""Parse JSON incrementally with a stack of structural contexts."""

from copy import deepcopy
import json

from .schema import ObjectSchema, PrimitiveSchema, SchemaNode


_HEX_DIGITS = set("0123456789abcdefABCDEF")
_STRING_ESCAPES = set('"\\/bfnrt')
_START_SYMBOLS = set('"-0123456789tfn{[')
_WHITESPACE = set(" \t\r\n")
_NUMBER_DELIMITERS = _WHITESPACE | {",", "]", "}"}


class JsonParserState:
    """Track JSON syntax while allowing incomplete input during generation."""

    def __init__(self, schema: SchemaNode | None = None):
        self._schema = schema
        self._stack: list[dict[str, object]] = []
        self._root_complete = False
        self._active_kind: str | None = None
        self._string_buffer = ""
        self._pending_schema: SchemaNode | None = None
        self._mode = "structural"
        self._number_kind: str | None = None
        self._number_buffer = ""
        self._literal: str | None = None
        self._literal_index = 0
        self._unicode_digits = 0

    def consume(self, text: str) -> None:
        """Consume text atomically or raise ``ValueError``.

        Parameters
        ----------
        text
            JSON text to consume from the current parser state.

        Raises
        ------
        ValueError
            If any character cannot continue the JSON document.
        """
        candidate = deepcopy(self)
        for char in text:
            candidate._consume_char(char)
        self.__dict__.update(candidate.__dict__)

    def can_consume(self, text: str) -> bool:
        """Return whether text can be consumed without changing this state.

        Parameters
        ----------
        text
            Candidate JSON text to test.

        Returns
        -------
        bool
            ``True`` when every character is valid from the current state.
        """
        candidate = deepcopy(self)
        try:
            for char in text:
                candidate._consume_char(char)
        except ValueError:
            return False
        return True

    def valid_symbols(self) -> set[str] | None:
        """Return exact next symbols when the valid set is finite.

        Returns
        -------
        set[str] | None
            Valid symbols for the current state. ``None`` means string content
            is open to any non-control character.
        """
        if self._active_kind is not None:
            if self._mode == "string":
                return None
            if self._mode == "string_escape":
                return _STRING_ESCAPES | {"u"}
            if self._mode == "unicode_escape":
                return _HEX_DIGITS
            if self._mode == "literal":
                return {self._literal[self._literal_index]}
            if self._mode == "number":
                if self._number_kind == "sign":
                    return set("0123456789")
                if self._number_kind == "digits":
                    return set("0123456789") | _NUMBER_DELIMITERS
                return _NUMBER_DELIMITERS

        if self._root_complete:
            return set(_WHITESPACE)
        if not self._stack:
            return _START_SYMBOLS | _WHITESPACE

        frame = self._stack[-1]
        if frame["kind"] == "object":
            if frame["phase"] == "key_or_end":
                return {'"', "}"} | _WHITESPACE
            if frame["phase"] == "key":
                return {'"'}
            if frame["phase"] == "colon":
                return {":"}
            if frame["phase"] == "value":
                return _START_SYMBOLS | _WHITESPACE
            return {",", "}"} | _WHITESPACE

        if frame["phase"] == "value_or_end":
            return _START_SYMBOLS | {"]"} | _WHITESPACE
        if frame["phase"] == "value":
            return _START_SYMBOLS | _WHITESPACE
        return {",", "]"} | _WHITESPACE

    def is_complete(self) -> bool:
        """Return whether a complete JSON document has been consumed."""
        if self._root_complete:
            return True
        return (
            not self._stack
            and self._active_kind == "value"
            and self._mode == "number"
            and self._number_kind in {"zero", "digits"}
            and self._number_is_allowed()
        )

    def _consume_char(self, char: str) -> None:
        if self._active_kind is not None:
            if self._mode == "number":
                self._consume_number_char(char)
            elif self._mode == "literal":
                self._consume_literal_char(char)
            elif self._mode == "string":
                self._consume_string_char(char)
            elif self._mode == "string_escape":
                self._consume_escape(char)
            else:
                self._consume_unicode_digit(char)
            return

        self._consume_structural_char(char)

    def _consume_structural_char(self, char: str) -> None:
        if char in _WHITESPACE:
            return
        if self._root_complete:
            raise ValueError("a complete JSON document cannot contain more values")
        if not self._stack:
            self._start_value(char)
            return

        frame = self._stack[-1]
        kind = frame["kind"]
        phase = frame["phase"]
        if kind == "object":
            if phase == "key_or_end":
                if char == "}":
                    self._close_container("object")
                elif char == '"':
                    self._start_string("key")
                else:
                    raise ValueError("object expects a key or closing brace")
            elif phase == "key":
                if char == '"':
                    self._start_string("key")
                else:
                    raise ValueError("object expects a string key")
            elif phase == "colon":
                if char == ":":
                    frame["phase"] = "value"
                else:
                    raise ValueError("object key must be followed by a colon")
            elif phase == "value":
                self._start_value(char)
            elif phase == "comma_or_end":
                if char == ",":
                    frame["phase"] = "key"
                elif char == "}":
                    self._close_container("object")
                else:
                    raise ValueError("object expects a comma or closing brace")
            return

        if phase == "value_or_end":
            if char == "]":
                self._close_container("array")
            else:
                self._start_value(char)
        elif phase == "value":
            self._start_value(char)
        elif phase == "comma_or_end":
            if char == ",":
                frame["phase"] = "value"
            elif char == "]":
                self._close_container("array")
            else:
                raise ValueError("array expects a comma or closing bracket")

    def _start_value(self, char: str) -> None:
        expected_schema = self._expected_schema()
        self._validate_value_start(char, expected_schema)

        if self._stack and self._stack[-1]["kind"] == "array":
            self._stack[-1]["phase"] = "value"

        if char == "{":
            self._stack.append(
                {
                    "kind": "object",
                    "phase": "key_or_end",
                    "schema": expected_schema,
                    "seen": set(),
                    "pending_name": None,
                    "pending_schema": None,
                }
            )
        elif char == "[":
            self._stack.append({"kind": "array", "phase": "value_or_end"})
        elif char == '"':
            self._start_string("value")
        elif char == "-":
            self._active_kind = "value"
            self._mode = "number"
            self._number_kind = "sign"
            self._number_buffer = char
        elif char == "0":
            self._active_kind = "value"
            self._mode = "number"
            self._number_kind = "zero"
            self._number_buffer = char
        elif char in "123456789":
            self._active_kind = "value"
            self._mode = "number"
            self._number_kind = "digits"
            self._number_buffer = char
        elif char in "tfn":
            self._active_kind = "value"
            self._mode = "literal"
            self._literal = {"t": "true", "f": "false", "n": "null"}[char]
            self._literal_index = 1
        else:
            raise ValueError(f"invalid JSON value start: {char!r}")

    def _start_string(self, kind: str) -> None:
        self._active_kind = kind
        self._mode = "string"
        self._string_buffer = ""

    def _consume_string_char(self, char: str) -> None:
        if char == '"':
            kind = self._active_kind
            value = json.loads(f'"{self._string_buffer}"')
            self._active_kind = None
            self._mode = "structural"
            if kind == "key":
                self._finish_key()
            else:
                self._complete_value(value)
        elif char == "\\":
            self._mode = "string_escape"
            self._string_buffer += char
        elif ord(char) < 0x20:
            raise ValueError("JSON strings cannot contain control characters")
        else:
            self._string_buffer += char

    def _consume_escape(self, char: str) -> None:
        if char in _STRING_ESCAPES:
            self._mode = "string"
            self._string_buffer += char
        elif char == "u":
            self._mode = "unicode_escape"
            self._unicode_digits = 0
            self._string_buffer += char
        else:
            raise ValueError(f"invalid JSON string escape: {char!r}")

    def _consume_unicode_digit(self, char: str) -> None:
        if char not in _HEX_DIGITS:
            raise ValueError(f"invalid Unicode escape digit: {char!r}")
        self._unicode_digits += 1
        self._string_buffer += char
        if self._unicode_digits == 4:
            self._mode = "string"

    def _consume_literal_char(self, char: str) -> None:
        if char != self._literal[self._literal_index]:
            raise ValueError(f"invalid JSON literal character: {char!r}")
        self._literal_index += 1
        if self._literal_index == len(self._literal):
            self._active_kind = None
            self._mode = "structural"
            self._complete_value(
                {"true": True, "false": False, "null": None}[self._literal]
            )

    def _consume_number_char(self, char: str) -> None:
        if self._number_kind == "sign":
            if char == "0":
                self._number_kind = "zero"
                self._number_buffer += char
            elif char in "123456789":
                self._number_kind = "digits"
                self._number_buffer += char
            else:
                raise ValueError(f"invalid JSON number character: {char!r}")
        elif self._number_kind == "zero":
            if char in _NUMBER_DELIMITERS:
                self._finish_number(char)
            else:
                raise ValueError(f"invalid JSON number character: {char!r}")
        elif char in "0123456789":
            self._number_kind = "digits"
            self._number_buffer += char
        elif char in _NUMBER_DELIMITERS:
            self._finish_number(char)
        else:
            raise ValueError(f"invalid JSON number character: {char!r}")

    def _finish_number(self, delimiter: str) -> None:
        self._active_kind = None
        self._mode = "structural"
        self._complete_value(int(self._number_buffer))
        self._consume_structural_char(delimiter)

    def _complete_value(self, value: object = None) -> None:
        expected_schema = self._expected_schema()
        if (
            isinstance(expected_schema, PrimitiveSchema)
            and expected_schema.enum_values is not None
            and value not in expected_schema.enum_values
        ):
            raise ValueError(f"value is not in the allowed enum: {value!r}")
        if not self._stack:
            self._root_complete = True
            return
        frame = self._stack[-1]
        if frame["phase"] != "value":
            raise ValueError("JSON value is not expected here")
        if frame["kind"] == "object":
            frame["seen"].add(frame["pending_name"])
            frame["pending_name"] = None
            frame["pending_schema"] = None
        frame["phase"] = "comma_or_end"

    def _number_is_allowed(self) -> bool:
        schema = self._expected_schema()
        return not (
            isinstance(schema, PrimitiveSchema)
            and schema.enum_values is not None
            and int(self._number_buffer) not in schema.enum_values
        )

    def _close_container(self, kind: str) -> None:
        if not self._stack or self._stack[-1]["kind"] != kind:
            raise ValueError(f"unexpected closing {kind}")
        frame = self._stack[-1]
        schema = frame.get("schema")
        if isinstance(schema, ObjectSchema):
            missing = schema.required - frame["seen"]
            if missing:
                raise ValueError(f"required properties are missing: {sorted(missing)}")
        self._stack.pop()
        self._complete_value()

    def _expected_schema(self) -> SchemaNode | None:
        if not self._stack:
            return self._schema
        frame = self._stack[-1]
        return frame.get("pending_schema")

    def _validate_value_start(
        self,
        char: str,
        schema: SchemaNode | None,
    ) -> None:
        if schema is None:
            return
        if isinstance(schema, ObjectSchema):
            if char != "{":
                raise ValueError("value does not match object type")
            return
        expected_starts = {
            "string": {'"'},
            "integer": set("-0123456789"),
            "boolean": {"t", "f"},
            "null": {"n"},
        }[schema.value_type]
        if char not in expected_starts:
            raise ValueError(f"value does not match {schema.value_type} type")

    def _finish_key(self) -> None:
        frame = self._stack[-1]
        key = self._string_buffer
        seen = frame["seen"]
        if key in seen:
            raise ValueError(f"duplicate object property: {key!r}")

        schema = frame["schema"]
        if isinstance(schema, ObjectSchema):
            if not schema.allows_property(key):
                raise ValueError(f"unknown object property: {key!r}")
            frame["pending_schema"] = schema.properties.get(key)
        frame["pending_name"] = key
        frame["phase"] = "colon"
