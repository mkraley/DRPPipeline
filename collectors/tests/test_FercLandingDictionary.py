"""Tests for the embedded FERC landing-page dictionary."""

from __future__ import annotations

import unittest

from collectors.FercLandingDictionary import parse_embedded_dictionary

_HTML = """
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"dataDict":[
  {"attribute":"CID","mapping":"CID","column_id":2,"sql_type":"STRING","description":"Company id"}
]}}}</script>
"""


class TestEmbeddedDictionary(unittest.TestCase):
    """Tests for parsing dataDict from Next.js page data."""

    def test_parse_embedded_dictionary(self) -> None:
        """A non-empty dataDict is returned as rows."""
        rows = parse_embedded_dictionary(_HTML)
        self.assertEqual(rows[0]["attribute"], "CID")
        self.assertEqual(rows[0]["sql_type"], "STRING")

    def test_null_dictionary_returns_none(self) -> None:
        """dataDict null means the page has no embedded dictionary."""
        html = '<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"dataDict":null}}}</script>'
        self.assertIsNone(parse_embedded_dictionary(html))


if __name__ == "__main__":
    unittest.main()
