## Hardware & Model Setup

My laptop:

* **CPU:** Intel Core i7-8650U — 4 cores, 8 threads
* **GPU:** NVIDIA GeForce MX130 — 2 GB VRAM
* **RAM:** 8 GB

### Model

I'm using `Qwen/Qwen2.5-0.5B-Instruct`.

I initially considered `sshleifer/tiny-gpt2`, but it is a heavily reduced model mainly intended for testing and examples, also tried using `openai-community/gpt2` but it is also a heavily reduced model. For TCD, I want to work with a real, small autoregressive language model that produces meaningful next-token probabilities.

I don't need a large LLM for this project. GPT-2 is small enough to run locally while still giving me a real model to work with.

### Why CPU?

My MX130 can run GPU workloads, but it is an older NVIDIA GPU and can run into compatibility issues with newer PyTorch/CUDA versions. Since GPT-2 is small and this project is for experimentation, CPU is more than sufficient.

I'm therefore using the **CPU version of PyTorch**, so CUDA is not involved in my inference.

The setup is:

```text
model: GPT-2
parameters: 124M
tokenizer: GPT-2 tokenizer
framework: PyTorch
device: CPU
```

The basic flow is:

```text
Hugging Face
    ↓
download model
    ↓
load model into RAM
    ↓
PyTorch runs inference on CPU
    ↓
GPT-2 produces logits
    ↓
TCD controls token selection
```

I'm not using `model.generate()`. I want to understand and build the generation process rather than simply calling a high-level generation API.

Eventually, the constraint will sit between the model's logits and the token selection step, allowing TCD to prevent the model from selecting tokens that would make the output invalid.
