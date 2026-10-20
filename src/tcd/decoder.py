import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer
from .constraints import DFAConstraint


class Decoder:
    def __init__(self, model_name="Qwen/Qwen2.5-0.5B-Instruct"):
        self.model = AutoModelForCausalLM.from_pretrained(model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, padding_side="left")
        self.model.to("cpu")


    def generate(
        self,
        prompt,
        max_tokens=50,
        temperature=0.8,
        allowed_tokens: list[str] | None = None,
        constraint: DFAConstraint | None = None,
    ):

        response = ""
        allowed_token_ids = None

        if allowed_tokens is not None and constraint is not None:
            raise ValueError("allowed_tokens and constraint cannot be used together")

        if allowed_tokens is not None:
            allowed_token_ids = []
            for text in allowed_tokens:
                for token_id in self.tokenizer.encode(text):
                    allowed_token_ids.append(token_id)

            allowed_token_ids.append(self.tokenizer.eos_token_id)

        with torch.inference_mode():
            inputs = self.tokenizer(prompt, return_tensors="pt")
            outputs = self.model(**inputs, use_cache=True)

            for _ in range(max_tokens):

                next_logits = outputs.logits[0, -1]
                if constraint is not None:
                    allowed_token_ids = constraint.valid_token_ids()

                if allowed_token_ids is not None:
                    if not allowed_token_ids:
                        raise ValueError("constraint has no valid next token IDs")
                    mask = torch.full_like(next_logits, float("-inf"))
                    mask[allowed_token_ids] = 0
                    next_logits = next_logits + mask

                probs = F.softmax(next_logits / temperature, dim=-1)
                next_token_id = torch.multinomial(probs, num_samples=1).item()

                next_token = self.tokenizer.decode([next_token_id])
                print(next_token_id, repr(next_token)) # to see tokens
                response += f"{next_token} "

                if constraint is not None:
                    constraint.consume_token(next_token_id)
                    if constraint.is_complete():
                        break

                if next_token_id == self.tokenizer.eos_token_id:
                    break

                next_input = torch.tensor([[next_token_id]])
                outputs = self.model(
                    input_ids=next_input,
                    past_key_values=outputs.past_key_values,
                    use_cache=True
                )
        return response, allowed_token_ids
