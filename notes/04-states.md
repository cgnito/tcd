## State

**State** → the current position according to the rules. It encapsulates the current state of the automaton.

## Transition

If **state** tells us where we are, **transition** tells us where to go next when we receive a particular input.

```text
q0 = initial state
c  = input
→  = transition
```

At the initial state `q0`, when we receive `y`, we transition to `q1` because `y` is valid.

If we receive `x`, since `x` is invalid at `q0`, there is no valid state to transition to.

A transition does two things:

* checks if the input is valid from the current state
* if valid, moves the machine to the appropriate next state

```text
q0        q1        q2        ((q3))
 │         │         │         │
 │ c       │ a       │ t       │
 ↓         ↓         ↓         ↓
"c"      "ca"      "cat"    accepted
```

## Bringing this into TCD

Conceptually:

```text
current state
      ↓
look at possible next tokens
      ↓
which tokens have valid transitions?
      ↓
allow those tokens
      ↓
generate one token
      ↓
follow its transition
      ↓
move to the next state
      ↓
repeat
```

The important part is that **the model is still generating tokens**.

The state machine is used to determine which tokens are valid to generate at the current state.

## Start State

The **start state** is the state from which the automaton begins processing.

## Accepting State

The **accepting state** is a state where the automaton can stop processing and accept the input.

The input accepted so far is a valid complete match.

## DFA

**DFA** → Deterministic Finite Automaton.

It brings the concepts above together.

It is a finite state machine that processes input one symbol at a time and moves between states according to its transitions.

Simply:

> a machine that takes an input symbol, checks the transition from the current state, moves to the next state, and eventually tells us if the input is accepted.

## DFA in TCD

This is where I think the DFA comes into TCD.

Conceptually, when I have a constraint, I need some way to describe that constraint to the automaton.
For example, if my constraint is:

```text
yes or no
```

I can describe the pattern with:

```text
yes|no
```

The automaton can then conceptually look like:

```text
                  y ──> q1 ──e──> q2 ──s──> ((q3))
                 /
start → q0
                 \
                  n ──> q4 ──o──> ((q5))
```

At `q0`, the valid next inputs are `y` and `n`.

So conceptually, TCD needs to determine:

```text
current DFA state
        ↓
valid next symbols/tokens
        ↓
convert them into allowed token IDs
        ↓
mask the model's logits
        ↓
model generates one token
        ↓
send the generated token back
        ↓
DFA moves to the next state
```

The main thing I need to figure out now is **how to connect the DFA's symbol-level transitions with the model's token-level generation**.

The model generates tokens, not one character at a time, so I need a way to determine how a generated token moves through the DFA.
