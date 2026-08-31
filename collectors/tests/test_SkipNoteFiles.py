"""Unit tests for collectors.SkipNoteFiles."""

import unittest

from collectors.SkipNoteFiles import parse_skip_note_publication_files


class TestParseSkipNotePublicationFiles(unittest.TestCase):
    """Tests for parse_skip_note_publication_files."""

    def test_none_and_empty_return_empty(self) -> None:
        """None or empty status_notes yields no files."""
        self.assertEqual(parse_skip_note_publication_files(None), [])
        self.assertEqual(parse_skip_note_publication_files(""), [])

    def test_parses_single_line(self) -> None:
        """A single skip line parses to (name, url, bytes)."""
        notes = (
            "Skipped download (>1GB): A01L4_1.zip (2.9 GB) - "
            "download manually: https://ndownloader.figshare.com/files/43634028"
        )
        files = parse_skip_note_publication_files(notes)
        self.assertEqual(len(files), 1)
        name, url, size = files[0]
        self.assertEqual(name, "A01L4_1.zip")
        self.assertEqual(url, "https://ndownloader.figshare.com/files/43634028")
        self.assertEqual(size, int(2.9 * 1024**3))

    def test_parses_multiple_lines(self) -> None:
        """Multiple skip lines each produce an entry, ignoring other notes."""
        notes = (
            "Collected 14 files\n"
            "Skipped download (>1GB): big.zip (5.0 GB) - download manually: http://x/1\n"
            "Skipped download (>1GB): huge.tar (2.0 GB) - download manually: http://y/2"
        )
        files = parse_skip_note_publication_files(notes)
        self.assertEqual([f[0] for f in files], ["big.zip", "huge.tar"])
        self.assertEqual([f[1] for f in files], ["http://x/1", "http://y/2"])
        self.assertEqual(files[0][2], 5 * 1024**3)
        self.assertEqual(files[1][2], 2 * 1024**3)

    def test_unparseable_size_yields_none(self) -> None:
        """A malformed size token leaves size as None but keeps the entry."""
        notes = "Skipped download (>1GB): odd.zip (huge) - download manually: http://z/3"
        files = parse_skip_note_publication_files(notes)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0][0], "odd.zip")
        self.assertIsNone(files[0][2])

    def test_parses_sizeless_skip_line(self) -> None:
        """Cumulative deferrals without catalog sizes still parse."""
        notes = (
            "Skipped download (>1GB): README_File.txt - "
            "download manually: https://rosap.ntl.bts.gov/view/dot/1/file.txt"
        )
        files = parse_skip_note_publication_files(notes)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0][0], "README_File.txt")
        self.assertIsNone(files[0][2])


if __name__ == "__main__":
    unittest.main()
