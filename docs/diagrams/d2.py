from diag import D, C, FM, FB, FR
W,H = 1660, 880
d = D(W,H,"Frontend View — Three Journeys, One Application",
      "Next.js 15 App Router. The role boundary is enforced in Postgres, not in the UI.")

# --- Student journey
d.tag(40,120,"JOURNEY A · STUDENT  ·  NO ACCOUNT, ONE CLASS CODE  ·  ENDS AT 'THANK YOU'",C["mark"],12.5)
y=142; bw=290; gap=22
xs=[40+i*(bw+gap) for i in range(5)]
scr=[("1  Landing",["Your logo + school name","Parental consent notice","~/t/[classCode]"]),
     ("2  Profile form",["Name, age, gender","Class, section, roll no","~react-hook-form + Zod"]),
     ("3  Instructions",["~8 minutes, 36 questions","EN / TA language toggle","~next-intl"]),
     ("4  The test",["6 screens x 6 items","Autosave on every tap","~Dexie · works offline"]),
     ("5  Thank you",["No score. No code.","No stream suggestion.","~journey ends here"])]
for x,(t,l) in zip(xs,scr):
    d.box(x,y,bw,116,t,l,"accent" if t.startswith(("2","4")) else ("verify" if t.startswith("5") else "plain"),tsize=16)
for i in range(4):
    d.arrow([(xs[i]+bw, y+58),(xs[i+1]-6, y+58)])
d.box(40,y+130,1580,44,None,["Resume by roll number + class code. A closed tab, a dead battery or a dropped Wi-Fi connection loses nothing — every answer is written the moment it is tapped."],"chip",pad=13)

# --- boundary
by=352
d.line(40,by,1620,by,C["mark"],3)
d.tag(40,by-22,"ROLE BOUNDARY — NO STUDENT ROUTE RETURNS A SCORE, A CODE OR A REPORT",C["mark"],12.5)
d.text(1620,by+10,"enforced by row-level security in PostgreSQL, not by hiding a button",12,FM,C["ink3"],anchor="ra")

# --- Teacher journey
d.tag(40,by+44,"JOURNEY B · TEACHER  ·  THE SCANNER  ·  AUTHENTICATED",C["mark"],12.5)
y2=by+66
tb=[("Pick / scan QR",["Binds to roster","~pyzbar on server"]),
    ("CAPTURING page n",["Live quad overlay","~4 quality metrics @10fps"]),
    ("QUALITY SCORE",["blur · glare · coverage · skew","~shutter locks until pass"]),
    ("PREVIEW strip",["Thumbnails of all pages","~amber badge if weak"]),
    ("COMPLETE",["Explicit button","~upload begins here"])]
for x,(t,l) in zip(xs,tb):
    d.box(x,y2,bw,100,t,l,"accent" if t in("CAPTURING page n","QUALITY SCORE") else ("verify" if t=="COMPLETE" else "plain"),tsize=15.5)
for i in range(4):
    d.arrow([(xs[i]+bw, y2+50),(xs[i+1]-6, y2+50)])
# retake loop
d.arrow([(xs[3]+bw/2, y2+100),(xs[3]+bw/2, y2+130),(xs[1]+bw/2, y2+130),(xs[1]+bw/2, y2+104)],C["mark"],1.8)
d.text((xs[1]+xs[3])/2+bw/2, y2+136,"RETAKE — re-shoots THAT page only and keeps its position in the sequence",12,FM,C["mark"],anchor="ma")
d.arrow([(xs[3]+bw, y2+50),(xs[4]-6, y2+50)])
d.box(40,y2+164,1580,44,None,["Pages live only in IndexedDB until Complete. Nothing reaches the server mid-scan, the whole flow works with no network, and a 24-hour purge clears any staffroom laptop automatically."],"chip",pad=13)

# --- Principal journey
py=y2+232
d.line(40,py,1620,py,C["rule"],1)
d.tag(40,py+18,"JOURNEY C · PRINCIPAL / ADMIN  ·  AUTHENTICATED",C["mark"],12.5)
y3=py+40
pb=[("Class roster",["40 students, live status","~complete / partial / flagged"]),
    ("Review queue",["Crop beside proposed value","~ordered by impact, not arrival"]),
    ("Student report",["Interest profile OR marks","~links back to source pixels"]),
    ("Cohort dashboard",["Class weakness patterns","~stream demand forecast"]),
    ("Accuracy panel",["Live audit-sample error rate","~proof, not a claim"])]
for x,(t,l) in zip(xs,pb):
    d.box(x,y3,bw,100,t,l,"accent" if t=="Review queue" else ("verify" if t=="Accuracy panel" else "plain"),tsize=15.5)
for i in range(4):
    d.arrow([(xs[i]+bw, y3+50),(xs[i+1]-6, y3+50)])

d.line(40,H-72,1620,H-72,C["rule"],1)
d.text(40,H-56,"Shared frontend stack:  Next.js 15 · TypeScript · Tailwind + shadcn/ui · TanStack Query · react-hook-form + Zod · next-intl (EN/TA) · Dexie (IndexedDB) · getUserMedia + OpenCV.js",14.5,FR,C["ink2"])
d.text(40,H-32,"One deployable. The test, the scanner and the dashboard share auth, the student table and the report layer — they are three routes, not three applications.",14.5,FR,C["ink2"])
d.save("d2.png"); print("ok")
