import unittest

from tags import normalize_tags


class NormalizeTagsTest(unittest.TestCase):
    def test_normalize_tags(self):
        self.assertEqual(normalize_tags("Python, api,python , Web"), ["python", "api", "web"])


if __name__ == "__main__":
    unittest.main()
