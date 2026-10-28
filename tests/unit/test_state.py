import pytest

from tcd import DFA
from tcd.state import EPSILON, NFA


@pytest.mark.parametrize(
    ("pattern", "accepted", "rejected"),
    [
        ("yes|no", ["yes", "no"], ["ye", "maybe", "yess"]),
        ("ab", ["ab"], ["a", "ba", "abc"]),
        ("a(b|c)", ["ab", "ac"], ["a", "aa", "bc"]),
        ("ab*", ["a", "ab", "abbb"], ["", "b", "ba"]),
    ],
)
def test_dfa_accepts_supported_patterns(pattern, accepted, rejected):
    dfa = DFA(pattern)

    assert all(dfa.accepts(value) for value in accepted)
    assert not any(dfa.accepts(value) for value in rejected)


def test_dfa_exposes_valid_symbols_without_consuming_input():
    dfa = DFA("yes|no")

    assert dfa.valid_symbols() == {"y", "n"}
    assert dfa.current_state == dfa.start_state


def test_dfa_transition_updates_state_and_rejects_invalid_symbols():
    dfa = DFA("cat")
    start_state = dfa.current_state

    next_state = dfa.transition(start_state, "c")

    assert next_state != start_state
    assert dfa.current_state == next_state

    with pytest.raises(ValueError, match="No transition"):
        dfa.transition(next_state, "x")


def test_dfa_transition_rejects_unknown_state():
    dfa = DFA("a")

    with pytest.raises(ValueError, match="not in the DFA"):
        dfa.transition("missing", "a")


def test_nfa_closure_follows_epsilon_and_move_consumes_symbols():
    nfa = NFA()
    start = nfa.new_state()
    middle = nfa.new_state()
    end = nfa.new_state()
    nfa.add_transition(start, EPSILON, middle)
    nfa.add_transition(middle, "a", end)

    closure = nfa.epsilon_closure({start})

    assert closure == frozenset({start, middle})
    assert nfa.move(closure, "a") == {end}