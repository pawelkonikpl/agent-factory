from app.models.client import Client
from app.services.email_content import render_content

ACME = Client(company_name="Acme", primary_email="biuro@acme.example")


def test_plain_content_is_escaped_and_gets_br() -> None:
    rendered = render_content("Dzień dobry {name},\n<{email}> {x}", ACME)

    assert rendered == "Dzień dobry Acme,<br>&lt;biuro@acme.example&gt; {x}"


def test_crlf_becomes_one_br() -> None:
    assert render_content("Jeden\r\nDwa\nTrzy", ACME) == "Jeden<br>Dwa<br>Trzy"


def test_content_with_a_tag_keeps_its_tags_and_gets_no_br() -> None:
    rendered = render_content("<p>Dzień dobry {company}</p>\n<p>{email}</p>", ACME)

    assert rendered == "<p>Dzień dobry Acme</p>\n<p>biuro@acme.example</p>"


def test_company_and_name_are_the_company_name_and_email_the_primary_email() -> None:
    rendered = render_content("{company} {name} {email}", ACME)

    assert rendered == "Acme Acme biuro@acme.example"


def test_values_are_escaped() -> None:
    client = Client(company_name="A<B", primary_email="biuro@ab.example")

    assert render_content("<p>{company} {name}</p>", client) == "<p>A&lt;B A&lt;B</p>"
    assert render_content("{name}", client) == "A&lt;B"


def test_unknown_variables_stay() -> None:
    assert render_content("{x} {Name} {email", ACME) == "{x} {Name} {email"
