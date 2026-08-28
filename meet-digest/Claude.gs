/** Claude, used only when AI_PROVIDER is set to "claude". Same prompt, same schema. */
function callClaude(prompt) {
  if (!CONFIG.claudeKey) throw new Error('ANTHROPIC_API_KEY script property is not set.');

  const res = fetchWithRetry('https://api.anthropic.com/v1/messages', {
    method: 'post',
    contentType: 'application/json',
    headers: { 'x-api-key': CONFIG.claudeKey, 'anthropic-version': '2023-06-01' },
    payload: JSON.stringify({
      model: CONFIG.model,
      max_tokens: 8192,
      tools: [{ name: 'emit_digests', description: 'Emit one digest per participant.',
                input_schema: DIGEST_SCHEMA }],
      tool_choice: { type: 'tool', name: 'emit_digests' },
      messages: [{ role: 'user', content: prompt }]
    }),
    muteHttpExceptions: true
  });

  if (res.getResponseCode() !== 200) {
    throw new Error(`Claude HTTP ${res.getResponseCode()}: ${res.getContentText()}`);
  }

  const block = JSON.parse(res.getContentText()).content.find(c => c.type === 'tool_use');
  if (!block) throw new Error('Claude returned no tool_use block.');
  return block.input;
}
