import unittest

from invoice import invoice_total


class InvoiceTotalTest(unittest.TestCase):
    def test_two_lines(self):
        self.assertEqual(invoice_total([("10.00", 2), ("5.00", 1)], "0.23"), "30.75")

    def test_returns_two_decimals(self):
        self.assertEqual(invoice_total([("10.00", 1)], "0.00"), "10.00")


if __name__ == "__main__":
    unittest.main()
