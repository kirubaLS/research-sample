from diag import D, C, FM, FB, FR, FMB
W,H = 1660, 872
d = D(W,H,"Mapping an Answer Sheet onto the Q-Matrix",
      "How a red number on page 9 becomes 'Section B, Q16, choice (b), 3 of 5 marks, Reproduction, Applying'.")

# left: address matching
d.tag(40,118,"STEP 1 · WHAT THE ANCHOR ACTUALLY IS",C["mark"],12.5)
d.box(40,140,520,214,"CBSE tells the student to write it for us",
 ["Every one of the five papers carries this instruction:","",
  "~'Please write down the Serial Number of the","~ question in the answer-book at the given","~ place before attempting it.'","",
  "So the anchor is not something we hope to find —","it is a field the board requires the student to fill in,","in their own black or blue ink."],"accent",tsize=17,lsize=13)
d.box(40,370,520,158,"And the section is written too",
 ["'Divide your answer sheet into four sections as per","the question paper — Section A (History), Section B",
  "(Geography)...  It is compulsory to answer each","question in its respective section.'","",
  "~section headers give us page-range priors for free"],"verify",tsize=17,lsize=13)

# middle: resolution
d.tag(600,118,"STEP 2 · RESOLVE THE ADDRESS",C["mark"],12.5)
d.box(600,140,480,388,"Parse, then constrain",
 ["Student writes:   16(b)   ·   Q.16 b   ·   16 (kha)","",
  "1. Normalise: strip punctuation, map Devanagari","    numerals, fold script variants.","",
  "2. CLOSED VOCABULARY: the parsed address must","    exist in the frozen Q-matrix. '16(c)' does not","    exist, so it is rejected, not invented.","",
  "3. Section prior: a page inside the Geography block","    resolves an ambiguous '4' to B/4, not A/4.","",
  "4. Monotonic order: addresses should advance down","    the script. A break is a flag, not a silent reorder.","",
  "~this is why hallucinated question numbers cannot","~survive — the vocabulary is closed by construction"],"accent",tsize=17,lsize=13)

# right: the choice problem
d.tag(1120,118,"STEP 3 · THE CHOICE PROBLEM  (THE ONE THAT MATTERS)",C["mark"],12.5)
d.box(1120,140,500,186,"A student attempts 16(b), not 16(a)",
 ["The Q-matrix holds both alternatives.","Only one carries a mark.","",
  "The naive system records 16(a) = 0.","","~That is wrong, and it is wrong in the",
  "~direction that damages a child."],"accent",tsize=17,lsize=13)
d.box(1120,342,500,186,"Missing NOT at random",
 ["16(a) must be recorded as NOT OFFERED —","the student has produced no evidence about",
  "those skills, and no evidence is not weakness.","",
  "Scoring it zero would systematically mark","every student weak in whichever topic they",
  "chose to avoid. Diagnosis inverted."],"verify",tsize=17,lsize=13)

d.arrow([(560,238),(594,238)],C["mark"],1.8)
d.arrow([(1080,238),(1114,238)],C["mark"],1.8)

# bottom: mapping to skills per subject
by=548
d.line(40,by,1620,by,C["ink"],2)
d.tag(40,by+16,"STEP 4 · WHAT THE ADDRESS MAPS TO — AND IT IS NOT 'CHAPTER' IN EVERY SUBJECT",C["mark"],12.5)
sy=by+38
cards=[("Maths","chapter → sub-topic → tier",
        ["Real chapters: Polynomials, Circles,","Trigonometry, Statistics.","",
         "The model in the earlier design applies","unchanged. This is the easy case."],"plain"),
       ("Science","section IS the discipline",
        ["Sections are Biology (30), Chemistry (25),","Physics (25) — not chapters.",
         "","Two levels: discipline → chapter →","sub-topic. Section gives the first for free."],"plain"),
       ("Social Science","four sub-subjects, 20 marks each",
        ["History, Geography, Political Science,","Economics.","",
         "Plus map-based items (2 + 3 marks) that","are a distinct question type, not a topic."],"plain"),
       ("English / Hindi","skills, not chapters",
        ["Reading · Grammar & Creative Writing ·","Literature.","",
         "Long answers are rubric-scored: each","RUBRIC CRITERION becomes a skill, each","band a partial credit. Q-matrix unchanged."],"accent")]
for i,(t,sub,lines,kind) in enumerate(cards):
    x=40+i*398
    d.box(x,sy,378,196,t,None,kind,tsize=19)
    d.text(x+13,sy+44,sub,13,FM,C["mark"] if kind=="accent" else C["verify"])
    yy=sy+72
    for ln in lines:
        d.text(x+13,yy,ln,13,FR,C["ink2"]); yy+=21

d.line(40,H-92,1620,H-92,C["ink"],2)
d.text(40,H-74,"The question types we must tag, because each one diagnoses differently",16,FB,C["ink"])
d.text(40,H-48,"MCQ  ·  Assertion–Reason  ·  Match-the-columns  ·  VSA (2 marks, 40 words)  ·  SA (3 marks, 60 words)  ·  LA (5 marks, 120 words)  ·  Case-based CBQ (4 marks, 3 sub-parts)  ·  Map work",14,FR,C["ink2"])
d.text(40,H-24,"All eight appear in the papers you sent, and the instructions state their marks and word limits explicitly — so question type is extracted, not guessed.",14,FR,C["ink2"])
d.save("d8.png"); print("ok")
