from diag import D, C, FM, FB, FR, FMB
W,H = 1660, 1190
d = D(W,H,"Classifying R&U / AP / AEC — Four Independent Signals, One Calibrated Fusion",
      "Tier is a judgement about cognitive demand, not a fact on the page. So we never ask one model once.")

d.box(40,116,1580,58,None,None,"chip",pad=0)
d.text(56,132,"THE ITEM",12,FMB,C["mark"])
d.text(56,152,'30(B) Q26 · Section C · 3 marks · "Prove that  √5  is an irrational number."',15.5,FR,C["ink"])

# four signals
d.tag(40,200,"FOUR SIGNALS · COMPUTED INDEPENDENTLY · NONE OF THEM DECIDES ALONE",C["mark"],12.5)
y=222; bw=380; xs=[40,444,848,1252]
d.box(xs[0],y,bw,292,"1 · Structural prior",
 ["Free, deterministic, from the paper itself.","",
  "~section        C  (SA, 3 marks)","~question type  Short Answer","~marks          3","~position       mid-paper","",
  "CBSE papers correlate type and tier strongly:","1-mark MCQ skews R&U, 5-mark LA skews AEC,","case-based CBQ skews AP/AEC.","",
  "Output: a prior distribution, never a label.","~R&U 0.30 | AP 0.55 | AEC 0.15"],"plain",tsize=17,lsize=13)

d.box(xs[1],y,bw,292,"2 · Bloom verb lexicon",
 ["A curated table per language, not code.","",
  "~EN  prove · find · calculate · solve   → AP","~EN  state · define · name · list      → R&U","~EN  justify · evaluate · comment      → AEC",
  "~HI  siddh kijiye  (prove)             → AP","~HI  gyaat kijiye  (find)              → AP","~TA  vilakkuka     (explain)           → R&U","",
  "Stem verb here: PROVE → AP","~R&U 0.15 | AP 0.70 | AEC 0.15"],"plain",tsize=17,lsize=13)

d.box(xs[2],y,bw,292,"3 · Novelty vs NCERT",
 ["The signal nobody else builds. Retrieve the","item against the NCERT corpus + Question Library.","",
  "~verbatim NCERT exercise   → recall/routine → R&U/AP","~known method, new context → AP","~unseen, or ≥2 sub-topics  → AEC","",
  "√5 irrational is a standard NCERT theorem,","cosine similarity 0.94 to Ex 1.2 Q1.","",
  "So despite 'prove', this is REPRODUCTION.","~R&U 0.55 | AP 0.40 | AEC 0.05"],"accent",tsize=17,lsize=13)

d.box(xs[3],y,bw,292,"4 · LLM judgement",
 ["claude-opus-5, output constrained to the three","tiers, with a required rationale.","",
  "Prompt carries: CBSE tier definitions, the","school's own adjudicated exemplars, and","signals 1–3 as stated evidence.","",
  "~self-consistency k = 5, vote spread kept","~as an uncertainty measure","",
  "Votes: R&U x3, AP x2","~R&U 0.60 | AP 0.40 | AEC 0.00"],"accent",tsize=17,lsize=13)

# fusion
fy=546
d.line(40,fy,1620,fy,C["ink"],2)
d.tag(40,fy+16,"FUSION · CALIBRATED, NOT AD HOC",C["mark"],12.5)
fy2=fy+38
d.box(40,fy2,600,238,"How the four are combined",
 ["Cold start (under ~200 adjudicated items):","~fixed weights  LLM .45 · verbs .25 · novelty .20 · structure .10","",
  "Once the adjudicated set grows:","~multinomial logistic regression over all four signal vectors","~plus marks, type, section, sub-topic count as features","",
  "The dashboard always states which mode is active.","",
  "~FUSED:  R&U 0.52 | AP 0.44 | AEC 0.04"],"accent",tsize=17,lsize=13)

d.box(664,fy2,470,238,"Conformal gate",
 ["Split conformal on a held-out adjudicated set,","calibrated so the returned SET contains the truth","with probability ≥ 1−α.","",
  "Set size 1  → auto-accept","Set size >1 → teacher review, candidates pre-selected","",
  "Here the set is {R&U, AP} — the two leaders are","4 points apart, so this item goes to a human.","",
  "~That is the correct outcome, not a failure."],"verify",tsize=17,lsize=13)

d.box(1158,fy2,462,238,"Teacher confirms once",
 ["One screen, the item beside the candidate set","and the rationale. One tap.","",
  "The decision is written to the Question Library","with the paper code, so the next school using","this exact question inherits it at confidence 1.0.","",
  "~expect tier abstention ≈ 3x the chapter rate.","~Budget for it. It is the honest cost of a label","~that is genuinely a judgement."],"plain",tsize=17,lsize=13)

d.arrow([(640,fy2+119),(658,fy2+119)],C["mark"],1.8)
d.arrow([(1134,fy2+119),(1152,fy2+119)],C["mark"],1.8)
for x in xs:
    d.arrow([(x+bw/2, y+292),(x+bw/2, fy-8)],C["ink3"],1.4)

# global constraint
gy=fy2+262
d.line(40,gy,1620,gy,C["rule"],1)
d.tag(40,gy+18,"THE PAPER-LEVEL TIE-BREAKER · AND WHEN NOT TO USE IT",C["mark"],12.5)
d.box(40,gy+40,780,150,"Board papers declare a blueprint — use it",
 ["CBSE targets R&U 54% · AP 24% · AEC 22% of marks.","",
  "For a board paper, nudge ONLY the abstained items so the paper's","tier mark-shares move toward the declared target. Confident items",
  "are never moved. A Sinkhorn-style adjustment, applied as a tie-break."],"verify",tsize=17,lsize=13)
d.box(840,gy+40,780,150,"School unit tests — never apply it",
 ["A school's paper deviating from 54/24/22 is not an error to correct.","It is the single most valuable finding in the paper-quality report:",
  "","~'This paper is recall-heavy: 71% R&U against a 54% target.'","",
  "Applying the prior here would erase the very signal we sell."],"accent",tsize=17,lsize=13)

d.line(40,H-92,1620,H-92,C["ink"],2)
d.text(40,H-74,"Why four signals rather than one good prompt",16,FB,C["ink"])
d.text(40,H-48,"Each signal fails differently. The verb lexicon is fooled by 'prove' on a memorised theorem; novelty retrieval is fooled by a reworded stem; the structural prior is fooled by an unusual paper;",14,FR,C["ink2"])
d.text(40,H-24,"the model is fooled by a plausible-sounding rationale. Fusing four uncorrelated failure modes, then abstaining when they disagree, is what makes the label defensible to a head of department.",14,FR,C["ink2"])
d.save("d9.png"); print("ok")
