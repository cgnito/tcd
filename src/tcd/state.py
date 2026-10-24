"""Build deterministic finite automata from a small regular-expression subset."""


EPSILON = ""


class NFA:
    """Represent a nondeterministic finite automaton during regex construction."""

    def __init__(self):
        self._counter: int = 0
        self.states: set[int] = set()
        self.transitions: dict[int, dict[str, set[int]]] = {}

    def new_state(self) -> int:
        """Create and return a new integer state ID."""
        state = self._counter
        self._counter += 1
        self.states.add(state)
        self.transitions[state] = {}
        return state

    def add_transition(self, src: int, symbol: str, dst: int) -> None:
        """Add a transition from ``src`` to ``dst`` for ``symbol``.

        Parameters
        ----------
        src
            Source state ID.
        symbol
            Consumed symbol, or ``EPSILON`` for an unconsumed transition.
        dst
            Destination state ID.
        """
        self.transitions[src].setdefault(symbol, set()).add(dst)

    def epsilon_closure(self, states: set[int]) -> frozenset[int]:
        """Return states reachable without consuming a symbol.

        Parameters
        ----------
        states
            NFA states from which to follow epsilon transitions.

        Returns
        -------
        frozenset[int]
            All reachable states, including the input states.
        """
        closure = set(states)
        stack = list(states)
        while stack:
            s = stack.pop()
            for t in self.transitions[s].get(EPSILON, set()):
                if t not in closure:
                    closure.add(t)
                    stack.append(t)
        return frozenset(closure)

    def move(self, states: frozenset[int], symbol: str) -> set[int]:
        """Return NFA states reachable after consuming ``symbol``.

        Parameters
        ----------
        states
            Current NFA states.
        symbol
            Symbol to consume.

        Returns
        -------
        set[int]
            States reached by the symbol before taking epsilon closures.
        """
        result = set()
        for s in states:
            result |= self.transitions[s].get(symbol, set())
        return result


# --- Thompson's construction ---
def _literal(nfa: NFA, char: str) -> tuple[int, int]:
    """Build an NFA fragment for one literal character."""
    start = nfa.new_state()
    accept = nfa.new_state()
    nfa.add_transition(start, char, accept)
    return start, accept


def _concat(nfa: NFA, f1: tuple[int, int], f2: tuple[int, int]) -> tuple[int, int]:
    """Join two fragments in sequence with an epsilon transition."""
    nfa.add_transition(f1[1], EPSILON, f2[0])
    return f1[0], f2[1]


def _alternation(nfa: NFA, f1: tuple[int, int], f2: tuple[int, int]) -> tuple[int, int]:
    """Build a fragment that accepts either of two alternatives."""
    start = nfa.new_state()
    accept = nfa.new_state()
    nfa.add_transition(start, EPSILON, f1[0])
    nfa.add_transition(start, EPSILON, f2[0])
    nfa.add_transition(f1[1], EPSILON, accept)
    nfa.add_transition(f2[1], EPSILON, accept)
    return start, accept


def _star(nfa: NFA, f: tuple[int, int]) -> tuple[int, int]:
    """Build a fragment that accepts zero or more repetitions."""
    start = nfa.new_state()
    accept = nfa.new_state()
    nfa.add_transition(start, EPSILON, f[0])
    nfa.add_transition(start, EPSILON, accept)
    nfa.add_transition(f[1], EPSILON, f[0])
    nfa.add_transition(f[1], EPSILON, accept)
    return start, accept


# --- Recursive descent regex parser ---
# Grammar:
#   expr   = term ('|' term)*
#   term   = factor+
#   factor = atom ('*')?
#   atom   = char | '(' expr ')'

