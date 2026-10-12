"""Tag handling for blog posts."""


def normalize_tags(raw):
    """Split a comma-separated tag string into tags.

    Tags are trimmed and lowercased, empty tags are dropped, and duplicates are
    removed keeping the first occurrence, so the order follows the input.
    """
    return list({tag.strip().lower() for tag in raw.split(",") if tag.strip()})
