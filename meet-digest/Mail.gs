function sendDigest(person, d, record, unmatched) {
  const when = Utilities.formatDate(new Date(record.startTime),
                                    Session.getScriptTimeZone(), 'd MMM, h:mm a');
  const dry  = CONFIG.dryRunTo;

  const esc = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const li  = s => `<li style="margin-bottom:8px">${s}</li>`;
  const section = (title, items) => items.length ? `
    <h3 style="font:600 13px system-ui;text-transform:uppercase;letter-spacing:.04em;
               color:#555;margin:22px 0 8px">${title}</h3>
    <ul style="margin:0;padding-left:20px">${items.join('')}</ul>` : '';

  const html = `
  <div style="max-width:600px;font:14px/1.6 -apple-system,system-ui,sans-serif;color:#1a1a1a">
    <p style="color:#888;margin:0 0 4px;font-size:13px">${esc(when)}</p>
    <p style="margin:0 0 4px">${esc(d.summary)}</p>

    ${section('Your commitments', d.my_commitments.map(c => li(
      `<b>${esc(c.task)}</b>${c.due ? ` <span style="color:#c0392b">— due ${esc(c.due)}</span>` : ''}
       <div style="color:#777;font-size:13px;margin-top:2px">&ldquo;${esc(c.quote)}&rdquo;</div>`)))}

    ${section('Questions waiting on you', d.open_questions_for_me.map(q => li(esc(q))))}

    ${section('You were mentioned', d.mentions_of_me.map(m => li(
      `<b>${esc(m.speaker)}:</b> &ldquo;${esc(m.quote)}&rdquo;`)))}

    ${section('Decisions affecting your work', d.decisions_affecting_me.map(x => li(esc(x))))}

    ${unmatched.length ? `<p style="color:#aaa;font-size:12px;margin-top:26px">
      Not matched to an account, so not mailed: ${esc(unmatched.join(', '))}</p>` : ''}

    <p style="color:#aaa;font-size:12px;margin-top:26px;border-top:1px solid #eee;padding-top:12px">
      Generated automatically from the meeting transcript. Reply here if anything looks wrong.</p>
  </div>`;

  MailApp.sendEmail({
    to: dry || person.email,
    subject: `${dry ? `[dry run -> ${person.email}] ` : ''}Your notes — ${when}`,
    htmlBody: html
  });

  console.log(`Sent to ${dry || person.email} (for ${person.name}).`);
}
