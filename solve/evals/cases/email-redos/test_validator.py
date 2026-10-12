import unittest

from validator import is_valid_email

VALID = ["jan.kowalski@example.com", "a@b.co", "x_1-y.z@sub.example.org"]
INVALID = ["plain", "a@b", "a..b@example.com", ".a@example.com", "a b@example.com"]


class EmailTest(unittest.TestCase):
    def test_accepts_valid(self):
        for address in VALID:
            with self.subTest(address=address):
                self.assertTrue(is_valid_email(address))

    def test_rejects_invalid(self):
        for address in INVALID:
            with self.subTest(address=address):
                self.assertFalse(is_valid_email(address))


if __name__ == "__main__":
    unittest.main()
