"""Unit tests for web2pdf's --layout mode (no network, no browser).

Run: uv run --with requests,beautifulsoup4,readability-lxml,lxml_html_clean \
       python -m unittest discover -s plugins/paper-review/tests
"""

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import web2pdf


class LayoutViewportTest(unittest.TestCase):
    def test_default_is_the_a4_column_at_1_35(self):
        # 210 mm minus 2 x 6 mm, at 96 px/in, divided by the print scale.
        self.assertEqual(web2pdf.layout_viewport(1.35, 0.6), (554, 797))

    def test_scale_one_without_margins_is_the_whole_a4_page(self):
        self.assertEqual(web2pdf.layout_viewport(1.0, 0.0), (793, 1122))

    def test_larger_scale_means_narrower_layout(self):
        self.assertLess(web2pdf.layout_viewport(2.0, 0.6)[0], web2pdf.layout_viewport(1.0, 0.6)[0])


class LayoutArgumentsTest(unittest.TestCase):
    def run_main(self, *argv):
        err = io.StringIO()
        with mock.patch.object(sys, "argv", ["web2pdf.py", *argv]), contextlib.redirect_stderr(err), \
             self.assertRaises(SystemExit) as cm:
            web2pdf.main()
        return cm.exception.code, err.getvalue()

    def test_layout_rejects_no_images(self):
        code, err = self.run_main("https://example.com", "--layout", "--no-images")
        self.assertEqual(code, 2)
        self.assertIn("--no-images cannot be combined with --layout", err)

    def test_layout_rejects_absurd_scale(self):
        code, err = self.run_main("https://example.com", "--layout", "--scale", "9")
        self.assertEqual(code, 2)
        self.assertIn("--scale must be between", err)

    def test_layout_does_not_fetch_or_extract(self):
        with mock.patch.object(web2pdf, "layout_to_pdf", return_value="T") as printer, \
             mock.patch.object(web2pdf, "fetch_page") as fetch, \
             contextlib.redirect_stdout(io.StringIO()), \
             mock.patch.object(sys, "argv", ["web2pdf.py", "https://example.com", "--layout", "-o", "out.pdf"]):
            web2pdf.main()
        printer.assert_called_once_with("https://example.com", "out.pdf", scale=1.35)
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
