import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "openai-community/gpt2"

model = AutoModelForCausalLM.from_pretrained(model_name)
tokenizer = AutoTokenizer.from_pretrained(model_name, padding_side="left")
model.to("cpu")

inputs = tokenizer("Hello, how are you?", return_tensors="pt")

outputs = model(**inputs)
next_logits = outputs.logits[0, -1]  # shape: (vocab_size,)

temperature = 0.7
probs = F.softmax(next_logits / temperature, dim=-1)
next_token_id = torch.multinomial(probs, num_samples=1).item()
next_token = tokenizer.decode(next_token_id)

print(next_token)
