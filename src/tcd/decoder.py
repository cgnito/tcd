import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer
from .constraints import Constraint, RegexConstraint


class Decoder:
    """Generate text while masking tokens that violate a regex constraint."""

    def __init__(self, model_name="Qwen/Qwen2.5-0.5B-Instruct"):
        self.model = AutoModelForCausalLM.from_pretrained(model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, padding_side="left")
        self.model.to("cpu")


    def generate(
        self,
        prompt,
        constraint: str | Constraint,
        max_tokens=50,
        temperature=0.8,
    ):
        """Generate text that matches ``constraint``.

        Parameters
        ----------
        prompt
            Input text provided to the language model.
            constraint
                Regex pattern or constraint object used to restrict generated
                text.
        max_tokens
            Maximum number of new tokens to generate.
        temperature
            Sampling temperature applied to the masked logits.

        Returns
        -------
        str
            Generated text, stopping when the constraint is complete or the
            token limit is reached.

        Examples
        --------
        >>> decoder.generate("Is Python a programming language?", "yes|no")
        'yes'
        """

        response = ""
        if isinstance(constraint, str):
            constraint = RegexConstraint(constraint)
        constraint.bind(self.tokenizer)

        with torch.inference_mode():
            inputs = self.tokenizer(prompt, return_tensors="pt")
            outputs = self.model(**inputs, use_cache=True)

            for step in range(max_tokens):

                next_logits = outputs.logits[0, -1]
                allowed_token_ids = constraint.valid_token_ids()
                if not allowed_token_ids:
                    raise ValueError("constraint has no valid next token IDs")
                mask = torch.full_like(next_logits, float("-inf"))
                mask[allowed_token_ids] = 0
                next_logits = next_logits + mask

                probs = F.softmax(next_logits / temperature, dim=-1)
                next_token_id = torch.multinomial(probs, num_samples=1).item()

                next_token = self.tokenizer.decode([next_token_id])
                print(next_token_id, repr(next_token))
                response += next_token

                constraint.consume_token(next_token_id)
                if constraint.is_complete() or step == max_tokens - 1:
                    break

                next_input = torch.tensor([[next_token_id]])
                outputs = self.model(
                    input_ids=next_input,
                    past_key_values=outputs.past_key_values,
                    use_cache=True
                )
        return response
