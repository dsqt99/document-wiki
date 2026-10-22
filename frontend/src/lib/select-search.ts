/** Match document names naturally, including Vietnamese input without diacritics. */
export function matchesOption(label: string, query: string): boolean {
  const normalize = (value: string) => value.normalize("NFD").replace(/\p{M}/gu, "").replace(/[đĐ]/g, "d").toLowerCase();
  const text = normalize(label);
  return normalize(query).trim().split(/\s+/).every((word) => text.includes(word));
}
