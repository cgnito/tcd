# how an autoregressive llm generates text

when you type a prompt into an llm such as:

```
the cat sat
```

the model does not generate the entire continuation at once.

instead, it repeatedly answers one question:

> given everything that has appeared so far, what token should come next?
> 

suppose the model predicts `on`.

the context changes from:

```
the cat sat
```

to:

```
the cat sat on
```

the model then looks at this expanded context and predicts again. perhaps the next token is `the`, so the context becomes:

```
the cat sat on the
```

then it predicts again and perhaps produces `mat`.

```
the cat sat on the mat
```

this repeated process is the basic idea behind **autoregressive generation**.

```
┌───────────────────────────────┐
│        current context        │
│                               │
│         "the cat sat"         │
└───────────────┬───────────────┘
                │
                ▼
        predict next token
                │
                ▼
              "on"
                │
                ▼
┌───────────────────────────────┐
│         new context           │
│                               │
│       "the cat sat on"        │
└───────────────┬───────────────┘
                │
                ▼
        predict next token
                │
                ▼
             "the"
                │
                ▼
              repeat
```

the word **autoregressive** describes this dependence on previously generated elements. in a sequence

```
x₁, x₂, x₃, x₄, ...
```

the general idea is:

```
x₁                    → predict x₂

x₁, x₂                → predict x₃

x₁, x₂, x₃            → predict x₄

x₁, x₂, x₃, x₄        → predict x₅
```

for an autoregressive llm, those sequence elements are tokens.

so we can summarize the idea as:

> an autoregressive llm predicts the next token based on the tokens that came before it, adds the newly generated token to the context, and repeats the process.
> 

but that immediately creates a bigger question.

**how does the model go from ordinary text like `"the cat sat"` to actually deciding that `"on"` should come next?**

---

## from text to tokens

the process starts with ordinary text.

```
"the cat sat"
       │
       ▼
┌──────────────┐
│   tokenizer  │
└──────────────┘
       │
       ▼
["the", "cat", "sat"]
```

a **token** is a piece of text that the model treats as one unit. a token does not necessarily equal a complete word. depending on the tokenizer, it could be a whole word, part of a word, punctuation, or another piece of text.

the **tokenizer** is the program responsible for breaking text into tokens and converting those tokens into numbers the model can work with.

---

## from tokens to token id

each token belongs to a fixed **vocabulary**.

the vocabulary is essentially a mapping between tokens and integer ids:

```
┌───────────────┐
│   vocabulary  │
├───────────────┤
│ 0 → <eos>     │
│ 1 → the       │
│ 2 → cat       │
│ 3 → dog       │
│ 4 → sat       │
│ 5 → ran       │
│ 6 → on        │
│ 7 → mat       │
└───────────────┘
```

real llm vocabularies are much larger, but the basic principle is the same. every token has an integer associated with it. that integer is called its **token id**.

so our tokens:

```
["the", "cat", "sat"]
```

might become:

```
[1, 2, 4]
```

because:

```
1 → "the"
2 → "cat"
4 → "sat"
```

---

## from token ids to embeddings

the model contains something called an **embedding matrix**.

you can think of it as a giant table containing a vector for every token in the vocabulary.

simplified:

```
token id       token        vector
------------------------------------------------
0              <eos>        [ 0.12, -0.31,  0.77, ...]
1              the          [ 0.42,  0.18, -0.25, ...]
2              cat          [-0.13,  0.91,  0.44, ...]
3              dog          [-0.10,  0.87,  0.41, ...]
4              sat          [ 0.31, -0.22,  0.63, ...]
```

so when the model receives:

```
[1, 2, 4]
```

it uses those ids to **look up the corresponding vectors**.

```
1 ──→ [vector for "the"]
2 ──→ [vector for "cat"]
4 ──→ [vector for "sat"]
```

these vectors are called **token embeddings**.

an embedding is a numerical representation of something in a high-dimensional vector space. during training, the model learns these vectors so that tokens acquire useful relationships within the model's representation space.

you can think of it like coordinates in a very large space. however, unlike a simple 2d graph where one axis might clearly mean "size" and another "color," the dimensions of neural-network embeddings generally do not correspond to simple human-labeled properties. information is distributed across many dimensions.

