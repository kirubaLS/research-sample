# Setup — one daily meeting, digests that send themselves

About 30 minutes. Shorter than it was: because you supply the email addresses, the whole
Admin SDK / directory-lookup path is gone, and with it the need for a super admin.

---

## First, the two questions

### "How does it connect to the Google Meet?"

**It doesn't attach to the meeting at all.** Nothing is installed into Meet, no bot joins the
call, and nobody sees anything different during the standup. There is nothing to add to the
invite.

What actually happens: Meet already writes a transcript when transcription is on, and Google
keeps it. Afterwards — up to 15 minutes later — the script asks Google *"give me the transcript
for meeting code `abc-mnop-xyz`"*, gets it as structured data, and works from that. The only
link between the script and your meeting is that **meeting code**, which you paste into a
setting in step 4.

So the only thing that has to be true inside Meet is: **transcription was running.** That is
step 1, and for a daily meeting it is the step that matters most.

### "How does it send to everyone automatically?"

Three pieces:

1. **The trigger.** Apps Script has a built-in scheduler. `installTrigger` (step 7) tells Google
   *"run `main` every 15 minutes, forever."* Google runs it on its own servers. Your laptop can
   be off.
2. **The roster.** You type the names and emails once, in step 4. The script matches each
   speaker in the transcript to that list.
3. **The send.** `MailApp.sendEmail` sends from your own Google account — the same account the
   script runs as. No SMTP, no mail service, no API key for email. Recipients see it from you.

Once step 7 is done there is no button to press, ever again. Meeting ends → within 15 minutes
everyone has their own digest.

---

## 1. Turn on transcription — automatically

This is the step people get wrong, and if it is wrong nothing else matters: **no transcript, no
digest.** For a daily standup you cannot rely on someone remembering to click *Start transcript*.

**Admin console → Apps → Google Workspace → Google Meet → Meet video settings → Automatic
transcription.** Turn it on for the OU or group that owns the meeting.

Two things to know before you count on it:

- **Editions.** Automatic transcription needs Business Plus, Enterprise Standard/Plus,
  Education Plus, or Enterprise Essentials (Plus). Plain Business Standard has manual
  transcripts only — they work, someone just has to click the button each morning.
- **It does not apply to recurring meetings created before you switched it on.** This is
  almost certainly your situation. **Delete your existing daily Meet event and recreate it**
  after enabling the setting, or transcripts will silently never start and you will spend an
  afternoon debugging a script that is working perfectly.

Verify it before going further: check tomorrow's calendar entry and confirm *Meeting transcript*
is ticked. Then run one real meeting and confirm a transcript lands in Drive.

## 2. Get your meeting code

From the daily meeting's join link:

```
https://meet.google.com/abc-mnop-xyz
                        ^^^^^^^^^^^^  this part
```

For a recurring Calendar event this code stays the same every day, which is exactly what makes
this work. Keep it — it goes in step 4.

## 3. Get a Gemini API key

<https://aistudio.google.com/apikey> → Create API key. Copy it.

**Then enable billing on that key**, even though the free tier would cover one meeting a day.
This is not about quota. On the free tier, Google's terms let it use submitted content to improve
its products, and let human reviewers read it — and what you are submitting is your team's
meeting transcripts. On the paid tier Google commits not to train on your content. It costs on
the order of ₹100–200 a month for a daily stand-up, and it is not a close call.

Correcting an earlier note in this guide: the free tier is fine for the *test runs* in step 7,
using a meeting whose contents you would not mind being read. It is not the right basis for
running this continuously.

## 4. Cloud project + Apps Script

**4a. Cloud project** — <https://console.cloud.google.com/projectcreate>, name it `meet-digest`.

- **APIs & Services → Library** → search **Google Meet API** → **Enable**. (Just this one now.)
- **APIs & Services → OAuth consent screen** → User type **Internal** → app name `Meet Digest`,
  your email in both contact fields → Save.
- Note the **project number** from the project picker at top-left.

> It must be a *standard* Cloud project, not the hidden default one Apps Script creates. The
> Meet API cannot be enabled on default projects, and this is the most common reason the build
> stalls.

**4b. Apps Script** — <https://script.google.com/home/projects/create>, rename to `Meet Digest`.

- **Project Settings** → tick **Show "appsscript.json" manifest file**.
- **Project Settings → Google Cloud Platform (GCP) Project → Change project** → paste the
  project *number* → Set project.
