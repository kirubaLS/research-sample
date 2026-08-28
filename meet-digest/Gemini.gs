/**
 * Gemini via the AI Studio API. This is the default provider.
 *
 * Structured output is enforced with responseMimeType + responseSchema, which is
 * Gemini's equivalent of Claude's forced tool call — the model cannot return prose,
 * so nothing downstream has to parse free text.
 */
function callGemini(prompt) {
  if (!CONFIG.geminiKey) throw new Error('GEMINI_API_KEY script property is not set.');

  const url = 'https://generativelanguage.googleapis.com/v1beta/models/'
            + `${CONFIG.model}:generateContent?key=${encodeURIComponent(CONFIG.geminiKey)}`;

  const res = fetchWithRetry(url, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({
      contents: [{ role: 'user', parts: [{ text: prompt }] }],
      generationConfig: {
        responseMimeType: 'application/json',
        responseSchema: DIGEST_SCHEMA,
        temperature: 0.2,
        maxOutputTokens: 8192
      }
    }),
    muteHttpExceptions: true
  });

  if (res.getResponseCode() !== 200) {
    throw new Error(`Gemini HTTP ${res.getResponseCode()}: ${res.getContentText()}`);
  }

  const body = JSON.parse(res.getContentText());
  const cand = (body.candidates || [])[0];
  if (!cand) throw new Error(`Gemini returned no candidate: ${res.getContentText()}`);
  if (cand.finishReason === 'MAX_TOKENS') {
    throw new Error('Gemini hit the output limit — the JSON is truncated. Raise maxOutputTokens.');
  }

  const text = (cand.content.parts || []).map(p => p.text || '').join('');
  return JSON.parse(text);
}