---

## what an embedding really is

an embedding is a numerical representation of something as a vector.

a vector is simply an ordered collection of numbers:

```
[0.12, -0.83, 0.41, 0.09, 0.27, ...]
```

one helpful way to build intuition is to imagine a two-dimensional coordinate system.

suppose our embeddings contained only two numbers.

we could draw them as points:

```
                    dimension 2
                         ↑
                         │
                         │
                 dog •   │   • cat
                         │
                         │
                         │
            car •        │
                         │
─────────────────────────┼────────────────────→ dimension 1
                         │
```

in this imaginary example, `"cat"` and `"dog"` might end up closer together than `"cat"` and `"car"` because their learned representations have more similarities.

real embeddings are not usually two-dimensional, though.

an llm might represent a token using hundreds or thousands of numbers:

```
"cat"

   ↓

[0.12, -0.83, 0.41, 1.02, -0.17, 0.63, ...]
```

mathematically, we can imagine this vector as a point in a space with hundreds or thousands of dimensions.

---

## the transformer receives token representations

the token embeddings are then passed through the **transformer**.

```
┌──────────────────────┐
│       transformer    │
│                      │
│  self-attention      │
│  feed-forward layers │
│  ...                 │
└──────────────────────┘
```

the transformer processes the token representations together and builds **contextual representations**.

this is important because a token's meaning can depend on the tokens around it.

for example:

```
the bank approved my loan
```

and:

```
the boat reached the river bank
```

the token "bank" starts with the same token embedding in both cases, but the transformer uses the surrounding context to produce different contextual representations.

this is where self-attention becomes important: tokens can incorporate information from other relevant tokens in the sequence.

---

## the lm head turns the representation into vocabulary scores

after the transformer processes the sequence, the resulting contextual representation is passed to the **language model head (lm head)**.

```
┌──────────────────────┐
│       transformer    │
└──────────────────────┘
          │
          ▼
 contextual representation
          │
          ▼
┌──────────────────────┐
│        lm head       │
└──────────────────────┘
          │
          ▼
        logits
```

the lm head produces a score for every possible token in the vocabulary.

if the vocabulary contains 50,000 tokens, the model produces roughly 50,000 scores for the next-token prediction.

these raw scores are called **logits**.

for example:

```
"the"  →  2.1
"cat"  →  0.4
"on"   →  5.7
"dog"  →  1.2
...
```

the logits are **not probabilities yet**. they are simply the model's raw scores for how suitable each possible next token is.

---

## from logits to probabilities

the logits are passed through **softmax**, which converts the scores into a probability distribution over the vocabulary.

```
logits
  │
  ▼
┌──────────────┐
│   softmax    │
└──────────────┘
  │
  ▼
probabilities
```

now the model has something like:

```
"on"   → 0.72
"the"  → 0.12
"dog"  → 0.04
"cat"  → 0.02
...
```

the probabilities sum to 1 and represent the model's predicted distribution for the next token.

**temperature** can be applied to the logits before softmax. it controls how concentrated or spread out the resulting probability distribution is.

a lower temperature makes the distribution sharper, making high-scoring tokens more dominant. a higher temperature makes it flatter, giving lower-scoring tokens a greater chance of being selected.

---

## from probabilities to sampling

the model now needs to actually choose one token.

this is where **sampling** comes in.

```
probability distribution
          │
          ▼
      sampling
          │
          ▼
     next token
```

the model can simply choose the highest-probability token (**greedy decoding**), or it can sample from the distribution so that other plausible tokens sometimes have a chance of being selected.

suppose it selects:

```
"on"
```

that token is added to the context:

```
the cat sat on
```

the entire process then happens again to predict the next token.

---

## the autoregressive loop

this is what makes the model **autoregressive**.

