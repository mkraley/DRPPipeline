"""Temporary script to inspect BTS ROSA P page structure."""

from __future__ import annotations

import json
from collectors.PlaywrightSession import PlaywrightSession

URLS = [
    "https://rosap.ntl.bts.gov/view/dot/54854",
    "https://rosap.ntl.bts.gov/view/dot/78551",
    "https://rosap.ntl.bts.gov/view/dot/88268",
]

JS = """() => {
  const out = {title: document.querySelector('h1')?.innerText?.trim(), details: {}, downloads: []};
  const text = document.body.innerText;
  const lines = text.split('\\n').map(l=>l.trim()).filter(Boolean);
  for (let i=0; i<lines.length; i++) {
    const line = lines[i];
    if (line.endsWith(':') && i+1 < lines.length) {
      const key = line.slice(0,-1);
      const val = lines[i+1];
      if (['Alternative Title','Abstract','Geographical Coverage','Format','DOI','Resource Type','Series','Subject/TRT Terms','File Type','Download URL','Main Document Checksum','Corporate Creators','Corporate Publisher'].includes(key)) {
        out.details[key] = val;
      }
    }
  }
  document.querySelectorAll('a[href]').forEach(a => {
    const href = a.href;
    const text = a.innerText.trim();
    if (href.includes('/view/dot/') && (href.includes('DS') || /\\.(zip|pdf|csv|xlsx|xls|tar|gz)$/i.test(href))) {
      out.downloads.push({text, href});
    }
  });
  const html = document.documentElement.innerHTML;
  const matches = [...html.matchAll(/href="([^"]*DS\\d+[^"]*)"/g)].map(m=>m[1]);
  out.ds_hrefs = [...new Set(matches)];
  return out;
}"""


def main() -> None:
    """Inspect sample BTS pages."""
    for url in URLS:
        session = PlaywrightSession(headless=True)
        session.start()
        session.goto(url, wait_until="networkidle", timeout=120_000)
        page = session.page
        assert page is not None
        page.wait_for_timeout(2000)
        data = page.evaluate(JS)
        session.close()
        print("===", url)
        print(json.dumps(data, indent=2)[:5000])
        print()


if __name__ == "__main__":
    main()
