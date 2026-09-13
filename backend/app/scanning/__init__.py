"""The seven-layer answer-script pipeline, as one place.

    L0  Capture         PageImage + quality metrics        app.vision.quality
    L1  Restoration     NormalizedPage                     app.vision.orientation  (partial)
    L2  Ink separation  InkLayers{teacher,student,printed}  app.vision.ink
    L3  Localisation    Anchor[], MarkCandidate[], Total[]  app.vision.localise
    L4  Recognition     distribution over legal values      app.scanning.recognise
    L5  Association     Binding[]                           app.mapping.association
    L6  Reconciliation  verified MarkFact[]                 app.mapping.solver
    L7  Adjudication    GroundTruth[] + training rows       app.scanning.adjudicate

Six of the eight already existed under other names; this module names them, states the
contract between each pair, and runs them in order. Nothing here re-implements a layer.

The layer that carries the accuracy claim is L6, not L4. A recogniser looking at one
handwritten crop will sometimes prefer 3 where the teacher wrote 1 -- that is a property of
handwriting, not of the model. L6 does not accept the crop's opinion: it chooses the
assignment of marks that maximises total likelihood *subject to the totals the teacher
wrote*, so a misread that breaks the arithmetic is repaired by the arithmetic. This is why
the system is more accurate than any of its parts, and why L4 must return a distribution
rather than a value -- a value throws away exactly the information L6 needs.
"""

from __future__ import annotations

from app.scanning.pipeline import ScriptResult, read_script
from app.scanning.recognise import MarkRecognizer

__all__ = ["MarkRecognizer", "ScriptResult", "read_script"]
