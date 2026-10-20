EPSILON = ""  # epsilon: move to another state without consuming input


class NFA:
    """
    Nondeterministic Finite Automaton.

    States are plain integers (0, 1, 2, ...) assigned by a counter.
    Transitions map (state, symbol) -> set of next states.
    EPSILON transitions are stored under the key "" (empty string).
    """

    def __init__(self):
        self._counter: int = 0
        self.states: set[int] = set()
        self.transitions: dict[int, dict[str, set[int]]] = {}

    def new_state(self) -> int:
        state = self._counter
        self._counter += 1
        self.states.add(state)
        self.transitions[state] = {}
        return state

    def add_transition(self, src: int, symbol: str, dst: int) -> None:
        self.transitions[src].setdefault(symbol, set()).add(dst)

    def epsilon_closure(self, states: set[int]) -> frozenset[int]:
        """
        All NFA states reachable from `states` via epsilon transitions alone.
        Uses a stack to follow every epsilon arrow until no new states appear.
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
        """All NFA states reachable from `states` by consuming `symbol`."""
        result = set()
        for s in states:
            result |= self.transitions[s].get(symbol, set())
        return result


# --- Thompson's construction ---
# Each function below takes an NFA and returns a (start, accept) pair —
# a "fragment" wired into the NFA. Fragments are composed to match the
# structure of the regex.
#
# The key idea behind Thompson's construction: Every regex piece gives me a little fragment
# with a start and an accept state. Then i connect those fragments together via epsilon transitions. (_concat)

def _literal(nfa: NFA, char: str) -> tuple[int, int]:
    """a  →  (start) --a--> (accept)"""
    start = nfa.new_state()
    accept = nfa.new_state()
    nfa.add_transition(start, char, accept)
    return start, accept


def _concat(nfa: NFA, f1: tuple[int, int], f2: tuple[int, int]) -> tuple[int, int]:
    """
    ab  →  connect accept of f1 to start of f2 via epsilon.
    The overall fragment runs from f1's start to f2's accept.
    """
    nfa.add_transition(f1[1], EPSILON, f2[0])
    return f1[0], f2[1]


def _alternation(nfa: NFA, f1: tuple[int, int], f2: tuple[int, int]) -> tuple[int, int]:
    """
    a|b  →  new start branches (via epsilon) into both fragments,
            both fragments merge (via epsilon) into a new accept.
    """
    start = nfa.new_state()
    accept = nfa.new_state()
    nfa.add_transition(start, EPSILON, f1[0])
    nfa.add_transition(start, EPSILON, f2[0])
    nfa.add_transition(f1[1], EPSILON, accept)
    nfa.add_transition(f2[1], EPSILON, accept)
    return start, accept


def _star(nfa: NFA, f: tuple[int, int]) -> tuple[int, int]:
    """
    a*  →  new start can skip directly to accept (zero times),
           or enter the fragment. After the fragment, loop back
           or exit to accept.
    """
    start = nfa.new_state()
    accept = nfa.new_state()
    nfa.add_transition(start, EPSILON, f[0])   # enter the fragment
    nfa.add_transition(start, EPSILON, accept)  # skip (zero repetitions)
    nfa.add_transition(f[1], EPSILON, f[0])    # loop back
    nfa.add_transition(f[1], EPSILON, accept)  # exit after one+ repetitions
    return start, accept


# --- Recursive descent regex parser ---
# Grammar:
#   expr   = term ('|' term)*
#   term   = factor+
#   factor = atom ('*')?
#   atom   = char | '(' expr ')'

class _RegexParser:
    """
    Turns a regex pattern into a sequence of construction operations.
    """
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
            self.pos += 1        # consume '('
            frag = self._expr()
            self.pos += 1        # consume ')'
            return frag
        char = self.pattern[self.pos]
        self.pos += 1
        return _literal(self.nfa, char)


class DFA:
    """
    A deterministic finite automaton (DFA) that matches a regex pattern.
    """
    def __init__(self, pattern: str):
        self.pattern = pattern

        # Step 1: parse the regex and build an NFA via Thompson's construction
        parser = _RegexParser(pattern)
        nfa, (nfa_start, nfa_accept) = parser.parse()

        # Collect every real symbol (everything that isn't epsilon)
        alphabet: set[str] = {
            sym
            for trans in nfa.transitions.values()
            for sym in trans
            if sym != EPSILON
        }

        # Step 2: subset construction — turn the NFA into a DFA.
        # Each DFA state is a frozenset of NFA states (all the states the
        # NFA could simultaneously be in). We name them q0, q1, q2, ...
        # in the order we first encounter them.

        # The key idea of subset construction: the next DFA state represents every NFA state that could be active after
        # reading the next character and following all possible epsilon transitions.

        state_map: dict[frozenset[int], str] = {}
        counter = 0

        def get_name(nfa_states: frozenset[int]) -> str:
            nonlocal counter
            if nfa_states not in state_map:
                state_map[nfa_states] = f"q{counter}"
                counter += 1
            return state_map[nfa_states]

        # The DFA starts at the epsilon-closure of the NFA's start state
        start_closure = nfa.epsilon_closure({nfa_start})

        self.states: set[str] = set()
        self.transitions: dict[str, dict[str, str]] = {}
        self.start_state: str = get_name(start_closure)
        self.accepting_states: set[str] = set()
        self.current_state: str = self.start_state

        # BFS over reachable DFA states
        worklist = [start_closure]
        visited: set[frozenset[int]] = {start_closure}

        while worklist:
            current_nfa = worklist.pop()
            current_dfa = get_name(current_nfa)

            self.states.add(current_dfa)
            self.transitions[current_dfa] = {}

            # If any NFA accept state is in this DFA state, it's accepting
            if nfa_accept in current_nfa:
                self.accepting_states.add(current_dfa)

            for symbol in alphabet:
                # Where do all these NFA states go on this symbol?
                next_nfa = nfa.epsilon_closure(nfa.move(current_nfa, symbol))
                if next_nfa:  # empty set means no transition (dead state)
                    next_dfa = get_name(next_nfa)
                    self.transitions[current_dfa][symbol] = next_dfa
                    if next_nfa not in visited:
                        visited.add(next_nfa)
                        worklist.append(next_nfa)

    def transition(self, state: str, symbol: str) -> str:
        if state not in self.states:
            raise ValueError(f"State {state} is not in the DFA's state set")
        if symbol not in self.transitions.get(state, {}):
            raise ValueError(f"No transition from {state} on '{symbol}'")
        self.current_state = self.transitions[state][symbol]
        return self.current_state

    def valid_symbols(self) -> set[str]:
        """Return the symbols that have transitions from the current state."""
        return set(self.transitions.get(self.current_state, {}))

    def accepts(self, string: str) -> bool:
        """Run the full string through the DFA and return whether it's accepted."""
        self.current_state = self.start_state
        try:
            for char in string:
                self.current_state = self.transition(self.current_state, char)
        except ValueError:
            return False
        return self.current_state in self.accepting_states
