candidate validation -> copied state
selected token       -> real state"""Track incremental JSON primitive parsing state."""

from copy import copy


_HEX_DIGITS = set("0123456789abcdefABCDEF")
_STRING_ESCAPES = set('"\\/bfnrt')
_START_SYMBOLS = set('"-0123456789tfn')


class JsonParserState:
    """Parse one JSON primitive incrementally without accepting structure yet."""

    def __init__(self):
        self._mode = "value"
        self._number_kind: str | None = None
        self._literal: str | None = None
        self._literal_index = 0
        self._unicode_digits = 0

    def consume(self, text: str) -> None:
        """Consume text atomically or raise ``ValueError``.

        Parameters
        ----------
        text
            JSON text to consume from the current state.

        Raises
        ------
        ValueError
            If any character cannot continue the current primitive.
        """
        candidate = copy(self)
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
        candidate = copy(self)
        try:
            for char in text:
                candidate._consume_char(char)
        except ValueError:
            return False
        return True

    def valid_symbols(self) -> set[str] | None:
        """Return known next symbols, or ``None`` for string content.

        Returns
        -------
        set[str] | None
            Exact valid next symbols when the set is finite. ``None`` means
            any non-control character may continue a JSON string.
        """
        if self._mode == "value":
            return set(_START_SYMBOLS)
        if self._mode == "literal":
            return {self._literal[self._literal_index]}
        if self._mode == "number":
            if self._number_kind == "sign":
                return set("0123456789")
            if self._number_kind == "digits":
                return set("0123456789")
            return set()
        if self._mode == "string":
            return None
        if self._mode == "string_escape":
            return _STRING_ESCAPES | {"u"}
        if self._mode == "unicode_escape":
            return _HEX_DIGITS
        return set()

    def is_complete(self) -> bool:
        """Return whether a complete primitive value has been consumed."""
        if self._mode == "complete":
            return True
        return self._mode == "number" and self._number_kind in {"zero", "digits"}

    def _consume_char(self, char: str) -> None:
        if self._mode == "value":
            self._start_value(char)
        elif self._mode == "string":
            self._consume_string_char(char)
        elif self._mode == "string_escape":
            self._consume_escape(char)
        elif self._mode == "unicode_escape":
            self._consume_unicode_digit(char)
        elif self._mode == "literal":
            self._consume_literal_char(char)
        elif self._mode == "number":
            self._consume_number_char(char)
        else:
            raise ValueError("a complete JSON primitive cannot consume more text")

    def _start_value(self, char: str) -> None:
        if char == '"':
            self._mode = "string"
        elif char == "-":
            self._mode = "number"
            self._number_kind = "sign"
        elif char == "0":
            self._mode = "number"
            self._number_kind = "zero"
        elif char in "123456789":
            self._mode = "number"
            self._number_kind = "digits"
        elif char in "tfn":
            self._mode = "literal"
            self._literal = {"t": "true", "f": "false", "n": "null"}[char]
            self._literal_index = 1
        else:
            raise ValueError(f"invalid JSON primitive start: {char!r}")

    def _consume_string_char(self, char: str) -> None:
        if char == '"':
            self._mode = "complete"
        elif char == "\\":
            self._mode = "string_escape"
        elif ord(char) < 0x20:
            raise ValueError("JSON strings cannot contain control characters")

    def _consume_escape(self, char: str) -> None:
        if char in _STRING_ESCAPES:
            self._mode = "string"
        elif char == "u":
            self._mode = "unicode_escape"
            self._unicode_digits = 0
        else:
            raise ValueError(f"invalid JSON string escape: {char!r}")

    def _consume_unicode_digit(self, char: str) -> None:
        if char not in _HEX_DIGITS:
            raise ValueError(f"invalid Unicode escape digit: {char!r}")
        self._unicode_digits += 1
        if self._unicode_digits == 4:
            self._mode = "string"

    def _consume_literal_char(self, char: str) -> None:
        if char != self._literal[self._literal_index]:
            raise ValueError(f"invalid JSON literal character: {char!r}")
        self._literal_index += 1
        if self._literal_index == len(self._literal):
            self._mode = "complete"

    def _consume_number_char(self, char: str) -> None:
        if self._number_kind == "sign":
            if char == "0":
                self._number_kind = "zero"
            elif char in "123456789":
                self._number_kind = "digits"
            else:
                raise ValueError(f"invalid JSON number character: {char!r}")
        elif self._number_kind == "digits" and char in "0123456789":
            return
        else:
            raise ValueError(f"invalid JSON number character: {char!r}")
