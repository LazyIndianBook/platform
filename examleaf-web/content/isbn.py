"""ISBN-13 (research-commerce-gst.md 6): free from the Raja Rammohun Roy National Agency, one per format (print and
e-book differ), a new one for a substantial change of the text and never for an unchanged reprint. Checked when a book
or a product is made or its ISBN changes, with python-stdnum's checksum (as erp/contract.py checks what goes to
ERPNext); a value saved before the check stays until it is changed."""

from django.core.exceptions import ValidationError
from stdnum import isbn
from stdnum.exceptions import ValidationError as InvalidNumber

MESSAGE = "Not a valid ISBN-13: 13 digits starting 978 or 979, the last one its check digit (hyphens may stay)."


def validate_isbn13(value):
    """The 13 digits of a valid ISBN-13 (spaces and hyphens dropped), else ValidationError."""
    try:
        digits = isbn.validate(value)
    except InvalidNumber as error:
        raise ValidationError(MESSAGE, code="invalid_isbn") from error
    if isbn.isbn_type(digits) != "ISBN13":
        raise ValidationError(MESSAGE, code="invalid_isbn")
    return digits


def changed_isbn(value, before):
    """`value` checked when it differs from what was saved (`before`; None for a new record): the 13 digits; an
    unchanged or empty one as it is."""
    value = (value or "").strip()
    if not value or value == (before or ""):
        return value
    return validate_isbn13(value)


if __name__ == "__main__":  # python content/isbn.py
    assert validate_isbn13("978-0-306-40615-7") == "9780306406157"
    for bad in ("978-0-306-40615-8", "0-306-40615-2", "97803064061", "isbn"):
        try:
            validate_isbn13(bad)
        except ValidationError:
            continue
        raise AssertionError(bad)
    assert changed_isbn("978-0-306-40615-8", "978-0-306-40615-8") == "978-0-306-40615-8"  # left as it was saved
    print("ok")
