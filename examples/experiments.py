from tcd import DFA

dfa = DFA("yes|no")

print("pattern:", dfa.pattern)
print("states:", sorted(dfa.states))
print("start:", dfa.start_state)
print("accepting:", sorted(dfa.accepting_states))
print("transitions:")
for state in sorted(dfa.transitions):
    print(f"  {state} -> {dfa.transitions[state]}")

print()
print("walking 'yes' char by char:")
dfa.current_state = dfa.start_state
print(f"  start in {dfa.current_state}, accepting: {dfa.current_state in dfa.accepting_states}")
for char in "yes":
    next_state = dfa.transition(dfa.current_state, char)
    print(f"  read {char!r} -> {next_state}, accepting: {next_state in dfa.accepting_states}")

print()
print("hitting a dead end with 'yea':")
dfa.current_state = dfa.start_state
for char in "yea":
    try:
        dfa.current_state = dfa.transition(dfa.current_state, char)
        print(f"  read {char!r} -> {dfa.current_state}")
    except ValueError as e:
        print(f"  read {char!r} -> {e}")
        break

print()
for s in ["yes", "no", "yess", "ye", "", "maybe"]:
    print(f"accepts({s!r}) = {dfa.accepts(s)}")
