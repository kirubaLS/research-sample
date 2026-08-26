from diag import D, C, FM, FB, FR, FMB
W,H = 1660, 1010
d = D(W,H,"How Accuracy and Efficiency Are Actually Achieved",
      "Eight defences on the left, the cost cascade on the right. Neither is a claim — both are measured.")

# LEFT: error funnel
d.tag(40,120,"THE ACCURACY LADDER · WHAT EACH DEFENCE CATCHES THAT THE OTHERS CANNOT",C["mark"],12.5)
rows=[("1","The model never does arithmetic","Every total computed in Python. Catches fabricated sums — the commonest LLM numeric failure."),
      ("2","Restricted alphabet per cell","A 3-mark question can only yield 0…3. The model is structurally unable to return 8."),
      ("3","Colour separation","The student's own working is not in the image the mark detector sees. Kills most false positives."),
      ("4","Closed-vocabulary anchors","A question label is accepted only if it exists in the frozen Q-matrix. Invented labels vanish."),
      ("5","Redundant extraction","Two independent passes, field-level diff. Two passes rarely invent the same thing twice."),
      ("6","Arithmetic reconciliation","Grand, section and page totals. A wrong digit must satisfy every equation — it cannot."),
      ("7","Conformal abstention","Calibrated so the returned set contains truth with probability ≥ 1−α. Catches confident wrongness."),
      ("8","Provenance to pixels","Every value links to its crop. A human verifies in one second, which makes review cheap.")]
y=142; wdt=980
for i,(n,t,sub) in enumerate(rows):
    h=74
    kind = "accent" if n in ("2","3","6") else "plain"
    d.box(96,y,wdt-56,h,None,None,"band" if kind=="plain" else "plain")
    if kind=="accent": d.d.rectangle([96*2,y*2,(96+wdt-56)*2,(y+h)*2],outline=C["mark"],width=5)
    d.text(112,y+13,n+" · "+t,16,FB,C["ink"])
    d.text(112,y+40,sub,13.5,FR,C["ink2"])
    y+=h+8
# funnel
d.arrow([(70,142),(70,y-8)],C["mark"],2.4)
d.text(58,152,"ERRORS",12,FM,C["mark"],anchor="rm")
d.text(58,y-14,"RESIDUAL",12,FM,C["mark"],anchor="rm")
d.box(96,y+4,wdt-56,62,None,["Whatever survives all eight reaches a human review queue — never a report. That is the guarantee: not that the system is never wrong, but that it is never silently wrong."],"verify",pad=14)

# RIGHT: cost cascade
d.tag(1110,120,"THE COST CASCADE · PAY BY STAKES, NOT BY VOLUME",C["mark"],12.5)
cy=142
d.box(1110,cy,510,150,"Question paper — once per paper",
 ["claude-opus-5, two independent passes","Highest stakes: a wrong Q-matrix poisons",
  "every report for 40 students.","No arithmetic oracle exists here, so pay for",
  "the best model. ~Rs 40–50, amortised over 40."],"accent",tsize=16)
cy+=162
d.box(1110,cy,510,150,"Cover page — once per student",
 ["claude-opus-5, one frame","A structured table, high information density,",
  "and the source of the grand total that makes","the constraint solver work.",
  "~Rs 1–2 per student."],"plain",tsize=16)
cy+=162
d.box(1110,cy,510,150,"Mark crops — ~30 per student",
 ["claude-haiku-4-5, tiny images","Restricted alphabet does most of the work here,",
  "so the cheap model is sufficient.","Disagreements escalate to opus as adjudicator.",
  "~Rs 1 per student. Batches API halves it again."],"verify",tsize=16)
cy+=162
d.box(1110,cy,510,172,"All in, one class of 40",
 ["≈ Rs 150–350 per assessment","",
  "Twenty classes, two assessments a term:","a few thousand rupees. Negligible against a",
  "school licence — and every crop processed is","training data for the free recogniser."],"accent",tsize=16)

d.line(40,H-98,1620,H-98,C["ink"],2)
d.text(40,H-82,"And the measurement that turns all of this from a claim into a fact",16,FB,C["ink"])
d.text(40,H-56,"A permanent audit sample: 10% of scripts re-keyed by hand, INCLUDING cells the system was confident about, with the resulting error rate published on the principal's dashboard.",14,FR,C["ink2"])
d.text(40,H-32,"Without it you have a system that feels accurate. With it you have one that can prove it — and if accuracy ever drifts you learn it from the dashboard, not from a parent.",14,FR,C["ink2"])
d.save("d6.png"); print("ok")
