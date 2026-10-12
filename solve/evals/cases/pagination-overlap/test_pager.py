import unittest

from pager import page, page_count


class PageTest(unittest.TestCase):
    def test_first_page(self):
        self.assertEqual(page(list(range(10)), 1, 4), [0, 1, 2, 3])

    def test_page_count(self):
        self.assertEqual(page_count(10, 4), 3)

    def test_rejects_page_zero(self):
        with self.assertRaises(ValueError):
            page([1, 2, 3], 0, 2)


if __name__ == "__main__":
    unittest.main()
