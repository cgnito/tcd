from tcd import DFA, DFAConstraint


class FakeTokenizer:
    def __init__(self, token_texts):
        self.token_texts = token_texts
        self.decode_calls = 0

    def get_vocab(self):
        return {text: token_id for token_id, text in self.token_texts.items()}

    def decode(self, token_ids, **kwargs):
        self.decode_calls += 1
        return self.token_texts[token_ids[0]]


def test_constraint_returns_tokens_that_fully_advance_dfa():
    tokenizer = FakeTokenizer({0: "y", 1: "n", 2: "yes", 3: "no", 4: "yea"})
    constraint = DFAConstraint(DFA("yes|no"), tokenizer)

    assert constraint.valid_token_ids() == [0, 1, 2, 3]


def test_candidate_lookup_does_not_change_dfa_state():
    dfa = DFA("yes|no")
    constraint = DFAConstraint(
        dfa,
        FakeTokenizer({0: "y", 1: "n", 2: "yes", 3: "no"}),
    )

    constraint.valid_token_ids()

    assert dfa.current_state == dfa.start_state


def test_consuming_tokens_advances_and_completes_constraint():
    dfa = DFA("yes|no")
    constraint = DFAConstraint(
        dfa,
        FakeTokenizer({0: "y", 1: "e", 2: "s", 3: "n", 4: "o"}),
    )

    constraint.consume_token(0)
    assert not constraint.is_complete()
    assert constraint.valid_token_ids() == [1]

    constraint.consume_token(1)
    constraint.consume_token(2)

    assert constraint.is_complete()


def test_constraint_decodes_vocabulary_once_and_reuses_cached_text():
    tokenizer = FakeTokenizer({0: "a", 1: "ab", 2: "b"})
    constraint = DFAConstraint(DFA("ab"), tokenizer)

    assert tokenizer.decode_calls == 3
    constraint.valid_token_ids()
    constraint.consume_token(0)
    constraint.valid_token_ids()

    assert tokenizer.decode_calls == 3