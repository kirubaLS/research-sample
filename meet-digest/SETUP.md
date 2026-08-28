# Setup — making the digests send themselves

About 45 minutes end to end. Do the steps in order; step 3 is the one that fails for most
people and it is much easier to fix before there is any code in the project.

---

## 0. Check you can actually do this

- **Meet transcripts must be available on your Workspace edition** (Business Standard and
  above). If the *Take notes / transcript* button is missing in a call, stop here — there is
  no transcript for anything downstream to read.
- **Transcripts must be turned on for your OU** in Admin console → Apps → Google Meet →
  Meet video settings → Transcription.
- **You need Google Cloud console access** for the project you will create in step 1. You do
  not need to be a Workspace super admin for that, but you do for step 2's Admin SDK scope.

### Whose account should this run as

The Meet API only returns conference records for meetings the **authenticated account was in**.
So install this on the account that hosts the team meeting — usually yours.

If you later want one script covering meetings it did not attend, that is a different setup:
a service account with domain-wide delegation, authorised by a super admin. Do not start
there. Get one person's meetings working first.

---

## 1. Google Cloud project

1. Go to <https://console.cloud.google.com/projectcreate>, name it `meet-digest`, create.
2. Note the **project number** (Cloud console → top-left project picker → the long number,
   not the ID). You need it in step 3.
3. Enable two APIs — search each by name in **APIs & Services → Library** and click Enable:
   - **Google Meet API**
   - **Admin SDK API**
4. **APIs & Services → OAuth consent screen**:
   - User type: **Internal** (everyone is in your Workspace, so no verification review).
   - App name `Meet Digest`, your email for both support and developer contact. Save.

> You need a *standard* Cloud project, not the hidden default one Apps Script creates,
> because the Meet API is not enabled on default projects and you cannot enable it there.
> This is the single most common reason this build stalls.

---

## 2. Anthropic API key

<https://console.anthropic.com> → API Keys → Create key. Copy it now; it is shown once.

Budget check: a 60-minute transcript is roughly 8–10k input tokens and one call per meeting,
so a team doing five meetings a week costs cents per month, not dollars.

---

## 3. Apps Script project

1. <https://script.google.com/home/projects/create> → rename it `Meet Digest`.
2. **Project Settings** (gear icon) → tick **Show "appsscript.json" manifest file**.
3. **Project Settings → Google Cloud Platform (GCP) Project → Change project** → paste the
   **project number** from step 1 → Set project.

   *If this rejects the number:* you are not an owner/editor on the Cloud project, or the
   OAuth consent screen in step 1.4 was never saved. Both must be true before it will link.

