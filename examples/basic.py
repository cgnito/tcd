from tcd import Decoder #will be back

decoder = Decoder()
prompt = input("Enter a prompt: ")
result = decoder.generate(prompt=prompt, allowed_tokens=["i", "am", "yesterday"])
print(result)
