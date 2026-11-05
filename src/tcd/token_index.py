"""Index decoded tokenizer vocabulary entries for constraint lookup."""


class TokenIndex:
    """Cache token text and group vocabulary entries by first character."""

    def __init__(self, tokenizer):
        self._text_by_id: dict[int, str] = {}
        self._entries_by_first_symbol: dict[str, list[tuple[int, str]]] = {}
        for token_id in tokenizer.get_vocab().values():
            text = tokenizer.decode(
                [token_id],
                skip_special_tokens=False,
                clean_up_tokenization_spaces=False,
            )
            if not text:
                continue
            self._text_by_id[token_id] = text
            self._entries_by_first_symbol.setdefault(text[0], []).append((token_id, text))

    def entries(self, first_symbols: set[str] | None) -> list[tuple[int, str]]:
        """Return cached token entries matching possible first symbols.

        Parameters
        ----------
        first_symbols
            First characters accepted by the current state. ``None`` requests
            all entries, which is needed while parsing string content.

        Returns
        -------
        list[tuple[int, str]]
            Token IDs paired with their decoded text.
        """
        if first_symbols is None:
            return list(self._text_by_id.items())

        entries = []
        for symbol in first_symbols:
            entries.extend(self._entries_by_first_symbol.get(symbol, []))
        return entries

    def text(self, token_id: int) -> str:
        """Return cached decoded text for a token ID.

        Parameters
        ----------
        token_id
            Vocabulary ID to look up.

        Returns
        -------
        str
            Decoded token text.
        """
        return self._text_by_id[token_id]
