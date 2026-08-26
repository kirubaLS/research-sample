from diag import D, C, FM, FB, FR, FMB
W,H = 1660, 900
d = D(W,H,"Data Storage Map — What Lives Where, and What Crosses",
      "Four stores, two hard boundaries. Nothing is ever updated in place; corrections are new rows.")

# operational
d.tag(40,120,"OPERATIONAL PLANE · POSTGRESQL 16 (ap-south-1) · ROW-LEVEL SECURITY BY school_id",C["mark"],12.5)
y=140
bw=380; xs=[40,444,848,1252]
d.box(xs[0],y,bw,178,"Identity (restricted schema)",
 ["student_profile — name, roll no, class","consent_ref, parental consent record",
  "school · section · staff · roles","","~separate credentials. Analytics never",
  "~joins to this table — only to a UUID."],"accent",tsize=16)
d.box(xs[1],y,bw,178,"Facts (append-only)",
 ["mark_event(student, question, marks,","  source, confidence, actor, ts)",
  "item_response(session, item, value,","  shown_at, answered_at)",
  "~never UPDATE. A correction is a new row;","~a view resolves current value by precedence."],"accent",tsize=16)
d.box(xs[2],y,bw,178,"Structure (versioned)",
 ["taxonomy_node — SCD-2, ltree path","question_skill — the frozen Q-matrix",
  "chapter_weight — board weights + source","question + embedding (pgvector)",
  "~a report six months old regenerates","~against the taxonomy as it was then."],"plain",tsize=16)
d.box(xs[3],y,bw,178,"Control",
 ["data_quality_flag — what blocks a report","analysis_run — code + model versions",
  "sheet_template, school_ink_profile","policy_decision (later, for the RL layer)",
  "~run_id tags every derived row, so any","~number traces back to its inputs."],"plain",tsize=16)

# object store
oy=352
d.tag(40,oy,"OBJECT STORE · S3 / MinIO · SSE-KMS · LIFECYCLE EXPIRY",C["mark"],12.5)
d.box(40,oy+20,780,150,"Full page images + assembled PDF",
 ["Restricted access — these contain the student's handwriting.","Retention clock set per school (e.g. 180 days after verification).",
  "The PDF is for humans; the page images are what crops, provenance","and any re-processing need. Storing only the PDF loses both.",
  "~s3://yaadhum/scripts/{school}/{assessment}/{student}/{page}.jpg"],"plain",tsize=16)
d.box(848,oy+20,772,150,"Mark crops",
 ["A crop of a single handwritten digit. Contains no name, no PII,","no substantive handwriting. These are what a review screen shows,",
  "what provenance links point at, and the only images that ever","leave for model training.",
  "~every MarkFact carries the crop_uri it came from"],"verify",tsize=16)

# boundary
by=548
d.line(40,by,1620,by,C["mark"],3)
d.tag(40,by-20,"TRAINING BOUNDARY — CROSSED ONLY BY CROPS AND LABELS, NEVER BY A NAME OR A MARK SHEET",C["mark"],12.5)

# ml corpus
d.tag(40,by+22,"ml_corpus · SEPARATE SCHEMA, SEPARATE CREDENTIALS · THIS IS WHAT MAKES 'TRAIN LATER' POSSIBLE",C["verify"],12.5)
my=by+44
d.box(40,my,504,196,"Evidence",
 ["capture_asset — uri, sha256, quality,","  device_hint, ink_profile, consent_class",
  "crop — asset, kind, layer, bbox,","  preproc_ver (so it regenerates identically)",
  "","~student identity here is a pseudonymous UUID.","~The mapping lives in the operational plane."],"verify",tsize=16)
d.box(568,my,504,196,"Model behaviour",
 ["prediction — backend, model_version,","  distribution (FULL, not just argmax),",
  "  confidence, calibrated, latency, cost","",
  "~Stored for EVERY prediction, including the","~ones auto-accepted. Storing only reviewed","~crops gives you a training set of hard cases only."],"verify",tsize=16)
d.box(1096,my,524,196,"Human judgement",
 ["human_label — value, labeler, mode,","  time_taken_ms  (slow label = hard crop)",
  "disagreement — source_a vs source_b","dataset_snapshot + eval_run (reproducible)","",
  "~40 students x 30 questions x 2 tests","~= 2,400 crops per class per term."],"accent",tsize=16)

d.arrow([(1470,oy+170),(1470,by-6)],C["verify"],2.2)
d.text(1490,by-32,"CROPS + LABELS ONLY",12,FM,C["verify"])
d.text(430,oy+186,"page images STOP here — they never enter the training corpus",12,FM,C["mark"],anchor="ma")

d.line(40,H-92,1620,H-92,C["ink"],2)
d.text(40,H-76,"The five rules that keep this corpus usable",16,FB,C["ink"])
d.text(40,H-50,"1. Store every prediction, not only reviewed ones.   2. Store the distribution, not the argmax — calibration needs it and you cannot recover it later.   3. Append-only: never delete a label.",14,FR,C["ink2"])
d.text(40,H-28,"4. Record time-taken on every human label — it is a free difficulty annotation.   5. consent_class is set at capture time. Retrofitting consent is not possible, so build the flag on day one.",14,FR,C["ink2"])
d.save("d4.png"); print("ok")
