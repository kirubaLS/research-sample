/** `level` drives the colour; `label` overrides the text when the bare
 * level would be ambiguous (a class-level "High" reads as high-performing
 * unless it says what is high). */
export function AttentionPill({ level, label }: { level: string; label?: string }) {
  const key = level.toLowerCase().replace(/\s+/g, "");
  return <span className={`attn attn--${key}`}>{label ?? level}</span>;
}
