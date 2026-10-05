"""A trained chapter classifier: multinomial naive Bayes over the book and confirmed questions.

Retrieval asks "which passage resembles this question". A classifier asks a different
thing: "which chapter's vocabulary generates these words". The two fail on different
questions, which is what makes a classifier worth having as another reader next to
retrieval, and it is as cheap as retrieval: no model, no network, trained in milliseconds
from data already in the database -- every book chunk is a labelled example of its chapter,
and every question a teacher confirmed is one more, counted more heavily because it is
written the way questions are.

It does not place anything by itself. It is a reader the Tier 0 gate consults: when it is
confident about a different chapter than retrieval chose, the gate does not pass and the
chapter judge reads the question.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from app.classify.memory import tokens

#: how many times a teacher-confirmed question counts against one book passage
CONFIRMED_WEIGHT = 3
#: Laplace smoothing
ALPHA = 0.1


class NaiveBayesChapters:
    def __init__(self) -> None:
        self.counts: dict[str, Counter] = defaultdict(Counter)
        self.totals: Counter = Counter()
        self.vocab: set[str] = set()

    def fit(self, examples: list[tuple[str, str, int]]) -> NaiveBayesChapters:
        """``examples``: (chapter, text, weight)."""
        for chapter, text, weight in examples:
            for t in tokens(text):
                self.counts[chapter][t] += weight
                self.totals[chapter] += weight
                self.vocab.add(t)
        return self

    def __len__(self) -> int:
        return len(self.counts)

    def predict(self, text: str, allowed: set[str] | None = None) -> tuple[str | None, float]:
        """(chapter, posterior) among ``allowed`` (every trained chapter when None); the
        posterior is the softmax of the log-likelihoods, uniform prior. (None, 0.0) when
        there is nothing to say."""
        words = Counter(t for t in tokens(text) if t in self.vocab)
        chapters = [c for c in self.counts if allowed is None or c in allowed]
        if not words or len(chapters) < 2:
            return (chapters[0], 1.0) if len(chapters) == 1 and words else (None, 0.0)
        v = len(self.vocab)
        scores = {}
        for c in chapters:
            denom = self.totals[c] + ALPHA * v
            counts = self.counts[c]
            # a word counts once however often the question repeats it: a question is short
            scores[c] = sum(math.log((counts[w] + ALPHA) / denom) for w in words)
        top = max(scores.values())
        z = sum(math.exp(s - top) for s in scores.values())
        best = max(scores, key=scores.get)
        return best, 1.0 / z
