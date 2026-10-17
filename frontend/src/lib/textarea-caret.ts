export type CaretCoords = { top: number; left: number; lineHeight: number };

/**
 * Computed-style properties (kebab-case) that influence how text is laid out
 * inside the textarea's content box. Everything matching is copied onto a
 * hidden measuring <div>, so its line breaks land where the textarea's do.
 */
const LAYOUT_PROPERTY = new RegExp(
  [
    "^font(-|$)",
    "^padding-",
    "^border-(top|right|bottom|left)-(width|style)$",
    "^text-(align|indent|transform|decoration)",
    "^(letter|word)-spacing$",
    "^line-height$",
    "^tab-size$",
    "^box-sizing$",
    "^(width|height)$",
    "^overflow-[xy]$",
  ].join("|"),
);

const FALLBACK_FONT_PX = 14;
const FALLBACK_LINE_RATIO = 1.4;

function buildProbe(source: CSSStyleDeclaration): HTMLDivElement {
  const probe = document.createElement("div");
  for (let i = 0; i < source.length; i += 1) {
    const name = source.item(i);
    if (LAYOUT_PROPERTY.test(name)) probe.style.setProperty(name, source.getPropertyValue(name));
  }
  // Keep the probe out of sight and wrap like a textarea does.
  Object.assign(probe.style, {
    position: "absolute",
    left: "-9999px",
    top: "0",
    visibility: "hidden",
    whiteSpace: "pre-wrap",
    overflowWrap: "break-word",
    wordBreak: "break-word",
  });
  return probe;
}

function resolveLineHeight(style: CSSStyleDeclaration): number {
  const explicit = Number.parseFloat(style.lineHeight);
  if (!Number.isNaN(explicit)) return explicit;
  const fontPx = Number.parseFloat(style.fontSize) || FALLBACK_FONT_PX;
  return fontPx * FALLBACK_LINE_RATIO;
}

/**
 * Viewport coordinates of the caret at `position` inside a textarea.
 *
 * The text before the caret is laid out in an invisible probe element styled
 * like the textarea; a marker span placed at the caret offset tells us where
 * the caret sits relative to the content box. Textarea scrolling is then
 * subtracted and the textarea's on-screen rectangle added.
 */
export function getTextareaCaretCoords(textarea: HTMLTextAreaElement, position: number): CaretCoords {
  const style = window.getComputedStyle(textarea);
  const probe = buildProbe(style);

  const text = textarea.value;
  const after = text.slice(position);
  const marker = document.createElement("span");
  // The marker carries the following text so wrapping after the caret matches too.
  marker.textContent = after.length > 0 ? after : ".";
  probe.append(document.createTextNode(text.slice(0, position)), marker);

  document.body.append(probe);
  try {
    const box = textarea.getBoundingClientRect();
    return {
      left: box.left - textarea.scrollLeft + marker.offsetLeft,
      top: box.top - textarea.scrollTop + marker.offsetTop,
      lineHeight: resolveLineHeight(style),
    };
  } finally {
    probe.remove();
  }
}
