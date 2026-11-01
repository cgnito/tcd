"""Parse JSON incrementally with a stack of structural contexts."""

from copy import deepcopy


_HEX_DIGITS = set("0123456789abcdefABCDEF")
_STRING_ESCAPES = set('"\\/bfnrt')
_START_SYMBOLS = set('"-0123456789tfn{[')
_WHITESPACE = set(" \t\r\n")
_NUMBER_DELIMITERS = _WHITESPACE | {",", "]", "}"}


class JsonParserState:
    """Track JSON syntax while allowing incomplete input during generation."""

    def __init__(self):
        self._stack: list[dict[str, str]] = []
        self._root_complete = False
        self._active_kind: str | None = None
        self._mode = "structural"
        self._number_kind: str | None = None
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
        if self._stack and self._stack[-1]["kind"] == "array":
            self._stack[-1]["phase"] = "value"

        if char == "{":
            self._stack.append({"kind": "object", "phase": "key_or_end"})
        elif char == "[":
            self._stack.append({"kind": "array", "phase": "value_or_end"})
        elif char == '"':
            self._start_string("value")
        elif char == "-":
            self._active_kind = "value"
            self._mode = "number"
            self._number_kind = "sign"
        elif char == "0":
            self._active_kind = "value"
            self._mode = "number"
            self._number_kind = "zero"
        elif char in "123456789":
            self._active_kind = "value"
            self._mode = "number"
            self._number_kind = "digits"
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

    def _consume_string_char(self, char: str) -> None:
        if char == '"':
            kind = self._active_kind
            self._active_kind = None
            self._mode = "structural"
            if kind == "key":
                self._stack[-1]["phase"] = "colon"
            else:
                self._complete_value()
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
            self._active_kind = None
            self._mode = "structural"
            self._complete_value()

    def _consume_number_char(self, char: str) -> None:
        if self._number_kind == "sign":
            if char == "0":
                self._number_kind = "zero"
            elif char in "123456789":
                self._number_kind = "digits"
            else:
                raise ValueError(f"invalid JSON number character: {char!r}")
        elif self._number_kind == "zero":
            if char in _NUMBER_DELIMITERS:
                self._finish_number(char)
            else:
                raise ValueError(f"invalid JSON number character: {char!r}")
        elif char in "0123456789":
            self._number_kind = "digits"
        elif char in _NUMBER_DELIMITERS:
            self._finish_number(char)
        else:
            raise ValueError(f"invalid JSON number character: {char!r}")

    def _finish_number(self, delimiter: str) -> None:
        self._active_kind = None
        self._mode = "structural"
        self._complete_value()
        self._consume_structural_char(delimiter)

    def _complete_value(self) -> None:
        if not self._stack:
            self._root_complete = True
            return
        frame = self._stack[-1]
        if frame["phase"] != "value":
            raise ValueError("JSON value is not expected here")
        frame["phase"] = "comma_or_end"

    def _close_container(self, kind: str) -> None:
        if not self._stack or self._stack[-1]["kind"] != kind:
            raise ValueError(f"unexpected closing {kind}")
        self._stack.pop()
        self._complete_value()
