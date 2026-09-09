## hardware & model setup

My laptop as of building this project:

* **CPU:** Intel Core i7-8650U — 4 physical cores, 8 threads
* **GPU:** NVIDIA GeForce MX130 — 2 GB VRAM
* **RAM:** 8 GB

Since the MX130 has only 2 GB of VRAM, I’ll run a tiny model, **`sshleifer/tiny-gpt2`**, on the CPU rather than the GPU.

The basic flow is:

```text
Hugging Face
    ↓
download model files → storage
    ↓
load model → RAM
    ↓
CPU → inference
```

The model consists of:

```text
MODEL
├── architecture
├── weights
├── tokenizer
│   ├── vocabulary
│   └── tokenization rules
└── configuration
```

* **Architecture:** Defines the structure and computation of the model.
* **Weights:** Learned parameters obtained during training.
* **Tokenizer:** Converts text ↔ tokens.

  * **Vocabulary:** The set of tokens the tokenizer can represent.
  * **Tokenization rules:** Rules for splitting text into tokens.
* **Configuration:** Describes the model, such as the number of layers, hidden dimension, attention heads, vocabulary size, and context length.

During inference, the CPU performs the model's computations, such as matrix multiplication, attention, and activation functions.
