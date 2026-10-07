# Question lab

An operator tool in the admin console (**Ops console → Question lab**, `/admin/question-lab`) that puts
**one** question through the mapping pipeline and shows every step. It is read only: nothing it does
can change a paper, a school or a student.

## What you get back

- **Chapter, topic (section and heading), tier, concept family** and whether the pipeline would flag it
  for review.
- **How it decided:** the retrieval ranking and the passages that put it there; whether the Tier 0 gate
  would have skipped the chapter judge; the trained classifier's vote; and, when a school is chosen, the
  nearest questions that school's teachers already confirmed and whether memory would reuse one.
- **Saved mapping** when the question was loaded from the database, side by side with the lab's answer.
- **Cost** in Full mode: calls, model, tokens, and the estimate both live and as classify runs it
  (topic judge batched at half price).

## Two modes

| Mode | Cost | Runs |
|---|---|---|
| Retrieval only | free | book retrieval, the retrieval-only topic, gate / memory / classifier signals. No Claude call. |
| Full | real money; limited to 60 runs an hour | also the live chapter judge and topic judge, configured exactly as the classify job configures them |

## Where to use it

- Pick a subject (Science, Social Science, ...). For Social Science, the paper section letter narrows the
  search to History / Geography / Political Science / Economics, as the real pipeline does.
- Type or paste a question, or search for one that is already stored and click **Use**.
- Choose a school to include its confirmed questions in the memory signal.

## Safety

The route (`POST /platform/question-lab/run`) sits behind the operator key. It opens its own database
session, never commits and rolls back in a `finally`; on Postgres the transaction starts READ ONLY. Tests
count every table it could touch before and after each run.

`GET /platform/question-lab/find?q=...` searches stored questions by text, also read only.

Retrieval-only mode on a book with no embeddings has one retriever, so the gate can never pass and every
result reads "would be flagged"; that mirrors the real pipeline on such a book.
