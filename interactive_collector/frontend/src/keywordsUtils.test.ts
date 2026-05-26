import { describe, expect, it } from "vitest";

import { convertTagsHtmlPaste, normalizeKeywords } from "./keywordsUtils";

const SAMPLE_TAGS_HTML = `<div class="card-footer">Tags:<span class="px-1 mx-1 pb-1 small rounded agency_abv" style="white-space: nowrap;"><a href="#mainTitle">EMPLOYERS</a></span><span class="px-1 mx-1 pb-1 small rounded agency_abv" style="white-space: nowrap;"><a href="#mainTitle">INVESTIGATION</a></span><span class="px-1 mx-1 pb-1 small rounded agency_abv" style="white-space: nowrap;"><a href="#mainTitle">PENALTIES</a></span><span class="px-1 mx-1 pb-1 small rounded agency_abv" style="white-space: nowrap;"><a href="#mainTitle">PLANS</a></span><span class="px-1 mx-1 pb-1 small rounded agency_abv" style="white-space: nowrap;"><a href="#mainTitle">STATE</a></span></div>`;

const SAMPLE_TAGS_SPAN_ONLY = `<div style="overflow-wrap: break-word;"><span class="px-1 mx-1 pb-1 small rounded agency_abv" style="white-space: nowrap;">ACCIDENTS</span><span class="px-1 mx-1 pb-1 small rounded agency_abv" style="white-space: nowrap;">CONTRACTORS</span><span class="px-1 mx-1 pb-1 small rounded agency_abv" style="white-space: nowrap;">CONTROLLERS</span><span class="px-1 mx-1 pb-1 small rounded agency_abv" style="white-space: nowrap;">FATALITIES</span><span class="px-1 mx-1 pb-1 small rounded agency_abv" style="white-space: nowrap;">INJURY OR ILLNESS</span><span class="px-1 mx-1 pb-1 small rounded agency_abv" style="white-space: nowrap;">MINES</span><span class="px-1 mx-1 pb-1 small rounded agency_abv" style="white-space: nowrap;">OCCUPATIONS</span><span class="px-1 mx-1 pb-1 small rounded agency_abv" style="white-space: nowrap;">OPERATORS</span><span class="px-1 mx-1 pb-1 small rounded agency_abv" style="white-space: nowrap;">STATE</span></div>`;

describe("convertTagsHtmlPaste", () => {
  it("converts DOL Tags footer HTML to lowercase semicolon-separated keywords", () => {
    expect(convertTagsHtmlPaste(SAMPLE_TAGS_HTML)).toBe(
      "employers; investigation; penalties; plans; state"
    );
  });

  it("converts agency_abv spans without anchor links", () => {
    expect(convertTagsHtmlPaste(SAMPLE_TAGS_SPAN_ONLY)).toBe(
      "accidents; contractors; controllers; fatalities; injury or illness; mines; occupations; operators; state"
    );
  });

  it("returns null for unrelated HTML", () => {
    expect(convertTagsHtmlPaste("<p>Hello <b>world</b></p>")).toBeNull();
  });

  it("returns null for plain text", () => {
    expect(convertTagsHtmlPaste("employers investigation")).toBeNull();
  });
});

describe("normalizeKeywords", () => {
  it("still converts space-separated words when not tag HTML", () => {
    expect(normalizeKeywords("foo bar baz")).toBe("foo; bar; baz");
  });

  it("converts tag HTML on blur-style normalization", () => {
    expect(normalizeKeywords(SAMPLE_TAGS_HTML)).toBe(
      "employers; investigation; penalties; plans; state"
    );
  });
});