```
                         ┌───────────────────────┐
                         │       CONTEXT         │
                         │                       │
                         │  "the cat sat"        │
                         └───────────┬───────────┘
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │       TOKENIZER       │
                         │                       │
                         │  text → tokens        │
                         │       → token ids     │
                         └───────────┬───────────┘
                                     │
                                     ▼
                              token ids
                              [1, 2, 4]
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │   EMBEDDING LOOKUP    │
                         │                       │
                         │  token id → vector   │
                         └───────────┬───────────┘
                                     │
                                     ▼
                           token embeddings
                         [0.12, -0.83, ...]
                                     │
                                     ▼
                  ┌────────────────────────────────┐
                  │           TRANSFORMER           │
                  │                                │
                  │  self-attention + feed-forward │
                  │                                │
                  │  incorporates context from     │
                  │  other tokens                  │
                  └───────────────┬────────────────┘
                                  │
                                  ▼
                     contextual representation
                                  │
                                  ▼
                         ┌───────────────────────┐
                         │        LM HEAD        │
                         │                       │
                         │ representation →      │
                         │ vocabulary scores     │
                         └───────────┬───────────┘
                                     │
                                     ▼
                                  logits
                        [2.1, 0.4, 5.7, 1.2, ...]
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │      TEMPERATURE      │
                         │                       │
                         │ adjusts the logits    │
                         │ before softmax        │
                         └───────────┬───────────┘
                                     │
                                     ▼
                             adjusted logits
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │        SOFTMAX        │
                         │                       │
                         │  logits → probabilities│
                         └───────────┬───────────┘
                                     │
                                     ▼
                         probability distribution
                       ┌─────────────────────────────┐
                       │ "on"   → 0.72               │
                       │ "the"  → 0.12               │
                       │ "dog"  → 0.04               │
                       │ ...                          │
                       └──────────────┬──────────────┘
                                      │
                                      ▼
                         ┌───────────────────────┐
                         │       SAMPLING        │
                         │                       │
                         │ probability           │
                         │ distribution → token  │
                         └───────────┬───────────┘
                                     │
                                     ▼
                              next token
                                 "on"
                                     │
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │   ADD TO CONTEXT      │
                         │                       │
                         │ "the cat sat" + "on"  │
                         └───────────┬───────────┘
                                     │
                                     │
                                     └──────────────────┐
                                                        │
                                                        ▼
                                              ┌───────────────────┐
                                              │   PREDICT NEXT    │
                                              │      TOKEN        │
                                              └─────────┬─────────┘
                                                        │
                                                        └───────→ repeat
                                                                  until
                                                                  generation
                                                                  stops
```

the newly generated token becomes part of the context for the next prediction. the model keeps repeating this process, using everything generated so far as additional context, until it reaches an appropriate stopping point such as an end-of-sequence token or a maximum generation length.

so the core idea is simply:

```
predict → append → predict → append → predict → ...
```

and that repeated next-token prediction is how an autoregressive llm turns a prompt into a complete piece of generated text.

---

## the complete mental model

```
text
  │
  ▼
┌──────────────┐
│   tokenizer  │
└──────────────┘
  │
  ▼
token ids
  │
  ▼
┌──────────────────┐
│ embedding lookup │
└──────────────────┘
  │
  ▼
token embeddings
  │
  ▼
┌──────────────────┐
│    transformer   │
└──────────────────┘
  │
  ▼
contextual representation
  │
  ▼
┌──────────────────┐
│      lm head     │
└──────────────────┘
  │
  ▼
logits
  │
  ▼
temperature + softmax
  │
  ▼
probability distribution
  │
  ▼
sampling
  │
  ▼
next token
  │
  └──────→ add to context → repeat
```

the key distinctions to remember are:

- **token** → a piece of text treated as one unit
- **tokenizer** → converts text into tokens and token ids
- **vocabulary** → the collection of tokens and their ids
- **token id** → an integer identifying a token
- **embedding** → a learned vector representation of a token
- **transformer** → processes representations and incorporates context
- **contextual representation** → a representation of a token after considering its context
- **lm head** → maps the model's final representation to vocabulary scores
- **logits** → raw scores for possible next tokens
- **softmax** → converts logits into probabilities
- **temperature** → controls how sharp or flat the probability distribution is
- **sampling** → selects the actual next token
- **autoregressive generation** → repeatedly predicts and appends the next token

i'm also learning, so this is my current understanding of how autoregressive llms generate text.
