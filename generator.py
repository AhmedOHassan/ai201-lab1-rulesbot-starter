from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL

_client = Groq(api_key=GROQ_API_KEY)


def generate_response(query, retrieved_chunks):
    """
    Generate a grounded answer from retrieved rule chunks.

    TODO — Milestone 3:

    `retrieved_chunks` is the list returned by retrieve(). Each item is a dict:
      - "text"     : the chunk text
      - "game"     : the game name
      - "distance" : similarity score (you can use this to filter weak matches)

    Before writing code, talk through these with your group:
      - How will you format the chunks into a context block for the prompt?
      - What instructions will stop the model from answering beyond what the
        rules say? (Grounding is the whole point — a confident wrong answer
        is worse than an honest "I don't know.")
      - How will you surface which game each answer comes from?

    Your response should:
      1. Answer using only the retrieved context — not the model's general knowledge
      2. Make clear which game the answer comes from
      3. Say so clearly when the answer isn't in the loaded rules

    Return the response as a plain string.
    """
    if not retrieved_chunks:
        return (
            "I couldn't find anything relevant in the loaded rule books. "
            "Try rephrasing your question — or check that your ingestion pipeline is working."
        )

    # Format each chunk as a [game]-labeled block, separated by a delimiter.
    # Game labels stay in (so the model can cite the source); distance stays out.
    context = "\n\n---\n\n".join(
        f"[{chunk['game']}]\n{chunk['text']}" for chunk in retrieved_chunks
    )

    # System message holds the stable behavioral rules: persona + grounding +
    # citation. The grounding clause is what keeps answers honest.
    system_prompt = (
        "You are a board game rules assistant. Answer the question using ONLY "
        "the rules in the provided context. Do not use any outside knowledge of "
        "these or any other board games. If the context does not contain the "
        "answer, say you cannot find it in the loaded rules — do not guess, "
        "infer, or fill in gaps.\n\n"
        "State which game your answer comes from, using the bracketed game "
        "labels in the context (e.g. [Catan]). If your answer draws on more than "
        "one game, name each game it applies to."
    )

    # User message holds the per-request payload: the context block + the query.
    user_message = (
        f"Context:\n{context}\n\n"
        f"Question: {query}"
    )

    response = _client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    return response.choices[0].message.content
