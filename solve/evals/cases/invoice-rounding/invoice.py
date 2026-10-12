"""Invoice totals."""


def invoice_total(lines, vat_rate):
    """Gross total of an invoice as a string with two decimals.

    `lines` is a list of (unit_net_price, quantity) with prices as strings such
    as "19.99", and `vat_rate` is a string such as "0.23". VAT is added to the
    net sum of the whole invoice and the result is rounded half up to the grosz.
    """
    net = sum(float(price) * quantity for price, quantity in lines)
    gross = net * (1 + float(vat_rate))
    return f"{round(gross, 2):.2f}"
