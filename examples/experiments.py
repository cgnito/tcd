from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct", padding_side="left")

print(tokenizer.encode("fine"))
print(tokenizer.encode("fine"))
print(tokenizer.encode("yesterday"))
print(tokenizer.encode("{"))
print(tokenizer.encode('{"name":'))




print(tokenizer.tokenize("hello, world"))

ids = tokenizer.encode("hello, world")

print(ids)

for token, token_id in zip(tokenizer.tokenize("hello, world"), ids):
    print(repr(token), token_id)

print(tokenizer.eos_token_id)
print(tokenizer("yesterday", return_tensors="pt"))
print(tokenizer("yesterday"))
for s in tokenizer.encode("yesterday"):
    print(s)
