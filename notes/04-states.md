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




we didn't talk about nfa... and the key difference there is non-determinism. a dfa operates with a state takes an input and moves to the next state(which can only be a single state) but an nfa can have multiple next states, a single state or no state for a given input. the rule is that as it takes multiple paths, if any pat gets to the accepting state, it is considered a valid match.

an an nfa also has an epislon transition, it acts has a glue. it lets an nfa move to a state without consuming a character. it acts as a concatnator.

our input is ab, we want a then b.

We can build two tiny machines.

For a:

q0 --a--> q1

For b:

q2 --b--> q3

Now how do we connect them?

We use ε:

q0 --a--> q1 --ε--> q2 --b--> q3
consume a -> move freely -> consume b




1. State: the current position of the machine
  
2. Transition: it tells us where to move next, it does 2 jobs, check if the input is valid and if valid, move to the next state
       
3. DFA: deterministic finite automaton: it is a state machine that takes in a symbol checks the transition from there and if symbol is valid moves to the next state and eventually tell us when all input so far are valid/accepted
       
4. NFA: works like a dfa but it is non-deterministic; it takes in a symbol and moves to a set of state that are valid, multiple, nono or a single state could be valid for just one input.
       
5. ε-transition: this is regarded as an empty input, it helps in concatenation. it helps in nfa to join 2 states
       
6. NFA acceptance: when a state in the set of state is an accepting state, (is this correct?)
      
7. Regex operators: they define the pattern of the regex
      
8. Regex → NFA (Thompson's construction): this is a construction algorithm that converts a regex into an NFA
       
9. ε-closure: this is the set of states that can be reached from a given state without consuming any input
       
10. NFA move: this is the set of states that can be reached from a given state by consuming a symbol
       
11. Subset construction: this is an algorithm that converts an NFA into a DFA, making a set of states in the nfa equal to a single state in the dfa. (making it deterministic)
       
how this fits into TCD: the overall state machine in tcd, will be something conceptually like this 

```python
def consume(token):
    text = tokenizer.decode([token])

    for character in text:
        state = dfa.transition(state, character)

    return state
```


so the dfa is like an abstraction in my state machine and my state machine will some how encapsulate the dfa.