class _RegexParser:
    """Parse the supported regex subset into an NFA."""
    def __init__(self, pattern: str):
        self.pattern = pattern
        self.pos = 0
        self.nfa = NFA()

    def parse(self) -> tuple[NFA, tuple[int, int]]:
        return self.nfa, self._expr()

    def _expr(self) -> tuple[int, int]:
        frag = self._term()
        while self.pos < len(self.pattern) and self.pattern[self.pos] == "|":
            self.pos += 1
            frag = _alternation(self.nfa, frag, self._term())
        return frag

    def _term(self) -> tuple[int, int]:
        frag = self._factor()
        while self.pos < len(self.pattern) and self.pattern[self.pos] not in ("|", ")"):
            frag = _concat(self.nfa, frag, self._factor())
        return frag

    def _factor(self) -> tuple[int, int]:
        frag = self._atom()
        if self.pos < len(self.pattern) and self.pattern[self.pos] == "*":
            self.pos += 1
            frag = _star(self.nfa, frag)
        return frag

    def _atom(self) -> tuple[int, int]:
        if self.pattern[self.pos] == "(":
            self.pos += 1
            frag = self._expr()
            self.pos += 1
            return frag
        char = self.pattern[self.pos]
        self.pos += 1
        return _literal(self.nfa, char)


class DFA:
    """Match strings against the supported regular-expression subset."""
    def __init__(self, pattern: str):
        self.pattern = pattern

        parser = _RegexParser(pattern)
        nfa, (nfa_start, nfa_accept) = parser.parse()

        alphabet: set[str] = {
            sym
            for trans in nfa.transitions.values()
            for sym in trans
            if sym != EPSILON
        }

        state_map: dict[frozenset[int], str] = {}
        counter = 0

        def get_name(nfa_states: frozenset[int]) -> str:
            nonlocal counter
            if nfa_states not in state_map:
                state_map[nfa_states] = f"q{counter}"
                counter += 1
            return state_map[nfa_states]

        start_closure = nfa.epsilon_closure({nfa_start})

        self.states: set[str] = set()
        self.transitions: dict[str, dict[str, str]] = {}
        self.start_state: str = get_name(start_closure)
        self.accepting_states: set[str] = set()
        self.current_state: str = self.start_state

        worklist = [start_closure]
        visited: set[frozenset[int]] = {start_closure}

        while worklist:
            current_nfa = worklist.pop()
            current_dfa = get_name(current_nfa)

            self.states.add(current_dfa)
            self.transitions[current_dfa] = {}

            if nfa_accept in current_nfa:
                self.accepting_states.add(current_dfa)

            for symbol in alphabet:
                next_nfa = nfa.epsilon_closure(nfa.move(current_nfa, symbol))
                if next_nfa:
                    next_dfa = get_name(next_nfa)
                    self.transitions[current_dfa][symbol] = next_dfa
                    if next_nfa not in visited:
                        visited.add(next_nfa)
                        worklist.append(next_nfa)

    def transition(self, state: str, symbol: str) -> str:
        """Consume a symbol and return the resulting DFA state.

        Parameters
        ----------
        state
            State from which to transition.
        symbol
            Symbol to consume.

        Returns
        -------
        str
            Destination state.

        Raises
        ------
        ValueError
            If ``state`` is unknown or no transition accepts ``symbol``.
        """
        if state not in self.states:
            raise ValueError(f"State {state} is not in the DFA's state set")
        if symbol not in self.transitions.get(state, {}):
            raise ValueError(f"No transition from {state} on '{symbol}'")
        self.current_state = self.transitions[state][symbol]
        return self.current_state

    def valid_symbols(self) -> set[str]:
        """Return symbols accepted from the current state.

        Returns
        -------
        set[str]
            Symbols with outgoing transitions from ``current_state``.
        """
        return set(self.transitions.get(self.current_state, {}))

    def accepts(self, string: str) -> bool:
        """Return whether ``string`` ends in an accepting DFA state.

        Parameters
        ----------
        string
            Text to consume from the start state.

        Returns
        -------
        bool
            ``True`` when the complete string matches the pattern.
        """
        self.current_state = self.start_state
        try:
            for char in string:
                self.current_state = self.transition(self.current_state, char)
        except ValueError:
            return False
        return self.current_state in self.accepting_states
