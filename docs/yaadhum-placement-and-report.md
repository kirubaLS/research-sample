# From a scanned paper to a student's report

What the system may claim, what it must refuse to claim, and how a question gets placed
when no blueprint exists.

---

## 1. The blueprint was the wrong name for it

An earlier design leaned on CBSE's published weightage — Mensuration 10 marks, Algebra 20 —
to catch a misplaced question. That works for a board paper and not for the papers this
product actually sees most: a daily test, a cyclic test, a unit test a teacher wrote last
night. None of those has a published blueprint.

But **a paper always declares something**, and scanning it tells us what. What the cover
page and section headers give us, before any classification:

| Read from the paper | Always present? | What it constrains |
|---|---|---|
| Exam name / paper code | usually | which curriculum version, which class |
| Question numbers | yes | the address every mark maps to |
| Marks per question | yes | the weight of each finding |
| Section totals ("Section B: 5 x 2 = 10") | usually | that the marks read back are right |
| Grand total ("Maximum Marks: 80") | yes | the same, at the paper level |
| Published unit weightage | **board papers only** | which *chapter* a question belongs to |

So the constraint is not one thing. It is a ladder, and the system uses the strongest rung
available rather than requiring the top one.

---

## 2. The constraint ladder

**Rung 1 — published blueprint.** Board papers. Strongest: it pins marks per board unit, so
a misplaced question shows up as arithmetic that will not close.

**Rung 2 — syllabus scope, declared or inferred.** *"This test covers Chapters 1 to 5."*
Nearly as strong as a blueprint **for placement**: a question in Chapter 9 is then provably
wrong, not merely suspicious, and the candidate set shrinks from fourteen chapters to five
before classification starts. For daily and cyclic tests this is the rung that does the
work.

A teacher can declare it, but usually should not have to, because **the paper already
answers it**. Inferring the scope is a far easier problem than placing any single question:
a cyclic test carries twenty to forty questions, each voting independently, so a chapter
twelve questions agree on is nearly certain while one question alone in a chapter is more
likely a misplacement than a topic. Errors are independent and cancel. So placement runs
twice -- classify freely, infer the scope from where the questions fell, then classify
again with the outliers ruled out.

Three guards, because a second pass makes a *systematic* error stickier rather than
weaker. If cone questions are consistently misread as trigonometry, trigonometry looks in
scope and the second pass repeats the error with more conviction:

* **A chapter must earn its place** -- two questions, or a tenth of the marks, and at least
  one placement the classifier stood behind. A single unconfident vote cannot create a
  topic; it can only be explained by one.
* **Below eight questions, no scope is inferred at all.** The argument was that errors
  cancel across a paper, and they do not cancel across a handful: on a three-question paper
  one misplacement *is* the consensus, and the second pass would delete the right chapter.
* **A scope that explains less than 80% of the marks is not acted on.** It has not
  understood the paper, and filtering by it would remove real content.

And a question whose evidence all falls outside the scope is **never dropped** -- it is
retried without the scope and handed to a person. A question missing from a report is worse
than one visibly in the wrong place: it disappears instead of being wrong.

Confirming an inferred scope is one glance. Confirming thirty-eight placements is an
afternoon. So the scope is what goes in front of a teacher first.

**Rung 3 — section and grand totals.** Always on the paper. These constrain *marks*, not
chapters — they cannot tell you a cone question is mensuration. They are what
`app.mapping.solver` already uses to repair a misread mark against the totals it must sum
to. Different job, same principle.

**Rung 4 — nothing declared.** The classifier decides alone and everything below its
confidence threshold goes to a person. Still usable; just more review.

**Design rule: the blueprint is optional, and its absence must never be silent.** A report
built on rung 4 says so, because a teacher reading it deserves to know how the placement
was arrived at.

---

## 3. Answer script to report

```
   scan the question paper
        |
        v
   Q.No + marks + section totals        <- the paper's own arithmetic
        |
        v
   place each question                  <- retrieve -> judge -> constraints
   chapter / section / concept family / tier
        |
   [ questions below confidence -> a person confirms, once per paper ]
        |
        v
   scan the answer script
        |
        v
   marks read per Q.No                  <- repaired against the section totals
        |
        v
   join on Q.No                         <- the only join in the system
        |
        v
   marks lost per chapter, per section, per tier
        |
        v
   the report
```

The join is on **question number**, which is why the address scheme matters so much: a mark
read as belonging to Q22(b) and a question tagged as Q22(b) must be the same thing, and the
choice groups are where that gets subtle. Nothing else in the pipeline is a join.

---

## 4. What the report may say, and what it may not

The standing instruction is that the report is **true, not helpful**. A confident sentence
a teacher acts on and that turns out to be unfounded costs more than a blank space. So
every claim is bound by a rule:

**Every finding names its questions.** "Weak in Surface Areas and Volumes" is unfalsifiable.
"Lost 6 of 9 marks in Surface Areas and Volumes — Q17, Q28, Q34" can be checked against the
script in thirty seconds. Nothing is reported that cannot be traced to specific marks.

**Below the evidence floor, say so instead of scoring.** Under two marks or two questions in
a chapter, the report reads *"insufficient evidence in this paper"* — not a low score.
One question is not a diagnosis. This is already enforced in `app.analysis.diagnostics`.

**A question the student was never offered is not a mark lost.** The unchosen half of a
choice pair is absence of evidence. It never enters a denominator. `NOT_OFFERED` exists for
exactly this.

**A chapter with weight but no marks in this paper is a coverage gap, never a zero.** *"This
paper carries no marks for Statistics, which is 11% of the board weighting. The test gives
you no information about it."* Silence about a chapter is a fact about the paper, not about
the student.

**An unconfirmed placement is excluded, and the exclusion is counted.** If a question's
chapter was below confidence and nobody confirmed it, its marks do not feed a chapter
finding. The report states how many marks were set aside for that reason — otherwise a
partial diagnosis reads as a complete one.

**Tier findings carry their provenance.** Where the paper declared a tier, the report may
state it flatly. Where it was derived, the report says it was derived. R&U / Applying / AEC
is a judgement even between experienced teachers, and presenting a derived tier as a board
fact is the most tempting false note in the whole product.

**No difficulty during a single-school pilot.** It needs volume across more than one school,
by definition, so it renders as absent with the reason — never as a provisional number.

**Recommendations follow from lost marks, and go no further.** *"Concentrate on Volume of
Composite Solids — 6 of the 9 marks lost were there, across Q17, Q28 and Q34."* Not "this
student is a visual learner", not a predicted board score, not a comparison to a cohort the
report cannot see.

---

## 5. Where the two use cases stay apart

The interest test says nothing about ability, and the marks engine says nothing about
interest. A student weak in Mensuration and scoring high on the Investigative scale is two
findings, not a story. Joining them into advice is a claim about causation that neither
instrument supports, and it is not made anywhere in this system.

---

## 6. What is built, and what is not

| Stage | State |
|---|---|
| Question placement: retrieve -> judge -> constraints | built; blueprint rung only, unmeasured against a real model |
| Syllabus-scope constraint (rung 2) | **not built** — the rung daily tests need |
| Mark repair against section totals | built (`app.mapping.solver`), proven on a worked example |
| Answer-script recognition | **not built** — needs real phone photographs first |
| Join on question number | built (`app.extraction.address`) |
| Findings with evidence floors and coverage gaps | built (`app.analysis.diagnostics`) |
| Confirmation screen for flagged questions | **not built** |
| Report rendering | partially — the API returns findings; no student-facing document |
