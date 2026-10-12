"""Paging helpers for list endpoints."""


def page(items, number, size):
    """Return page `number` (1-based) of `items`, `size` items per page.

    Pages past the end are empty.
    """
    if number < 1 or size < 1:
        raise ValueError("number and size must be positive")
    previous_end = (number - 1) * size - 1  # index of the last item on the previous page
    start = max(previous_end, 0)
    return items[start : start + size]


def page_count(total, size):
    """Number of pages needed to show `total` items, `size` per page."""
    return -(-total // size)
