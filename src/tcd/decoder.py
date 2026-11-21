import time

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

    def _eos_token_ids(self) -> set[int]:
        """Return every EOS ID configured by the model or tokenizer."""
        eos_ids: set[int] = set()

        generation_config = getattr(self.model, "generation_config", None)
        configured = getattr(generation_config, "eos_token_id", None)
        if isinstance(configured, int):
            eos_ids.add(configured)
        elif configured is not None:
            eos_ids.update(configured)

        tokenizer_eos = getattr(self.tokenizer, "eos_token_id", None)
        if isinstance(tokenizer_eos, int):
            eos_ids.add(tokenizer_eos)

        return eos_ids

    def generate(
        self,
        prompt,
        constraint: str | Constraint | None = None,
        max_tokens=50,
        temperature=0.8,
        verbose: bool = False,
        _metrics: dict | None = None,
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
        _metrics
            Optional dict populated with timing data before returning. Keys:
            ``tokens_generated`` (int), ``finish_reason`` (str),
            ``bind_time_s`` (float), ``valid_token_ids_time_s`` (float),
            ``consume_token_time_s`` (float). ``finish_reason`` is one of
            ``"constraint_complete"``, ``"eos"``, or ``"max_tokens"``.
            The last three are ``0.0`` for unconstrained generation.
            ``bind_time_s`` reflects a cold-start cost: in this benchmark a
            new constraint is created per call, so vocabulary indexing is paid
            every time. Pass an empty dict to collect metrics; omit for normal
            use.

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
        tokens_generated = 0
        finish_reason = "max_tokens"
        bind_time_s = 0.0
        valid_token_ids_time_s = 0.0
        consume_token_time_s = 0.0

        if isinstance(constraint, str):
            constraint = RegexConstraint(constraint)
        if constraint is not None:
            _t = time.perf_counter()
            constraint.bind(self.tokenizer)
            bind_time_s = time.perf_counter() - _t

        eos_token_ids = self._eos_token_ids()

        with torch.inference_mode():
            inputs = self.tokenizer(prompt, return_tensors="pt")
            outputs = self.model(**inputs, use_cache=True)

            for step in range(max_tokens):

                next_logits = outputs.logits[0, -1]

                if constraint is not None:
                    _t = time.perf_counter()
                    allowed_token_ids = constraint.valid_token_ids()
                    valid_token_ids_time_s += time.perf_counter() - _t
                    if not allowed_token_ids:
                        raise ValueError("constraint has no valid next token IDs")
                    mask = torch.full_like(next_logits, float("-inf"))
                    mask[allowed_token_ids] = 0
                    next_logits = next_logits + mask

                probs = F.softmax(next_logits / temperature, dim=-1)
                next_token_id = torch.multinomial(probs, num_samples=1).item()
                tokens_generated += 1

                if constraint is None and next_token_id in eos_token_ids:
                    finish_reason = "eos"
                    break

                next_token = self.tokenizer.decode([next_token_id])
                if verbose:
                    print(next_token_id, repr(next_token))
                response += next_token

                if constraint is not None:
                    _t = time.perf_counter()
                    constraint.consume_token(next_token_id)
                    consume_token_time_s += time.perf_counter() - _t
                    if constraint.is_complete():
                        finish_reason = "constraint_complete"
                        break
                    if step == max_tokens - 1:
                        finish_reason = "max_tokens"
                        break
                else:
                    if step == max_tokens - 1:
                        finish_reason = "max_tokens"
                        break

                next_input = torch.tensor([[next_token_id]])
                outputs = self.model(
                    input_ids=next_input,
                    past_key_values=outputs.past_key_values,
                    use_cache=True
                )

        if _metrics is not None:
            _metrics["tokens_generated"] = tokens_generated
            _metrics["finish_reason"] = finish_reason
            _metrics["bind_time_s"] = bind_time_s
            _metrics["valid_token_ids_time_s"] = valid_token_ids_time_s
            _metrics["consume_token_time_s"] = consume_token_time_s

        return response
