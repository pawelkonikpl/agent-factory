"""A campaign's content as one client receives it: plain text turned into HTML (D4), then the
variables substituted (D3)."""

import html
import re

from app.models.client import Client

_TAG = re.compile(r"<[a-zA-Z/!][^>]*>")
_VARIABLE = re.compile(r"\{(name|email|company)\}")


def render_content(content: str, client: Client) -> str:
    # Escaped before the newlines become <br>, and substituted after, so a company name with
    # "<" stays text.
    if not _TAG.search(content):
        content = html.escape(content).replace("\r\n", "\n").replace("\n", "<br>")
    values = {
        "name": html.escape(client.company_name),
        "company": html.escape(client.company_name),
        "email": html.escape(client.primary_email),
    }
    return _VARIABLE.sub(lambda match: values[match.group(1)], content)
