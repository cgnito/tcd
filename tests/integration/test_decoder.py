from types import SimpleNamespace

import pytest
import torch

from tcd import Decoder


class FakeTokenizer:
    def __init__(self):
        self.token_texts = {0: "y", 1: "n", 2: "yes", 3: "no"}

    def __call__(self, prompt, return_tensors):
        return {"input_ids": torch.tensor([[7]])}

    def get_vocab(self):
        return {text: token_id for token_id, text in self.token_texts.items()}

    def decode(self, token_ids, **kwargs):
        return self.token_texts[token_ids[0]]


class FakeModel:
    def __init__(self, preferred_token_id):
        self.preferred_token_id = preferred_token_id
        self.calls = 0

    def to(self, device):
        return self

    def __call__(self, **kwargs):
        self.calls += 1
        logits = torch.full((1, 1, 100), -100.0)
        logits[0, 0, self.preferred_token_id] = 100.0
        return SimpleNamespace(logits=logits, past_key_values=None)


def test_decoder_masks_and_stops_on_a_complete_constraint(monkeypatch):
    tokenizer = FakeTokenizer()
    model = FakeModel(preferred_token_id=2)
    monkeypatch.setattr(
        "tcd.decoder.AutoTokenizer",
        SimpleNamespace(from_pretrained=lambda *args, **kwargs: tokenizer),
    )
    monkeypatch.setattr(
        "tcd.decoder.AutoModelForCausalLM",
        SimpleNamespace(from_pretrained=lambda *args, **kwargs: model),
    )

    decoder = Decoder("fake-model")

    response = decoder.generate("question", constraint="yes|no", max_tokens=5, temperature=1.0)

    assert response == "yes"
    assert model.calls == 1


def test_decoder_raises_when_no_token_can_continue_constraint(monkeypatch):
    tokenizer = FakeTokenizer()
    model = FakeModel(preferred_token_id=2)
    monkeypatch.setattr(
        "tcd.decoder.AutoTokenizer",
        SimpleNamespace(from_pretrained=lambda *args, **kwargs: tokenizer),
    )
    monkeypatch.setattr(
        "tcd.decoder.AutoModelForCausalLM",
        SimpleNamespace(from_pretrained=lambda *args, **kwargs: model),
    )

    decoder = Decoder("fake-model")

    with pytest.raises(ValueError, match="constraint has no valid next token IDs"):
        decoder.generate("question", constraint="z", max_tokens=1)


def test_decoder_stops_at_max_tokens_before_constraint_is_complete(monkeypatch):
    tokenizer = FakeTokenizer()
    model = FakeModel(preferred_token_id=0)
    monkeypatch.setattr(
        "tcd.decoder.AutoTokenizer",
        SimpleNamespace(from_pretrained=lambda *args, **kwargs: tokenizer),
    )
    monkeypatch.setattr(
        "tcd.decoder.AutoModelForCausalLM",
        SimpleNamespace(from_pretrained=lambda *args, **kwargs: model),
    )

    response = Decoder("fake-model").generate(
        "question",
        constraint="yes",
        max_tokens=1,
        temperature=1.0,
    )

    assert response == "y"
    assert model.calls == 1