/**
 * Keywords field helpers: DOL Tags footer HTML paste and space → "; " normalization.
 */

const TAGS_HTML_MARKERS = /card-footer|agency_abv|#mainTitle/i;

function tagTextFromSpan(span: Element): string | null {
  const anchor = span.querySelector("a");
  const t = ((anchor ?? span).textContent || "").trim();
  if (!t || /^tags:?$/i.test(t)) return null;
  return t.toLowerCase();
}

/** DOL Tags HTML → "keyword1; keyword2; ..." (lowercase), or null if not a match. */
export function convertTagsHtmlPaste(input: string): string | null {
  const raw = input.trim();
  if (!raw || !/<[a-z][\s\S]*>/i.test(raw) || !TAGS_HTML_MARKERS.test(raw)) {
    return null;
  }

  const doc = new DOMParser().parseFromString(raw, "text/html");
  const keywords: string[] = [];

  doc.querySelectorAll("span.agency_abv").forEach((span) => {
    const t = tagTextFromSpan(span);
    if (t) keywords.push(t);
  });

  if (keywords.length === 0) {
    doc
      .querySelectorAll(
        ".card-footer span a, a[href='#mainTitle'], a[href=\"#mainTitle\"]"
      )
      .forEach((a) => {
        const t = (a.textContent || "").trim();
        if (!t || /^tags:?$/i.test(t)) return;
        keywords.push(t.toLowerCase());
      });
  }

  if (keywords.length === 0) return null;
  return keywords.join("; ");
}

/** Convert spaces to "; " when no commas or semicolons present. */
export function normalizeKeywords(value: string): string {
  const fromTags = convertTagsHtmlPaste(value);
  if (fromTags !== null) return fromTags;

  const trimmed = value.replace(/\s+/g, " ").trim();
  if (!trimmed) return "";
  if (/[;,]/.test(trimmed)) return value;
  if (/\s/.test(trimmed)) {
    return trimmed.split(/\s+/).filter(Boolean).join("; ");
  }
  return value;
}

/** Prefer clipboard HTML, then plain text, then keyword normalization. */
export function keywordsFromClipboard(clipboard: DataTransfer): string {
  const html = clipboard.getData("text/html") || "";
  const plain = clipboard.getData("text/plain") || "";
  return convertTagsHtmlPaste(html) ?? convertTagsHtmlPaste(plain) ?? normalizeKeywords(plain);
}
