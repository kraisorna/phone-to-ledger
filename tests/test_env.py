"""Secret resolution: environment first, nearest .env upward after that.

All cases use explicit tmp dirs as the search start, so they never read
the real working directory or the developer's own .env.
"""
import os
import tempfile
import unittest
from unittest import mock

from ptl.adapters.env import resolve_secret


def _dotenv(directory, body):
    with open(os.path.join(directory, ".env"), "w", encoding="utf-8") as f:
        f.write(body)


class TestResolveSecret(unittest.TestCase):
    def test_environ_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            _dotenv(tmp, "MODEL_API_KEY=from-file\n")
            with mock.patch.dict(os.environ,
                                 {"MODEL_API_KEY": "from-env"}):
                self.assertEqual(
                    resolve_secret("MODEL_API_KEY", start=tmp), "from-env")

    def test_dotenv_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            _dotenv(tmp, "MODEL_API_KEY=from-file\n")
            with mock.patch.dict(os.environ):
                os.environ.pop("MODEL_API_KEY", None)
                self.assertEqual(
                    resolve_secret("MODEL_API_KEY", start=tmp), "from-file")

    def test_upward_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            _dotenv(tmp, "MODEL_API_KEY=from-parent\n")
            nested = os.path.join(tmp, "a", "b")
            os.makedirs(nested)
            with mock.patch.dict(os.environ):
                os.environ.pop("MODEL_API_KEY", None)
                self.assertEqual(resolve_secret("MODEL_API_KEY",
                                                start=nested),
                                 "from-parent")

    def test_nearest_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            _dotenv(tmp, "MODEL_API_KEY=from-parent\n")
            nested = os.path.join(tmp, "sub")
            os.mkdir(nested)
            _dotenv(nested, "MODEL_API_KEY=from-child\n")
            with mock.patch.dict(os.environ):
                os.environ.pop("MODEL_API_KEY", None)
                self.assertEqual(resolve_secret("MODEL_API_KEY",
                                                start=nested),
                                 "from-child")

    def test_missing_returns_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ):
                os.environ.pop("MODEL_API_KEY", None)
                self.assertIsNone(resolve_secret("MODEL_API_KEY",
                                                 start=tmp))
                self.assertEqual(resolve_secret("MODEL_API_KEY",
                                                default="d", start=tmp),
                                 "d")

    def test_parsing_tolerances(self):
        body = ("# comment\n"
                "\n"
                "export QUOTED='q val'\n"
                'DQUOTED="d val"\n'
                "EQUALS=a=b=c\n"
                "EMPTY=\n"
                "no-separator-here\n")
        with tempfile.TemporaryDirectory() as tmp:
            _dotenv(tmp, body)
            with mock.patch.dict(os.environ):
                for name in ("QUOTED", "DQUOTED", "EQUALS", "EMPTY"):
                    os.environ.pop(name, None)
                self.assertEqual(resolve_secret("QUOTED", start=tmp),
                                 "q val")
                self.assertEqual(resolve_secret("DQUOTED", start=tmp),
                                 "d val")
                self.assertEqual(resolve_secret("EQUALS", start=tmp),
                                 "a=b=c")
                self.assertIsNone(resolve_secret("EMPTY", start=tmp))


if __name__ == "__main__":
    unittest.main()