4. Copy the files in this folder into the editor. Click **+ → Script** for each `.gs` file and
   name it to match (`Config`, `Setup`, `Meet`, `Main`, `Claude`, `Mail` — the editor adds the
   `.gs`). Replace the contents of `appsscript.json` with the one here.

   Or skip the clicking with [clasp](https://github.com/google/clasp):

   ```bash
   npm i -g @google/clasp
   clasp login
   cd meet-digest
   cp .clasp.json.example .clasp.json      # paste your Script ID from Project Settings
   clasp push
   ```

5. Set `timeZone` in `appsscript.json` to your own if you are not on `Asia/Kolkata` —
   it decides the times printed in the emails.

---

## 4. Configuration values

**Project Settings → Script Properties → Add script property.** Four properties:

| Property | Value | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | the key from step 2 | yes |
| `DRY_RUN_TO` | **your own email address** | see below |
| `LOOKBACK_HOURS` | `24` | no |
| `KILL_PHRASE` | `off the record` | no |

**`DRY_RUN_TO` is the safety catch.** While it is set, every digest goes to you instead of the
real recipient, with the intended recipient in the subject line. Leave it set until step 7.
Nothing here is hard-coded in the source, so the API key never lands in git.

---

## 5. Authorise and verify

In the editor, pick **`checkConfig`** from the function dropdown and click **Run**.

The first run triggers the consent screen. Because the app is Internal and unverified you will
see *"Google hasn't verified this app"* — click **Advanced → Go to Meet Digest (unsafe)**. This
is your own script; the warning is about it not having been through Google's public review.

Read the log (**Execution log**, bottom panel). You want four green lines. The common failures:

| Log message | Fix |
|---|---|
| `Meet API failed: HTTP 403 ... not enabled` | Step 1.3 — enable the Google Meet API, then wait a minute |
| `Meet API failed: HTTP 403 ... insufficient scope` | The manifest was not saved before you ran. Save `appsscript.json`, then **Run** again to re-consent |
| `No conference records found` | This account hosted no transcribed meeting in 7 days. Run a two-minute test call with transcription on |
| `Admin Directory failed` | Step 1.3 — enable Admin SDK API; and the account needs the directory read scope, which on a locked-down tenant means a super admin grants it |

Do not go on until `checkConfig` is clean.

---

## 6. Test on a real meeting

Run **`testOnce`**. It takes the most recent transcribed meeting, builds the digests, and mails
them — all to `DRY_RUN_TO`, since you set it.

Read them as if you were each recipient. Almost certainly you will want to adjust something.
**When a digest reads wrong, edit the rules list in `buildPrompt` in `Claude.gs`, not the code.**
That list is the entire product. Re-run `testOnce` after each change — first run
`resetLedger` if you are re-testing the same meeting, or it will be skipped as already done.

---

## 7. Turn on the automation

This is the step that makes it automatic.

1. Run **`installTrigger`**. That creates a time-driven trigger firing `main` every 15 minutes.
2. Confirm it: **Triggers** in the left sidebar (alarm-clock icon) — one row, `main`,
   Time-driven, Minutes timer, Every 15 minutes.

That is it. It now runs whether or not any browser is open. `main` finds conference records
that ended since the last run, skips any already in its ledger, and sends.

**Do not delete `DRY_RUN_TO` yet.** Let it run for a week with everything landing in your
inbox. You will learn what the model gets wrong on *your* meetings while the cost of being
wrong is zero.

### Going live

Two options, and I would do them in this order:

1. **Host forwards, one month.** Leave `DRY_RUN_TO` set. You get everyone's digest and forward
   the good ones by hand. Slow, but nothing reaches the team unreviewed.
2. **Direct send.** Delete the `DRY_RUN_TO` property. Digests now go to participants.

Before you do (2): **tell the team in standup first.** A mail that quotes a colleague back at
someone, arriving unannounced, reads as surveillance even when it is useful.

---

## 8. Knowing when it breaks

- **Executions** in the left sidebar is the run history — every `main` firing, with logs.
- Apps Script emails the project owner a daily summary of failed trigger runs by default.
  Confirm it is on at **Triggers → the trigger's ⋮ menu → Failure notification settings**.
- A meeting that throws is deliberately *not* written to the ledger, so the next run retries it.
  A meeting that keeps failing will retry every 15 minutes until it ages out of the lookback
  window — check Executions if the same error repeats.

## Operational commands

Run these by hand from the editor whenever you need them:

| Function | What it does |
|---|---|
| `checkConfig` | Health check. Sends nothing. Run this first when something is wrong |
| `testOnce` | Process the most recent meeting only |
| `installTrigger` | Start (or restart) the 15-minute automation |
| `removeTriggers` | Stop the automation; the code stays put |
| `resetLedger` | Forget which meetings were processed, so they can be re-sent |

---

## Quota and cost ceilings

| Limit | Consumer Gmail | Workspace |
|---|---|---|
| `MailApp` recipients/day | 100 | 1,500 |
| Script runtime per execution | 6 min | 6 min |
| `UrlFetchApp` calls/day | 20,000 | 100,000 |

A team meeting of eight people is eight emails. You will not come close. The 6-minute runtime
is the only real ceiling: a backlog of many meetings in one run could hit it — the ledger makes
that safe, since the next firing picks up exactly where it stopped.

---

## When to move off the 15-minute poll

Only when the delay actually annoys someone. The event-driven version subscribes the meeting
space through the Google Workspace Events API and receives
`google.workspace.meet.transcript.v2.fileGenerationEnded` over Pub/Sub, which fires the moment
the transcript is ready. It needs a Cloud Function, a Pub/Sub topic, and a subscription that
must be renewed — real infrastructure, for a few minutes of latency.

`processConference` lifts into that Cloud Function unchanged, so nothing here is wasted work.
Design notes are in [`../docs/meet-transcript-per-person-mail.md`](../docs/meet-transcript-per-person-mail.md).
