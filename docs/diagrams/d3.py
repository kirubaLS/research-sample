from diag import D, C, FM, FB, FR, FMB
W,H = 1660, 1160
d = D(W,H,"Backend View — Seven Layers, One Model",
      "Exactly one layer contains a model. That is what makes the free and paid plans interchangeable.")

colx = [40, 296, 776, 1150]
head = ["LAYER","METHOD / ALGORITHM","LIBRARY OR MODEL","OUTPUT CONTRACT"]
for x,t in zip(colx,head): d.tag(x,118,t,C["mark"],12.5)
d.line(40,138,1620,138,C["rule"],1)

rows = [
 ("L0","Capture",
  ["Blur = variance of Laplacian · glare = bright-blob fraction","coverage = quad area · skew = top-edge angle. Shutter locks","until all four pass — a bad photo costs 5 s here, a wrong report later"],
  ["getUserMedia","OpenCV.js (browser)","Dexie / IndexedDB"],
  ["PageImage","+ quality metrics"], "plain"),
 ("L1","Restoration",
  ["Corner detect (approxPolyDP) → homography → illumination","flattening by division with a blurred copy → white balance →","deskew by minimising projection-profile entropy"],
  ["OpenCV","NumPy"],
  ["NormalizedPage","300 dpi, A4 aspect"], "plain"),
 ("L2","Ink separation",
  ["HSV banding after white balance. Per-school hue centroids","fitted by k-means (k=3) on ink pixels — unsupervised, 3 pages.",
   "Long straight red structures removed first (the printed margin rule trap)"],
  ["OpenCV","scikit-learn k-means"],
  ["InkLayers","teacher / student / printed"], "accent"),
 ("L3","Localisation",
  ["Anchors from the STUDENT layer; marks from the TEACHER layer.","Closed-vocabulary filter: a label is an anchor only if it exists",
   "in the frozen Q-matrix. Totals detected as extra constraints"],
  ["DBNet / PaddleOCR det","OpenCV contours"],
  ["Anchor[] MarkCandidate[]","TotalCandidate[]"], "accent"),
 ("L4","RECOGNITION",
  ["The only model. Returns a probability distribution over the legal","values for THAT question — a 3-mark item can only yield 0…3.",
   "Restricting the alphabet per cell is the biggest free accuracy gain"],
  ["PAID: claude-haiku-4-5","      claude-opus-5 (adjudicate)","FREE: TrOCR-ft / PaddleOCR"],
  ["Distribution","dict[value → probability]"], "accent"),
 ("L5","Association",
  ["Cost matrix over distance, answer-block containment, side","consistency and value plausibility → Hungarian algorithm. Then refit",
   "the teacher's own convention from confident bindings and re-solve"],
  ["scipy.optimize","linear_sum_assignment"],
  ["Binding[]","mark ↔ question"], "plain"),
 ("L6","Reconciliation",
  ["max Σ log p(m) s.t. Σm = grand total, section totals AND page","totals, 0 ≤ m ≤ max_marks, on the legal step lattice. Exact DP.",
   "If nothing clears the likelihood floor the script is FLAGGED"],
  ["Pure Python DP","NumPy"],
  ["MarkFact[]","verified or flagged"], "accent"),
 ("L7","Adjudication",
  ["Everything unverified reaches a human, ordered by expected value","of the label (uncertainty x marks at stake x board weight), with the",
   "crop shown beside it. One tap to confirm, one to correct"],
  ["FastAPI + Next.js","ml_corpus writer"],
  ["GroundTruth[]","+ training rows"], "verify"),
]
y=152
for code,name,method,lib,out,kind in rows:
    h = 96
    d.box(40,y,1580,h,None,None,"band" if kind=="plain" else "plain")
    if kind=="accent": d.d.rectangle([40*2,y*2,1620*2,(y+h)*2],outline=C["mark"],width=5)
    if kind=="verify": d.d.rectangle([40*2,y*2,1620*2,(y+h)*2],outline=C["verify"],width=4)
    d.text(colx[0]+14, y+16, code, 20, FMB, C["mark"] if kind!="plain" else C["ink3"])
    d.text(colx[0]+14, y+48, name, 16.5, FB, C["ink"])
    yy=y+16
    for ln in method:
        d.text(colx[1], yy, ln, 13.5, FR, C["ink2"]); yy+=21
    yy=y+16
    for ln in lib:
        d.text(colx[2], yy, ln, 12.5, FM, C["mark"] if code=="L4" else C["ink3"]); yy+=21
    yy=y+22
    d.text(colx[3], yy, out[0], 14, FB, C["ink"]); yy+=22
    d.text(colx[3], yy, out[1], 12.5, FM, C["ink3"])
    if y<930: d.arrow([(170, y+h),(170, y+h+12)],C["ink3"],1.4)
    y += h+12

d.line(40,H-96,1620,H-96,C["ink"],2)
d.text(40,H-80,"Why this segregation is worth the discipline",16,FB,C["ink"])
d.text(40,H-54,"Six of the seven layers are OpenCV, SciPy and plain Python: deterministic, CPU-cheap, unit-testable against fixed images, byte-identical every run. Swapping the paid recogniser for the",14,FR,C["ink2"])
d.text(40,H-32,"free one is a configuration value, not a rewrite. And when something is wrong, the failure is localised to a named layer with its own tests — not to 'the AI got it wrong'.",14,FR,C["ink2"])
d.save("d3.png"); print("ok")
