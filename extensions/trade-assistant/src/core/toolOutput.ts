export const TOOL_OUTPUT_MAX_CHARS = 8_000;
export const TOOL_OUTPUT_MAX_LINE_CHARS = 400;

export interface CompressOptions {
  maxChars?: number;
  maxLineChars?: number;
}

export function compressToolOutput(text: string, options: CompressOptions = {}): string {
  const maxChars = options.maxChars ?? TOOL_OUTPUT_MAX_CHARS;
  const maxLineChars = options.maxLineChars ?? TOOL_OUTPUT_MAX_LINE_CHARS;
  const normalized = text.replace(/\r\n?/g, '\n');
  const shortLines: string[] = [];
  let removedChars = 0;
  for (const line of normalized.split('\n')) {
    if (line.length > maxLineChars) {
      removedChars += line.length - maxLineChars;
      shortLines.push(`${line.slice(0, maxLineChars)} …[+${line.length - maxLineChars} chars]`);
    } else {
      shortLines.push(line);
    }
  }
  let joined = shortLines.join('\n').replace(/\n{3,}/g, '\n\n');
  if (joined.length <= maxChars) {
    return removedChars > 0 ? `${joined}\n…[${removedChars} characters removed from long lines]` : joined;
  }
  const headSize = Math.floor(maxChars * 0.7);
  const tailSize = maxChars - headSize;
  const head = joined.slice(0, headSize);
  const tail = joined.slice(joined.length - tailSize);
  joined = `${head}\n…[${joined.length - maxChars} characters omitted]…\n${tail}`;
  return joined;
}
