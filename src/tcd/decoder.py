import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer
from .constraints import Constraint, RegexConstraint


class Decoder:
    """Generate text, optionally masking tokens that violate a constraint."""

    def __init__(self, model_name="Qwen/Qwen2.5-0.5B-Instruct"):
        self.model = AutoModelForCausalLM.from_pretrained(model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, padding_side="left")
        self.model.to("cpu")


    def generate(
        self,
        prompt,
        constraint: str | Constraint | None = None,
        max_tokens=50,
        temperature=0.8,
        verbose: bool = False,
    ):
        """Generate text, optionally constrained to match ``constraint``.

        Parameters
        ----------
        prompt
            Input text provided to the language model.
        constraint
            Regex pattern, constraint object, or ``None`` for unconstrained
            generation. When ``None``, generation stops at the EOS token or
            ``max_tokens``.
        max_tokens
            Maximum number of new tokens to generate.
        temperature
            Sampling temperature applied to the logits.
        verbose
            When ``True``, print each token ID and its decoded text.

        Returns
        -------
        str
            Generated text, stopping when the constraint is complete, an EOS
            token is produced, or the token limit is reached.

        Examples
        --------
        >>> decoder.generate("Is Python a programming language?", "yes|no")
        'yes'
        """

        response = ""
        if isinstance(constraint, str):
            constraint = RegexConstraint(constraint)
        if constraint is not None:
            constraint.bind(self.tokenizer)

        with torch.inference_mode():
            inputs = self.tokenizer(prompt, return_tensors="pt")
            outputs = self.model(**inputs, use_cache=True)

            for step in range(max_tokens):

                next_logits = outputs.logits[0, -1]

                if constraint is not None:
                    allowed_token_ids = constraint.valid_token_ids()
                    if not allowed_token_ids:
                        raise ValueError("constraint has no valid next token IDs")
                    mask = torch.full_like(next_logits, float("-inf"))
                    mask[allowed_token_ids] = 0
                    next_logits = next_logits + mask

                probs = F.softmax(next_logits / temperature, dim=-1)
                next_token_id = torch.multinomial(probs, num_samples=1).item()

                next_token = self.tokenizer.decode([next_token_id])
                if verbose:
                    print(next_token_id, repr(next_token))
                response += next_token

                if constraint is not None:
                    constraint.consume_token(next_token_id)
                    if constraint.is_complete() or step == max_tokens - 1:
                        break
                else:
                    if next_token_id == self.tokenizer.eos_token_id or step == max_tokens - 1:
                        break

                next_input = torch.tensor([[next_token_id]])
                outputs = self.model(
                    input_ids=next_input,
                    past_key_values=outputs.past_key_values,
                    use_cache=True
                )
        return response