- Copy the files from this folder in (**+ → Script** for each, named `Config`, `Roster`, `Meet`,
  `AI`, `Gemini`, `Claude`, `Main`, `Mail`, `Setup`), and replace `appsscript.json` with the one
  here. Set `timeZone` to yours if you are not on `Asia/Kolkata` — it sets the times in the email.

  Or with [clasp](https://github.com/google/clasp):

  ```bash
  npm i -g @google/clasp && clasp login
  cd meet-digest && cp .clasp.json.example .clasp.json   # paste your Script ID
  clasp push
  ```

## 5. Settings — this is where you put the addresses

**Project Settings → Script Properties.** Nothing is hard-coded, so no key ever reaches git.

| Property | Value |
|---|---|
| `MEETING_CODE` | `abc-mnop-xyz` from step 2 |
| `ROSTER` | the list below |
| `GEMINI_API_KEY` | the key from step 3 |
| `DRY_RUN_TO` | **your own email** — leave this set for the first week |

`ROSTER` is one person per line, `Display Name = email`:

```
Kingshuk Dey = kingshuk@leadstrategus.com
Ravi Kumar   = ravi@leadstrategus.com
Priya S      = priya@leadstrategus.com
```

**The name on the left must match how the person shows up in Meet**, because that is the only
handle the transcript gives you. First names work too (`Ravi = ...` matches "Ravi Kumar") as long
as they are unambiguous — two Ravis and the script refuses to guess and mails neither. `checkConfig`
in the next step prints exactly who matched and who did not, so you can fix the spelling in a minute.

Optional: `AI_PROVIDER` = `claude` (with `ANTHROPIC_API_KEY`) to switch models, `AI_MODEL` to pin
a different one, `KILL_PHRASE` to change the withhold phrase from `off the record`.

## 6. Authorise and check

Pick **`checkConfig`** in the function dropdown → **Run**.

First run asks for consent. *"Google hasn't verified this app"* → **Advanced → Go to Meet Digest
(unsafe)**. It is your own script; the warning means it has not been through Google's public
review, which Internal apps do not need.

Read the **Execution log**. It prints every participant it saw and which email each matched:

```
+ Pinned to meeting code abc-mnop-xyz.
+ Roster has 3 people: Kingshuk Dey, Ravi Kumar, Priya S.
+ Provider gemini, model gemini-3.6-flash.
+ Most recent meeting participants -> Kingshuk Dey (kingshuk@...), Ravi Kumar (ravi@...), Guest (NO MATCH)
```

Common failures:

| Message | Fix |
|---|---|
| `Meet API failed: HTTP 403 ... not enabled` | Step 4a — enable the Google Meet API, wait a minute |
| `HTTP 403 ... insufficient scope` | `appsscript.json` was not saved before running. Save it, **Run** again to re-consent |
| `No meetings matched` | Wrong `MEETING_CODE`, or this account was not in those calls |
| `That meeting has no transcript` | Step 1. Transcription was not running during the call |
| `(NO MATCH)` next to a name | Fix that person's spelling in `ROSTER` to match exactly |

Do not continue until this is clean.

## 7. Test on a real meeting

Run **`testOnce`**. It takes your most recent standup, builds every digest, and mails them all to
`DRY_RUN_TO` — with the intended recipient shown in the subject line.

Read them as each person. You will want to change something. **When a digest reads wrong, edit the
rules list in `buildPrompt` in `AI.gs`, not the code.** That list is the whole product. Re-run
`testOnce` after each change — run `resetLedger` first if you are retesting the same meeting,
otherwise it is skipped as already done.

## 8. Turn on the automation

Run **`installTrigger`**.

Confirm it: **Triggers** in the left sidebar (alarm-clock icon) — one row, `main`, Time-driven,
Minutes timer, every 15 minutes. That is the automation. It now runs on Google's servers whether
or not anything of yours is open.

**Leave `DRY_RUN_TO` set for a week.** Every morning you will get the whole team's digests in your
own inbox and learn what the model gets wrong on *your* meetings while the cost of being wrong is
zero. Then:

1. **Host forwards, one month** (recommended) — keep `DRY_RUN_TO`, forward the good ones by hand.
2. **Direct send** — delete the `DRY_RUN_TO` property. Digests now go to the team.

Before (2): **tell the team at standup first.** A mail that quotes a colleague back at someone,
arriving unannounced, reads as surveillance even when it is useful.

---

## Daily operation

Nothing. That is the point. Meeting ends → within 15 minutes everyone has their digest.

The three things that will ever go wrong, in order of likelihood:

1. **Transcription did not start.** Log says `no transcript`. Step 1 — and check whether the
   recurring event predates the automatic-transcription setting.
2. **Someone's name changed** in their Google profile, so `ROSTER` no longer matches. Log says
   `NO MATCH`. Fix the line.
3. **Gemini quota.** Log says `HTTP 429`. The script retries once. If you are still on the free
   tier, this is one more reason to enable billing (step 3).

| Function | What it does |
|---|---|
| `checkConfig` | Health check. Sends nothing. Run this first when anything is wrong |
| `testOnce` | Process the most recent meeting only |
| `installTrigger` | Start (or restart) the automation |
| `removeTriggers` | Stop it. The code stays put |
| `resetLedger` | Forget which meetings were done, so they can be re-sent |

**Executions** in the sidebar is the full run history with logs. Apps Script also emails the owner
a daily summary of failed runs — confirm it at **Triggers → ⋮ → Failure notification settings**.

A meeting that errors is deliberately *not* recorded as done, so the next run retries it rather
than losing it.

---

## Limits

| Limit | Consumer Gmail | Workspace |
|---|---|---|
| `MailApp` recipients/day | 100 | 1,500 |
| Runtime per execution | 6 min | 6 min |
| `UrlFetchApp` calls/day | 20,000 | 100,000 |

One daily standup of eight people is eight emails a day. You are nowhere near any of these.

## Later: instant instead of 15 minutes

Only if the delay ever actually bothers someone. The event-driven version subscribes the meeting
space through the Google Workspace Events API and receives
`google.workspace.meet.transcript.v2.fileGenerationEnded` over Pub/Sub the moment the transcript is
ready. It needs a Cloud Function, a Pub/Sub topic, and a subscription that must be renewed — real
infrastructure for a few minutes of latency. `processConference` moves there unchanged.

Design notes: [`../docs/meet-transcript-per-person-mail.md`](../docs/meet-transcript-per-person-mail.md)
