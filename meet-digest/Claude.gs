/**
 * One Claude call per MEETING, not per person. The model must see the whole
 * conversation to know that "Ravi said Priya should own the API contract" is
 * Priya's item — routing that line is impossible from Priya's own utterances.
 */

const DIGEST_TOOL = {
  name: 'emit_digests',
  description: 'Emit one digest per named participant.',
  input_schema: {
    type: 'object',
    properties: {
      digests: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            person:  { type: 'string', description: 'Exactly as given in the participant list.' },
            summary: { type: 'string', description: 'One or two sentences: only what changed for this person.' },
            my_commitments: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  task:  { type: 'string' },
                  due:   { type: 'string', description: 'ISO date, or "" if none was stated. Never invent one.' },
                  quote: { type: 'string', description: 'Verbatim line this came from.' }
                },
                required: ['task', 'due', 'quote']
              }
            },
            mentions_of_me: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  speaker: { type: 'string' },
                  quote:   { type: 'string' }
                },
                required: ['speaker', 'quote']
              }
            },
            open_questions_for_me:  { type: 'array', items: { type: 'string' } },
            decisions_affecting_me: { type: 'array', items: { type: 'string' } }
          },
          required: ['person', 'summary', 'my_commitments', 'mentions_of_me',
                     'open_questions_for_me', 'decisions_affecting_me']
        }
      }
    },
    required: ['digests']
  }
};

/**
 * THIS PROMPT IS WHERE THE QUALITY LIVES. When a digest reads wrong, change these
 * rules before you change any code.
 */
function buildPrompt(script, names) {
  return [
    'Below is a timestamped meeting transcript. Produce one digest per participant listed.',
    '',
    `Participants: ${names.join(', ')}`,
    '',
    'Rules:',
    '- A digest is about what the person NEEDS, not what they SAID. Never summarise a',
    "  person's own speech back to them — they were in the meeting.",
    '- mentions_of_me must contain lines spoken by OTHER people that name or clearly',
    '  refer to this person. This is the most valuable section; do not leave it thin.',
    '- Only record a commitment if the person actually accepted it. "Could you look at X?"',
    '  with no answer is an open question, not a commitment.',
    '- Never infer a deadline that was not spoken. An empty string is correct and expected.',
    '- Every quote must be verbatim from the transcript. Do not clean up grammar.',
    '- If a person has nothing meaningful, return them with empty arrays. Do not pad.',
    '- Ignore small talk, scheduling chatter and audio problems entirely.',
    '',
    '--- TRANSCRIPT ---',
    script
  ].join('\n');
}

/** Returns { <personName>: digest }. Retries once on 429/5xx. */
function askClaude(script, names) {
  const payload = {
    model: CONFIG.model,
    max_tokens: 4096,
    tools: [DIGEST_TOOL],
    tool_choice: { type: 'tool', name: 'emit_digests' },
    messages: [{ role: 'user', content: buildPrompt(script, names) }]
  };

  let res;
  for (let attempt = 0; attempt < 2; attempt++) {
    res = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', {
      method: 'post',
      contentType: 'application/json',
      headers: { 'x-api-key': CONFIG.claudeKey, 'anthropic-version': '2023-06-01' },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
    const code = res.getResponseCode();
    if (code === 200) break;
    if (code !== 429 && code < 500) break;   // not retryable
    Utilities.sleep(5000);
  }

  if (res.getResponseCode() !== 200) {
    throw new Error(`Claude HTTP ${res.getResponseCode()}: ${res.getContentText()}`);
  }

  const body  = JSON.parse(res.getContentText());
  const block = body.content.find(c => c.type === 'tool_use');
  if (!block) throw new Error('Claude returned no tool_use block.');

  const out = {};
  block.input.digests.forEach(d => { out[d.person] = d; });
  return out;
}
