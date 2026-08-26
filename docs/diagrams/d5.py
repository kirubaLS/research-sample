from diag import D, C, FM, FB, FR, FMB
W,H = 1660, 1116
d = D(W,H,"The Core Algorithm — From Photograph to a Verified Mark",
      "How a red number written anywhere on the page becomes a mark bound to the right question.")

# stage 1: separation
d.tag(40,120,"STEP 1 · SEPARATE THE TWO INKS  (L2)",C["mark"],12.5)
d.box(40,142,300,176,"Normalised page",["Dewarped, illumination-flattened,","white-balanced, deskewed.",
  "Contains three things mixed:","printed text, the student's","black/blue answer, the teacher's","red mark."],"plain",tsize=16)
d.arrow([(346,217),(392,217)],C["mark"],1.8)
d.box(398,142,300,68,"TEACHER layer (red)",["~HSV bands wrapping 0/180 + sat floor"],"accent",tsize=15,pad=10)
d.box(398,224,300,68,"STUDENT layer (black/blue)",["~dark low-sat OR blue hue band"],"plain",tsize=15,pad=10)
d.box(722,142,420,176,"Why this one step matters so much",
 ["It turns one hard problem into two easy ones.","",
  "Question numbers are searched for in the","STUDENT image. Marks are searched for in the",
  "TEACHER image. The student's own arithmetic","working is simply not present in the picture the",
  "mark detector looks at."],"verify",tsize=16)
d.box(1166,142,454,176,"The traps this must survive",
 ["Printed red margin rule → remove long straight","structures first (Hough + long thin opening).",
  "Bleed-through from the reverse page → filter by","stroke intensity. Teacher overwriting their own",
  "mark → detect stacked components and send","straight to a human. Never guess between two",
  "values written on top of each other."],"accent",tsize=16)

# stage 2 localisation
d.line(40,336,1620,336,C["rule"],1)
d.tag(40,354,"STEP 2 · FIND ANCHORS AND CANDIDATES  (L3)",C["mark"],12.5)
d.box(40,376,500,152,"Anchors — from the STUDENT layer",
 ["Detect text → recognise → parse '6', '6.', 'Q6', '6(a)'.","",
  "CLOSED-VOCABULARY FILTER: accepted only if that","label exists in the frozen Q-matrix for this paper.",
  "~a hallucinated 'Q47' on a 30-question paper is","~discarded by construction, at zero cost"],"accent",tsize=16)
d.box(560,376,500,152,"Candidates — from the TEACHER layer",
 ["Connected components filtered by area, aspect and","stroke width. Circled numerals via contour hierarchy.",
  "Ticks, crosses, strikes and underlines excluded by shape.","",
  "~page and section totals detected SEPARATELY —","~each one becomes an extra equation in step 4"],"accent",tsize=16)
d.box(1080,376,540,152,"Answer-block segmentation",
 ["Using the student layer, segment the page into text blocks.","The block starting at anchor j and ending before anchor j+1",
  "is question j's answer region.","",
  "This gives step 3 a far better notion of 'which question is","this mark beside' than raw vertical distance ever could."],"plain",tsize=16)

# stage 3 association
d.line(40,548,1620,548,C["rule"],1)
d.tag(40,566,"STEP 3 · BIND MARK → QUESTION  (L5)  ·  A CONSTRAINED ASSIGNMENT PROBLEM, NOT A PILE OF IF-STATEMENTS",C["mark"],12.5)
d.box(40,588,760,196,"Cost of binding mark i to anchor j",
 ["~C[i][j] =  w1 · vertical_distance(i, j)",
  "~         + w2 · (0 if i inside question j's answer block else PENALTY)",
  "~         + w3 · side_inconsistency(i, fitted_convention)",
  "~         + w4 · page_mismatch(i, j)",
  "~         − w5 · log p_legal(value_i | max_marks(q_j))","",
  "Solved with the Hungarian algorithm — scipy.optimize.linear_sum_assignment.","Exact, optimal, ~1 ms for a 30 x 40 matrix. Each question takes at most one mark."],"accent",tsize=16)
d.box(820,588,800,196,"Then the second pass — this is the part competitors will not have",
 ["1. Take the bindings whose cost margin over the runner-up is large.",
  "2. Fit the convention they imply: the modal offset vector from anchor to",
  "    mark, the modal side (left / right / above), the distance distribution.",
  "3. Rebuild the cost matrix with that convention as a prior.",
  "4. Solve again.","",
  "A teacher is highly consistent within a script. The bindings that were","coin-flips in pass one are now decided by the teacher's own habit."],"verify",tsize=16)

# stage 4 reconcile
d.line(40,804,1620,804,C["rule"],1)
d.tag(40,822,"STEP 4 · RECONCILE AGAINST ARITHMETIC  (L6)  ·  THE ORACLE",C["mark"],12.5)
d.box(40,844,900,246,"Every constraint at once",
 ["~maximise   Σ log p_q(m_q)","",
  "~subject to  Σ marks over the paper    = grand total",
  "~            Σ marks in each section   = section total   (one equation each)",
  "~            Σ marks on each page      = page total      (one equation each)",
  "~            0 ≤ m_q ≤ max_marks(q),  on the legal step lattice","",
  "Exact dynamic programme over the mark lattice. If nothing clears the likelihood floor,","the script is FLAGGED — a missing page, an unmarked question, or the teacher's own","addition error surfaces here instead of silently corrupting a report."],"accent",tsize=16,lsize=13)
d.box(960,844,660,246,"Why the totals matter more than the recogniser",
 ["A handwritten 1 and 3 are the most confusable pair on an Indian answer","script. Per-crop, a model may prefer 3. The arithmetic says otherwise,",
  "and the arithmetic is ground truth.","",
  "This is why system accuracy is far higher than component accuracy.","A recogniser wrong one time in twelve, wrapped in these constraints,",
  "produces scripts that are correct or flagged — almost never silently wrong.","",
  "~If no total is written anywhere, ask the school to add one. It is the single","~cheapest accuracy improvement available."],"verify",tsize=16,lsize=13)
d.save("d5.png"); print("ok")
