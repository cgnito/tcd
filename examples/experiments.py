from tcd import DFA

dfa = DFA("hello")
print(dfa.transitions)
print(dfa.transition("q0", "h"))
