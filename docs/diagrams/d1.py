from diag import D, C, FM, FB, FR

W,H = 1660, 1000
d = D(W,H,"End-to-End System Flow","Both use cases, from the user's screen to the principal's report. Dashed arrows are writes to storage.")

cols = [40, 368, 696, 1024, 1352]
cw = 288
hdr = ["1 · CAPTURE  (BROWSER)","2 · API + QUEUE","3 · PROCESSING","4 · VERIFY","5 · DELIVER"]
for x,t in zip(cols,hdr):
    d.tag(x, 118, t, C["mark"], 12.5)
d.line(40,140,1620,140,C["rule"],1)

# lane A
d.tag(40, 158, "USE CASE 1 · PSYCHOMETRIC INTEREST TEST", C["ink3"])
ya = 178
d.box(cols[0],ya,cw,118,"Test UI",["Profile form + 36 items","Next.js · autosave per answer","~Dexie/IndexedDB queue"],"plain")
d.box(cols[1],ya,cw,118,"POST /sessions/responses",["Pydantic validation","Idempotent per item","~FastAPI"],"plain")
d.box(cols[2],ya,cw,118,"Scoring engine",["Ipsative centering → percentile","Empirical-Bayes shrinkage","~NumPy · no model involved"],"accent")
d.box(cols[3],ya,cw,118,"Validity + gate",["Long-string, timing, rev-pairs","Differentiation gate D",'~flat profile → no stream call'],"accent")
d.box(cols[4],ya,cw,118,"Principal only",["Holland code + stream fit","Cohort dashboard, PDF","~student never sees a score"],"verify")
for i in range(4):
    d.arrow([(cols[i]+cw, ya+59),(cols[i+1]-6, ya+59)])

# lane B
d.line(40,326,1620,326,C["rule"],1)
d.tag(40, 344, "USE CASE 2 · MARKS ENGINE", C["ink3"])
yb = 364
d.box(cols[0],yb,cw,196,"Scanner UI",
      ["Feature 1: cover-page frame","Feature 2: all pages, per-page retake",
       "Live quality gate: blur, glare,","coverage, skew — shutter locks","until all four pass",
       "~getUserMedia + OpenCV.js"],"plain")
d.box(cols[1],yb,cw,196,"Upload + assemble",
      ["Resumable per-page upload","img2pdf (lossless) + pikepdf",
       "QR → student binding","Job queued (arq/Redis) or","overnight Batch API",
       "~originals AND pdf both kept"],"plain")
d.box(cols[2],yb,cw,196,"7-layer extraction",
      ["L1 dewarp · L2 red/black split","L3 anchors + mark candidates",
       "L4 recogniser  ← only model","L5 Hungarian association","L6 constraint solver",
       "~six layers are pure OpenCV/SciPy"],"accent")
d.box(cols[3],yb,cw,196,"Reconcile + route",
      ["Σ marks = page/section/grand","total, else FLAG not guess",
       "Auto-accept above threshold","Rest → review queue with crop",
       "~one tap to confirm or correct"],"accent")
d.box(cols[4],yb,cw,196,"Diagnostic report",
      ["Marks → chapter / sub-topic /","tier via frozen Q-matrix",
       "Evidence floor + intervals","Board-weighted indicator",
       "~principal only, never the student"],"verify")
for i in range(4):
    d.arrow([(cols[i]+cw, yb+98),(cols[i+1]-6, yb+98)])

# question paper feed
d.box(cols[2],yb+212,cw,100,"Question paper (once per paper)",
      ["claude-opus-5 · 2 passes · strict JSON","Gates: Σ marks · sequence · consensus","~teacher confirms → Q-matrix FROZEN"],"accent",tsize=15)
d.arrow([(cols[2]+cw, yb+255),(cols[3]+cw/2, yb+255),(cols[3]+cw/2, yb+200)], C["mark"], 1.8)

# storage strip
d.line(40,712,1620,712,C["ink"],2)
d.tag(40, 726, "STORAGE · EVERY STAGE ABOVE WRITES DOWN HERE", C["mark"], 12.5)
sy = 748
sw = 380
sx = [40, 444, 848, 1252]
d.box(sx[0],sy,sw,150,"PostgreSQL 16 + pgvector",
      ["mark_event (append-only, never updated)","taxonomy_node · question_skill (Q-matrix)",
       "test_session · item_response · scale_score","Row-level security by school_id",
       "~system of record · ap-south-1"],"plain",tsize=15)
d.box(sx[1],sy,sw,150,"Object store (S3/MinIO)",
      ["Page images + assembled PDF","Mark crops for provenance",
       "SSE-KMS, lifecycle expiry","Restricted access on full pages",
       "~a report links back to the pixels"],"plain",tsize=15)
d.box(sx[2],sy,sw,150,"ml_corpus  (separate schema)",
      ["capture_asset · crop · prediction","human_label · disagreement",
       "Full distribution stored, not argmax","consent_class gates training use",
       "~this is what trains the free model"],"verify",tsize=15)
d.box(sx[3],sy,sw,150,"Analytics (DuckDB → ClickHouse)",
      ["dbt models, tagged by run_id","Loss by chapter / sub-topic / tier",
       "Paper quality + board indicator","Audit-sample accuracy dashboard",
       "~reports regenerate bit-identically"],"plain",tsize=15)

for x in [cols[0]+cw/2, cols[1]+cw/2, cols[2]+cw/2, cols[3]+cw/2, cols[4]+cw/2]:
    d.arrow([(x, 686),(x, 708)], C["ink3"], 1.2, dash=(5,4))

d.line(40,930,1620,930,C["rule"],1)
d.text(40, 946, "The only arrow that carries a model is inside box 3. Everything else — geometry, colour separation, association, arithmetic reconciliation, scoring — is deterministic code that cannot hallucinate.", 15, FR, C["ink2"])
d.save("d1.png"); print("d1 ok")
