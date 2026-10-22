/** Fix legacy extraction heading markup in the readable view, preserving the source text. */
export function normalizeExtractedHeadings(markdown: string): string {
  let fence: { marker: string; length: number } | null = null;
  let previousNonempty = "";
  return markdown.split(/\r?\n/).map((line) => {
    const fenceMatch = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
    if (fenceMatch) {
      const run = fenceMatch[1];
      if (!fence) fence = { marker: run[0], length: run.length };
      else if (run[0] === fence.marker && run.length >= fence.length && !fenceMatch[2].trim()) fence = null;
      return line;
    }
    if (fence) return line;
    const heading = line.match(/^( {0,3})#{1,6}[\t ]+(.+)$/);
    if (!heading) {
      if (line.trim()) previousNonempty = line.trim();
      return line;
    }
    const plain = heading[2].normalize("NFC")
      .replace(/<sup\b[^>]*>.*?<\/sup>/gi, "")
      .replace(/<[^>]+>/g, "")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/[*_`]/g, "").trim();
    const candidate = plain.match(/^(?:Điều\s+\d+[a-zđ]?|Chương\s+[IVXLCDM\d]+[a-z]?|(?:Tiểu\s+)?Mục\s+\d+|Phần\s+thứ\s+[\p{L}\d]+|Phụ\s+lục(?:\s+[A-Z\d]+)?)(?![\p{L}\p{N}_])(.*)$/iu);
    if (!candidate) {
      previousNonempty = line;
      return line;
    }
    const tail = candidate[1].trim();
    const firstLetter = tail.match(/\p{L}/u)?.[0];
    const explicitReference = /^Điều\s+/iu.test(plain) && /^(?:Nghị định|Luật|Bộ luật|Thông tư|Quyết định|Pháp lệnh)\s+(?:này|số|năm|của|và)(?=[^\p{L}\p{N}_]|$)/iu.test(tail);
    const bareReference = /^Điều\s+\d+[a-zđ]?\.?$/iu.test(plain) && !/^\s*#/.test(previousNonempty)
      && /[,;]$/.test(previousNonempty) && /Điều\s+\d+/iu.test(previousNonempty);
    const isCitation = explicitReference || bareReference || /^[,;]/.test(tail) || (
      !/^[.:]/.test(tail) && firstLetter !== undefined && firstLetter !== firstLetter.toUpperCase()
    );
    const output = isCitation ? heading[1] + heading[2] : line;
    previousNonempty = output.trim();
    return output;
  }).join("\n");
}
