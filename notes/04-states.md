## the idea

A state machine keeps track of **where we are** in a rule while reading an
input one symbol at a time.

For the pattern `cat`, the machine can look like this:

```text
q0 --c--> q1 --a--> q2 --t--> q3
                              accepting
```

`q0` is the start state. Each arrow is a transition. A transition checks
whether the next symbol is valid and, if it is, moves the machine forward.
If there is no matching arrow, the input cannot satisfy the rule.

An accepting state means that the input read so far is a complete valid match.
The machine may still have other transitions from that state if the pattern
allows a longer match.

## NFA and DFA

The implementation first builds an NFA, or **nondeterministic finite
automaton**, from the regex. An NFA can have multiple possible states after
reading a symbol. It can also use an epsilon transition, written `ε`, which
moves to another state without consuming input.

For example, concatenating `a` and `b` can use epsilon as glue:

```text
q0 --a--> q1 --ε--> q2 --b--> q3
```

The NFA is useful for building regex pieces. The decoder needs a simpler
machine, so the code converts the NFA into a DFA, or **deterministic finite
automaton**. A DFA has exactly one next state for a given state and symbol.

The conversion is called subset construction. Each DFA state represents a set
of NFA states that could currently be active. The code follows epsilon
transitions with `epsilon_closure()`, follows real symbols with `move()`, and
uses those sets to create named states such as `q0`, `q1`, and `q2`.

## how `state.py` builds the machine

`_RegexParser` reads the pattern recursively. It supports literals,
concatenation, alternation with `|`, grouping with parentheses, and repetition
with `*`.

Each parser operation adds a small NFA fragment:

```text
literal:      a       -> start --a--> accept
alternation:  a|b     -> branch to either fragment
concatenation: ab     -> connect fragments with ε
repetition:   a*      -> add a loop and an empty path
```

`DFA.__init__()` then performs subset construction. It starts with the epsilon
closure of the NFA start state and explores every reachable set of NFA states.
For each set and each real symbol, it creates one DFA transition.

It stores:

```python
self.start_state       # where matching begins
self.current_state     # where matching currently is
self.transitions        # state -> symbol -> next state
self.accepting_states   # states where the input is complete
```

## reading input with the DFA

`DFA.transition(state, symbol)` checks the transition table. If the symbol is
valid, it updates `current_state` and returns the next state. If it is invalid,
it raises `ValueError`.

`DFA.valid_symbols()` returns the symbols that have outgoing transitions from
the current state. This is what the constraint layer uses to find possible next
characters.

`DFA.accepts(string)` resets the machine to the start state, consumes the
whole string, and returns `True` only if the final state is accepting.

## how this connects to tcd

The DFA reads characters, but the language model generates token IDs. The
constraint layer decodes each candidate token and tests all of its characters:

```text
token ID -> decoded text -> DFA transitions
```

For `yes|no`, the DFA starts with valid symbols `y` and `n`. A token decoding
to `yes` is valid only if all three transitions succeed:

```text
q0 --y--> q1 --e--> q2 --s--> q3
                              accepting
```

After the decoder selects a token, the constraint commits its decoded text to
the DFA. When the DFA reaches an accepting state, generation can stop.

This gives the overall flow:

```text
regex pattern
    -> NFA
    -> DFA
    -> valid next symbols
    -> valid token IDs
    -> logit mask
    -> sampled token
    -> DFA state update
    -> accept or continue
```
