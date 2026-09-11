from linecache import cache

import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "Qwen/Qwen2.5-0.5B-Instruct"

model = AutoModelForCausalLM.from_pretrained(model_name)
tokenizer = AutoTokenizer.from_pretrained(model_name, padding_side="left")
model.to("cpu")

prompt = input("prompt: ")
response = ""

with torch.inference_mode():
    inputs = tokenizer(prompt, return_tensors="pt")
    outputs = model(**inputs, use_cache=True)

    for _ in range(50):

        next_logits = outputs.logits[0, -1]  # shape: (vocab_size,)
        temperature = 0.7
        probs = F.softmax(next_logits / temperature, dim=-1)
        next_token_id = torch.multinomial(probs, num_samples=1).item()

        #next_token_id = torch.argmax(next_logits).item()

        next_token = tokenizer.decode([next_token_id])
        response += next_token
        next_input = torch.tensor([[next_token_id]])

        outputs = model(
            input_ids=next_input,
            past_key_values=outputs.past_key_values,
            use_cache=True
        )

    print("-", response)
