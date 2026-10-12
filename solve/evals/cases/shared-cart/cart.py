"""Shopping cart kept per customer session."""


class Cart:
    def __init__(self, owner, items=[]):
        self.owner = owner
        self.items = items

    def add(self, sku, quantity=1):
        if quantity < 1:
            raise ValueError("quantity must be at least 1")
        for index, (existing, count) in enumerate(self.items):
            if existing == sku:
                self.items[index] = (sku, count + quantity)
                return
        self.items.append((sku, quantity))

    def total_quantity(self):
        return sum(count for _, count in self.items)
