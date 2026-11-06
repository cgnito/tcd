import json
from types import SimpleNamespace

import torch

from tcd import Decoder, JSONSchemaConstraint


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


class JsonTokenizer:
    token_texts = {
        0: "{",
        1: '"name"',
        2: ":",
        3: '"Ada"',
        4: ",",
        5: '"age"',
        6: "18",
        7: '"active"',
        8: "true",
        9: "}",
    }

    def __call__(self, prompt, return_tensors):
        return {"input_ids": torch.tensor([[0]])}

    def get_vocab(self):
        return {text: token_id for token_id, text in self.token_texts.items()}

    def decode(self, token_ids, **kwargs):
        return self.token_texts[token_ids[0]]


class JsonModel:
    token_ids = [0, 1, 2, 3, 4, 5, 2, 6, 4, 7, 2, 8, 9]

    def __init__(self):
        self.calls = 0

    def to(self, device):
        return self

    def __call__(self, **kwargs):
        logits = torch.full((1, 1, 10), -100.0)
        logits[0, 0, self.token_ids[self.calls]] = 100.0
        self.calls += 1
        return SimpleNamespace(logits=logits, past_key_values=None)


def test_public_generate_returns_schema_conforming_json(monkeypatch):
    tokenizer = JsonTokenizer()
    model = JsonModel()
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "minimum": 0},
            "active": {"type": "boolean"},
        },
        "required": ["name", "age", "active"],
        "additionalProperties": False,
    }
    monkeypatch.setattr(
        "tcd.decoder.AutoTokenizer",
        SimpleNamespace(from_pretrained=lambda *args, **kwargs: tokenizer),
    )
    monkeypatch.setattr(
        "tcd.decoder.AutoModelForCausalLM",
        SimpleNamespace(from_pretrained=lambda *args, **kwargs: model),
    )

    response = Decoder("fake-model").generate(
        prompt="Generate a user profile.",
        constraint=JSONSchemaConstraint(schema),
        max_tokens=20,
        temperature=1.0,
    )
    value = json.loads(response)

    assert value == {"name": "Ada", "age": 18, "active": True}
    assert model.calls == len(JsonModel.token_ids)