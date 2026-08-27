from diag import D, C, FM, FB, FR, FMB
W,H = 1660, 884
d = D(W,H,"From Real CBSE PDF to a Frozen Q-Matrix — Five Normalisations",
      "Measured on the five 2026 papers you supplied. Every step below exists because one of them breaks without it.")

xs=[40,368,696,1024,1352]; cw=288
titles=["0 · RAW PAGES","1 · DE-IMPOSE","2 · DE-DUPLICATE","3 · ADDRESS","4 · CHOICE GROUPS"]
for x,t in zip(xs,titles): d.tag(x,118,t,C["mark"],12.5)
d.line(40,138,1620,138,C["rule"],1)

y=152
d.box(xs[0],y,cw,236,"What we actually get",
 ["English  : text layer, 19 pp","Science   : text layer, 27 pp",
  "SocialSci : partial text, 27 pp","Hindi     : NO TEXT, 16 pp",
  "Maths     : NO TEXT, 7 pp","",
  "~2 of 5 papers have zero extractable","~text. Vision is the primary path,","~not a fallback."],"accent",tsize=16,lsize=13)
d.box(xs[1],y,cw,236,"Maths is 4-up imposed",
 ["7 PDF pages carry 27 logical pages","— four A4 pages tiled 2x2, each with",
  "its own footer and QR code.","",
  "Detect by footer regex 'Page N of M'","and dashed cut lines; split into",
  "logical pages before anything else.","",
  "~missing this quadruples every question"],"accent",tsize=16,lsize=13)
d.box(xs[2],y,cw,236,"Bilingual interleave",
 ["Science, Social Science, Maths and","Hindi print every question twice —",
  "once in English, once in Hindi.","",
  "Naive mark sums we measured:","~English    90  vs 80 max",
  "~Science   172  vs 80 max","~SocialSci 349  vs 80 max","",
  "Dedupe by script + question number."],"accent",tsize=16,lsize=13)
d.box(xs[3],y,cw,236,"The address, not the number",
 ["The atomic unit is NOT '16'. It is","",
  "~SECTION / QNO / SUBPART / CHOICE","",
  "e.g.  A / 15 / (iii) / b","      B / 4  / (a)   / -",
  "","Marks are written per sub-part, so","the Q-matrix must key on the full",
  "address or nothing downstream lines up."],"accent",tsize=16,lsize=13)
d.box(xs[4],y,cw,236,"OR pairs share a budget",
 ["'Attempt any one from (a) and (b)'","",
  "Both alternatives carry the same marks.","They contribute to the paper total ONCE.",
  "","~choice_group_id in the schema",
  "","We counted 6 OR blocks in English,","9 in Science, 6 in Social Science."],"accent",tsize=16,lsize=13)
for i in range(4): d.arrow([(xs[i]+cw, y+118),(xs[i+1]-6, y+118)],C["mark"],1.8)

# verification band
vy=418
d.line(40,vy,1620,vy,C["ink"],2)
d.tag(40,vy+16,"5 · VERIFY — THE PAPERS HAND US FOUR FREE EQUATIONS",C["mark"],12.5)
vb=[("Question count","'contains 38 questions.'",
     ["Printed in General Instructions on","every one of the five papers. Our",
      "extracted count must equal it exactly."]),
    ("Section marks","'Section A : Biology (30 marks)'",
     ["A section's marks, after choice-","grouping and de-duplication, must",
      "equal the stated figure."]),
    ("Section arithmetic","'5 VSA questions x 2 marks  5x2=10'",
     ["The Maths paper literally prints the","multiplication for each section.",
      "Free, exact, per-section check."]),
    ("Paper total","'Maximum Marks : 80'",
     ["The sum over all sections. This is the","same equation the answer-script solver",
      "later uses as its oracle."])]
vy2=vy+38
for i,(t,ex,note) in enumerate(vb):
    x = 40 + i*398
    d.box(x,vy2,378,142,t,None,"verify",tsize=17)
    d.text(x+13,vy2+46,ex,12,FM,C["mark"])
    yy=vy2+74
    for ln in note:
        d.text(x+13,yy,ln,13,FR,C["ink2"]); yy+=21

# geometry finding
gy=604
d.line(40,gy,1620,gy,C["rule"],1)
d.tag(40,gy+18,"MEASURED GEOMETRY — A HARD PRIOR WE GET FOR FREE",C["mark"],12.5)
d.box(40,gy+40,780,120,"Marks are right-aligned at x ≈ 0.88 × page width",
 ["Measured across all three text-layer papers: the 10th, 50th and 90th percentile of the",
  "right edge of every bare mark label all land on 0.88. Not a heuristic — a typesetting rule.",
  "~ENGLISH 0.88 / 0.88 / 0.88     SCIENCE 0.88 median     SOCIAL SCIENCE 0.88 median"],"accent",tsize=17,lsize=13)
d.box(840,gy+40,780,120,"So the extractor never has to hunt",
 ["A candidate mark label must be a bare integer, alone on its line, right-aligned in that band.",
  "Anything else is body text. This single constraint removes almost all false positives before",
  "a model is asked to read anything — and it is the same prior we use on the answer script."],"verify",tsize=17,lsize=13)

d.line(40,H-96,1620,H-96,C["ink"],2)
d.text(40,H-78,"The output of all five steps",16,FB,C["ink"])
d.text(40,H-52,"One frozen, versioned Q-matrix row per address: section, question number, sub-part, choice group, max marks, question type, and the skill tags added in the next stage.",14,FR,C["ink2"])
d.text(40,H-28,"Nothing downstream — not the solver, not the mapping, not the report — ever sees a page again.",14,FR,C["ink2"])
d.save("d7.png"); print("ok")
