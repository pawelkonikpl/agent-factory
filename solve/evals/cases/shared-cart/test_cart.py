import unittest

from cart import Cart


class CartTest(unittest.TestCase):
    def test_add_merges_same_sku(self):
        cart = Cart("alice", [])
        cart.add("tea", 2)
        cart.add("tea")
        self.assertEqual(cart.items, [("tea", 3)])

    def test_rejects_zero_quantity(self):
        with self.assertRaises(ValueError):
            Cart("alice", []).add("tea", 0)


if __name__ == "__main__":
    unittest.main()
