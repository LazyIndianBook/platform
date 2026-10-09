"""EAN-13 barcodes (plan 5.5; research-commerce-gst.md 2 and 6): a book's ISBN-13 is its EAN-13 ("Bookland": 978 and
979), drawn as an SVG for the printer and the packing slip, from the standard's patterns (GS1, ISO/IEC 15420): a
start guard, six digits in L or G patterns by the first digit's parity, a centre guard, six digits in R patterns, an
end guard; 95 modules, with a quiet zone of 11 modules on the left and 7 on the right. No library: the tables are
the standard's."""

from html import escape

L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
# the first digit is not drawn: it chooses which of the left six digits are G (even parity) rather than L
PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]
START = END = "101"
CENTRE = "01010"
LEFT_QUIET, RIGHT_QUIET = 11, 7
MODULE_MM = 0.33  # the nominal module (magnification 100%): 37.29 mm wide with its quiet zones


def check_digit(first_twelve):
    """The EAN-13 check digit of twelve digits: weights 1 and 3 from the left, the rest to the next ten."""
    total = sum(int(digit) * (3 if index % 2 else 1) for index, digit in enumerate(first_twelve))
    return str((10 - total % 10) % 10)


def modules(code):
    """The 95 modules of a valid EAN-13 (13 digits with their check digit) as "1" (bar) and "0" (space); ValueError
    for anything else."""
    if len(code) != 13 or not code.isdigit() or check_digit(code[:12]) != code[12]:
        raise ValueError(f"Not an EAN-13: {code!r}.")
    parity = PARITY[int(code[0])]
    left = "".join((L if side == "L" else G)[int(digit)] for side, digit in zip(parity, code[1:7], strict=True))
    right = "".join(R[int(digit)] for digit in code[7:])
    return START + left + CENTRE + right + END


def guard(index):
    """Whether module `index` (0 to 94) is part of a guard, drawn longer."""
    return index < 3 or 45 <= index < 50 or index >= 92


def svg(code):
    """The barcode of `code` (a valid EAN-13) as a standalone SVG: its bars, longer guards, the digits under it, the
    quiet zones white, sized for printing at the nominal module; ValueError for an invalid code."""
    bars = modules(code)
    width, height, long, text_y = LEFT_QUIET + 95 + RIGHT_QUIET, 76, 65, 73
    rects, start = [], None
    for index, bit in enumerate(bars + "0"):  # runs of bars as one rectangle each (the last "0" ends the last run)
        if bit == "1" and start is None:
            start = index
        elif bit == "0" and start is not None:
            run_height = long if guard(start) else 60
            rects.append(f'<rect x="{LEFT_QUIET + start}" y="0" width="{index - start}" height="{run_height}"/>')
            start = None
    digit = lambda x, text: f'<text x="{x}" y="{text_y}" text-anchor="middle">{text}</text>'  # noqa: E731
    digits = [digit(LEFT_QUIET - 5, code[0])]
    digits += [digit(LEFT_QUIET + 3 + 7 * i + 3.5, value) for i, value in enumerate(code[1:7])]
    digits += [digit(LEFT_QUIET + 50 + 7 * i + 3.5, value) for i, value in enumerate(code[7:])]
    label = escape(f"EAN-13 barcode {code}")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width * MODULE_MM:.2f}mm" height="{height * MODULE_MM:.2f}mm" role="img" aria-label="{label}">'
        f"<title>{label}</title>"
        f'<rect width="{width}" height="{height}" fill="#fff"/>'
        f'<g fill="#000" shape-rendering="crispEdges">{"".join(rects)}</g>'
        f'<g fill="#000" font-family="ui-monospace, Menlo, Consolas, monospace" font-size="9">{"".join(digits)}</g>'
        "</svg>"
    )
