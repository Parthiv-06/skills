import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import count_tokens  # noqa: E402


class CountTokensTest(unittest.TestCase):
    def test_falls_back_to_labeled_estimate(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(count_tokens, "tiktoken", None):
            self.assertEqual(count_tokens.count("abcd" * 100), (100, "estimated:chars/4"))

    def test_empty_text_is_zero(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(count_tokens, "tiktoken", None):
            self.assertEqual(count_tokens.count(""), (0, "estimated:chars/4"))


if __name__ == "__main__":
    unittest.main()
