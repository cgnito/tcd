from tcd import Decoder

decoder = Decoder()
prompt = input("Enter a prompt: ")
result = decoder.generate(prompt=prompt)
print(result)
