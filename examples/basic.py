from tcd import Decoder

decoder = Decoder()
prompt = input("Enter a prompt: ")
result = decoder.generate(prompt=prompt, constraint="yes|no|nigeria")
print(result)