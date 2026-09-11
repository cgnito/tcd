### The generation loop

**Before the loop:**

* Initialize the model and tokenizer.
* Tokenize the input text to get **token IDs**.
* Pass the token IDs into `model()` to perform the first forward pass.
* The model converts token IDs into **embeddings** and adds positional information, then processes them through the Transformer layers.
* Set `use_cache=True` so the model returns the **KV cache** for the processed tokens.

**Inside the loop:**

* The Transformer output is passed through the **LM head**, producing **logits** — one score for every token in the model's vocabulary.
* Divide the logits by the **temperature**, then apply **softmax** to convert them into probabilities.
* **Sample** from the probability distribution to select the next token ID.
* Pass only this **new token ID** into the model along with the existing **KV cache**.
* The model reuses the cached Key/Value states instead of recomputing them, produces the next logits, and the process repeats.
