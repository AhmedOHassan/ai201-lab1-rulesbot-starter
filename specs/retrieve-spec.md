# Spec: `retrieve()`

**File:** `retriever.py`
**Status:** Complete — implemented in `retriever.py` and verified against a test query

---

## Purpose

Given a user's natural language query, find the most relevant chunks from the vector store using semantic similarity search. Return them ranked by relevance so that `generate_response()` can use them as context.

---

## Input / Output Contract

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | `str` | The user's natural language question |
| `n_results` | `int` | Maximum number of chunks to return (default: `N_RESULTS` from `config.py`) |

**Output:** `list[dict]`

Each dict in the returned list must contain exactly these keys:

| Key | Type | Description |
|-----|------|-------------|
| `"text"` | `str` | The chunk text |
| `"game"` | `str` | The game name this chunk came from |
| `"distance"` | `float` | Cosine distance score — lower means more similar to the query |

Results should be ordered from most to least relevant (lowest to highest distance). Returns an empty list `[]` if the collection contains no documents.

---

## Design Decisions

### Query approach

```
_collection.query(
    query_texts=[query],
    n_results=n_results,
    include=["documents", "metadatas", "distances"],
)

- query_texts is a LIST because ChromaDB supports batch queries. I have one
  query, so I pass it as a single-element list.
- I do NOT embed the query myself. The collection was created with the same
  embedding function (all-MiniLM-L6-v2) used at ingestion, so ChromaDB embeds
  the query text into the SAME vector space as the stored chunks — that's what
  makes the cosine distances comparable.
- n_results comes from the parameter (default N_RESULTS = 3).
- include asks for exactly the three pieces my output contract needs:
  documents -> "text", metadatas -> "game", distances -> "distance".
  I omit embeddings/ids since I don't return them.
```

---

### Return structure

```
One item (for result index i):

{
    "text": "On your turn, roll both dice and move your token...",
    "game": "Catan",
    "distance": 0.41,
}

Where each field comes from in the query results:
- "text"     <- results["documents"][0][i]
- "game"     <- results["metadatas"][0][i]["game"]
               (the "game" key exists because embed_and_store() stored
                metadata as {"game": c["game"]} for every chunk)
- "distance" <- results["distances"][0][i]
```

---

### Handling the nested result structure

```
Index [0].

The nesting exists because query_texts can hold MANY queries at once. So each
key in the result (documents, metadatas, distances) maps to a list-of-lists:
  - the OUTER list is indexed by query (one entry per query_text)
  - the INNER list is that query's ranked results

I sent a single query, so everything I want lives at index [0]:
  results["documents"][0]  -> list of chunk texts
  results["metadatas"][0]  -> list of metadata dicts
  results["distances"][0]  -> list of distances

I then walk the three [0] lists in parallel (e.g. with zip) to build my dicts.
```

---

### Relevance threshold

```
Decision: return all n_results, no distance threshold.

Why this matches the contract: the output contract only promises an empty list
when the COLLECTION is empty — not when matches are weak. ChromaDB's
nearest-neighbor search always returns the n closest chunks if the collection
is non-empty, so returning all n_results is the straightforward behavior.

Tradeoffs:
- Return all n_results (chosen): simpler, and generate_response() always gets
  something to work with. Risk: an off-topic query still feeds 3 chunks as
  context, which can lead to confident-but-wrong answers.
- Threshold filter (e.g. drop distance > ~1.0–1.5): cleaner context and lets
  the bot say "I don't know." But cosine cutoffs are dataset/model-specific and
  fragile to tune — too tight and good results get dropped.

A threshold is a reasonable future improvement; for this milestone I keep it
simple and rely on the LLM prompt to handle weak context.
```

---

### Edge cases

```
(a) Empty collection: handled by the existing guard at the top of retrieve()
    — `if _collection.count() == 0: return []`. No query is run.

(b) No good match: query() still returns the n closest chunks (nearest
    neighbors always exist when the collection is non-empty), just with HIGH
    distances. Since I chose no threshold (see above), I return them as-is and
    let the LLM prompt decide how to handle weakly-relevant context.

(c) Multiple games: results can freely mix chunks from different games. Each
    returned dict's "game" field disambiguates which rulebook a chunk came from,
    so generate_response() can tell them apart.

Also: if the collection holds FEWER than n_results chunks, query() returns only
what exists — no error.
```

---

## Implementation Notes

**Test query and top result returned:**

```
Query: How do I build a settlement and what does it cost?
Top result game: Catan
Distance score: 0.4755
Does it make sense? yes — the top chunk is exactly the BUILDING section:
  "Settlements cost 1 Brick + 1 Lumber + 1 Grain + 1 Wool..." and all 3
  returned chunks were Catan building/road/settlement rules, ranked by
  increasing distance (0.4755, 0.5323, 0.5514).
```

**One thing about the query results that surprised you:**

```
The retrieved chunk text starts mid-word, the top result began
"eely during your turn.  BUILDING Settlements cost...". Chunks are split by
size during ingestion, not on sentence/word boundaries, so a relevant chunk
can begin or end in the middle of a word. Semantic search still ranked it #1
because the embedding captures meaning regardless of where the cut lands, but
it's a reminder that the raw context handed to generate_response() isn't
always clean prose.
```
