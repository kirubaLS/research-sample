# Handover: Science book map

Load exactly as described in the Social Science `HANDOVER.md`, with these differences:

- File: `science_units.json`. Unit fields are the same, plus `intext_questions[]` {label, page, text[]}, which is **never** evidence and must be excluded from placement search, like exercises.
- Chapter codes are the existing database codes (`X.SCI.CHEMRXN`, `X.SCI.ACIDS`, `X.SCI.METALS`, `X.SCI.CARBON`, `X.SCI.LIFEPROC`, `X.SCI.CONTROL`, `X.SCI.REPRO`, `X.SCI.HEREDITY`, `X.SCI.LIGHT`, `X.SCI.EYE`, `X.SCI.ELECTRICITY`, `X.SCI.MAGNETIC`, `X.SCI.ENVIRONMENT`).
- Topics: one per `catalog` code. 88 reuse existing database family codes; 90 are new. Retire the remaining old X.SCI families (`valid_to`, no section claims) after moving any questions that use them.
- Board papers split Science into Biology, Chemistry and Physics sections in some series. When a section is given, restrict placement to that subject's chapters: Chemistry CHEMRXN, ACIDS, METALS, CARBON; Biology LIFEPROC, CONTROL, REPRO, HEREDITY, ENVIRONMENT; Physics LIGHT, EYE, ELECTRICITY, MAGNETIC.
- Numericals and chemical equations: the book's worked examples are in the body text of their unit (for example Lens Formula and Magnification, Resistors in Series). Formulas were extracted as text and may show subscripts inline (H2SO4).
