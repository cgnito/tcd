from types import SimpleNamespace

import torch

from tcd import Decoder


class PublicApiTokenizer:
    def __call__(self, prompt, return_tensors):
        return {"input_ids": torch.tensor([[0]])}

    def get_vocab(self):
        return {"cat": 0, "dog": 1}

    def decode(self, token_ids, **kwargs):
        return {0: "cat", 1: "dog"}[token_ids[0]]


class PublicApiModel:
    def to(self, device):
        return self

    def __call__(self, **kwargs):
        logits = torch.tensor([[[5.0, 1.0]]])
        return SimpleNamespace(logits=logits, past_key_values=None)


def test_public_generate_accepts_a_pattern_string_without_manual_constraint_setup(monkeypatch):
    monkeypatch.setattr(
        "tcd.decoder.AutoTokenizer",
        SimpleNamespace(from_pretrained=lambda *args, **kwargs: PublicApiTokenizer()),
    )
    monkeypatch.setattr(
        "tcd.decoder.AutoModelForCausalLM",
        SimpleNamespace(from_pretrained=lambda *args, **kwargs: PublicApiModel()),
    )

    response = Decoder("fake-model").generate(
        prompt="Choose an animal",
        constraint="cat|dog",
        max_tokens=1,
        temperature=1.0,
    )

    assert response == "cat"