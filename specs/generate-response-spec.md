# Spec: `generate_response()`

**File:** `generator.py`
**Status:** Spec incomplete — fill in all blank fields before implementing

---

## Purpose

Given a user query and a list of retrieved rule chunks, generate a response that directly answers the question using only the retrieved text as context. The response must be grounded — it should not draw on the model's general knowledge of board games, only on what was retrieved.

---

## Input / Output Contract

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | `str` | The user's original question |
| `retrieved_chunks` | `list[dict]` | Ranked list of chunks from `retrieve()`, each with `"text"`, `"game"`, and `"distance"` |

**Output:** `str`

A plain string containing the response to show the user. The response should:
- Answer the question using only the retrieved rule text
- Identify which game the answer comes from
- Acknowledge clearly when the answer is not found in the loaded rules

Returns a fallback string (not an error) when `retrieved_chunks` is empty.

---

## Design Decisions

### Context formatting

```
One labeled block per chunk, separated by a delimiter:

    [Catan]
    Settlements cost 1 Brick + 1 Lumber + 1 Grain + 1 Wool...

    ---

    [Risk]
    The attacker rolls up to 3 dice...

- Game label IN: each block is prefixed with its [game] so the citation
  instruction has something concrete to cite. Without the label the model has
  no reliable way to name the source.
- Distance score OUT: distance is a retrieval-internal cosine float. It's noise
  to the LLM and risks being parroted into the answer ("distance 0.47"). It adds
  nothing to answering the question.
- Delimiter between chunks (--- or numbered blocks): chunks can start/end
  mid-word (size-based chunking), so a clear separator stops two chunks from
  bleeding into one run-on context.
```

---

### System prompt — grounding instruction

```
"You are a board game rules assistant. Answer the question using ONLY the rules
in the provided context. Do not use any outside knowledge of these or any other
board games. If the context does not contain the answer, say you cannot find it
in the loaded rules — do not guess, infer, or fill in gaps."

The critical clause is the last one: "if it's not in the context, say so."
That is what turns a confident hallucination into an honest "I don't know,"
which is the entire point of grounding — a wrong-but-confident rules answer is
worse than admitting the rule isn't loaded.
```

---

### System prompt — citation instruction

```
"State which game your answer comes from, using the bracketed game labels in
the context (e.g. [Catan]). If your answer draws on more than one game, name
each game it applies to."

This depends on the context formatting (above) keeping the [game] labels — the
model cites by reading those labels back, so the two decisions are linked.
```

---

### Fallback behavior

```
There are TWO distinct "not found" cases, handled by two different mechanisms:

(a) No chunks retrieved at all (retrieved_chunks is empty). This is a Python
    guard already in generator.py, returning the exact string:

    "I couldn't find anything relevant in the loaded rule books. Try rephrasing
     your question — or check that your ingestion pipeline is working."

(b) Chunks WERE retrieved but none actually contain the answer. There is no
    code branch for this — it is handled by the grounding instruction in the
    system prompt, which tells the model to say it cannot find the answer in the
    loaded rules. The exact wording is the model's, constrained by that prompt.

Keeping these separate matters: (a) is a pipeline/empty-store signal, (b) is a
relevance signal. They should not be collapsed into one message.
```

---

### Handling low-relevance chunks

```
Decision: pass all retrieved chunks in (no distance filtering here), and rely
on the grounding instruction to ignore irrelevant context.

Why: retrieve() already returns only N_RESULTS (3) chunks and deliberately
applies no threshold. Adding a second, separate threshold here would create two
competing relevance decisions in the system that are hard to reason about.

Tradeoffs:
- Pass all (chosen): simpler and consistent with retrieve(). The grounding
  prompt is responsible for not using weak chunks. Risk: a weak chunk could
  still mislead the model.
- Filter by distance here: cleaner context, but cosine cutoffs are fragile and
  dataset-specific, AND filtering could remove every chunk — leaving an empty
  context that would then need to be routed into the fallback path.

If filtering is ever added, it belongs in ONE place (preferably retrieve), not
split across both functions.
```

---

### Message structure

```
Two messages:

  system : the stable behavioral rules that don't change between requests —
           persona + grounding instruction + citation instruction.

  user   : the dynamic, per-request payload — the formatted context block
           (the labeled chunks) followed by the actual user query.

messages = [
    {"role": "system", "content": <persona + grounding + citation>},
    {"role": "user",   "content": <context block> + <query>},
]

Rationale: behavioral instructions go in system so they aren't buried inside
the data and are clearly separated from input. The retrieved context is
request-specific input, so it belongs in the user message alongside the
question it's meant to answer.
```

---

## Implementation Notes

**Test query and response:**

```
Query: How many resource cards do I lose if I have too many when a 7 is rolled?
Response: "[Catan] If you have more than 7 resource cards in hand when a 7 is
          rolled, you must discard half of them (rounded down)..." (then gives
          worked examples: 10 cards -> discard 5, 9 cards -> discard 4).
Correctly grounded? yes — the discard-half-rounded-down rule comes straight
          from the retrieved Catan chunk, no outside knowledge added.
Cited the right game? yes — led with [Catan].

Also tested the grounding refusal (case b): query "What is the best opening
chess move?" retrieved weak Risk/Clue chunks, and the model correctly answered
"I cannot find the answer in the loaded rules... the context only contains
rules for [Risk] and [Clue]" instead of guessing.
```

**One thing you changed from your original spec after seeing the actual output:**

```
The citation instruction told the model to cite "using the bracketed game
labels," and it took that literally — it prints "[Catan]" as a raw header at
the very start of the answer. It's correct, but in the UI the bracket syntax
reads more like a debug tag than natural prose. If I iterate, I'd soften the
citation instruction to ask for inline phrasing ("According to the Catan
rules, ...") so the answer reads naturally instead of leading with [Catan].

A pleasant surprise: on the out-of-scope query the model didn't just refuse —
it volunteered which games WERE in the context. That's stronger grounding
behavior than the prompt explicitly asked for.
```
