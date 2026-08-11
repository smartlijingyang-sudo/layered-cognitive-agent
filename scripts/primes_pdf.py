"""Find primes under 200 and generate a PDF explaining the logic."""

from __future__ import annotations

import math
from pathlib import Path


def sieve_of_eratosthenes(limit: int) -> list[int]:
    """Return all primes < limit using the Sieve of Eratosthenes."""
    if limit < 2:
        return []
    is_prime = [True] * limit
    is_prime[0] = is_prime[1] = False
    for i in range(2, math.isqrt(limit) + 1):
        if is_prime[i]:
            for j in range(i * i, limit, i):
                is_prime[j] = False
    return [i for i, flag in enumerate(is_prime) if flag]


def generate_pdf(primes: list[int], output_path: str | Path) -> Path:
    """Generate a PDF document explaining the prime-finding logic."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=25 * mm,
        rightMargin=25 * mm,
        topMargin=25 * mm,
        bottomMargin=25 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontSize=22,
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        spaceBefore=16,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "CustomBody",
        parent=styles["BodyText"],
        fontSize=11,
        leading=16,
        spaceAfter=6,
    )
    code_style = ParagraphStyle(
        "Code",
        parent=styles["Code"],
        fontSize=9,
        leading=13,
        leftIndent=12,
        spaceAfter=8,
    )

    elements = []

    elements.append(Paragraph("Primes Under 200", title_style))
    elements.append(
        Paragraph(
            "A visual guide to the Sieve of Eratosthenes algorithm",
            body_style,
        )
    )
    elements.append(Spacer(1, 8 * mm))

    elements.append(Paragraph("1. What Is a Prime Number?", heading_style))
    elements.append(
        Paragraph(
            "A prime number is a natural number greater than 1 that has no positive divisors "
            "other than 1 and itself. For example, 2, 3, 5, 7 are primes; 4, 6, 8, 9 are not.",
            body_style,
        )
    )

    elements.append(Paragraph("2. Algorithm: Sieve of Eratosthenes", heading_style))
    elements.append(
        Paragraph(
            "The Sieve of Eratosthenes is one of the oldest and most efficient algorithms "
            "for finding all primes up to a given limit. It works by iteratively marking "
            "the multiples of each prime as composite.",
            body_style,
        )
    )

    elements.append(Paragraph("3. Step-by-Step Logic", heading_style))
    steps = [
        "Create a list of consecutive integers from 2 to N-1.",
        "Start with the first prime number, p = 2.",
        "Mark all multiples of p (p*p, p*p+p, ...) as composite.",
        "Find the next unmarked number > p; this is the next prime.",
        "Repeat steps 3-4 until p*p >= N.",
        "All unmarked numbers are primes.",
    ]
    for i, step in enumerate(steps, 1):
        elements.append(Paragraph(f"<b>Step {i}:</b> {step}", body_style))

    elements.append(Paragraph("4. Implementation", heading_style))
    code_lines = [
        "def sieve_of_eratosthenes(limit):",
        "    is_prime = [True] * limit",
        "    is_prime[0] = is_prime[1] = False",
        "    for i in range(2, isqrt(limit) + 1):",
        "        if is_prime[i]:",
        "            for j in range(i*i, limit, i):",
        "                is_prime[j] = False",
        "    return [i for i, v in enumerate(is_prime) if v]",
    ]
    for line in code_lines:
        elements.append(Paragraph(line.replace(" ", "&nbsp;"), code_style))

    elements.append(Paragraph("5. Complexity", heading_style))
    elements.append(
        Paragraph(
            "<b>Time:</b> O(N log log N) — nearly linear, extremely efficient.<br/>"
            "<b>Space:</b> O(N) — one boolean per number.",
            body_style,
        )
    )

    elements.append(Paragraph("6. Results: 46 Primes Under 200", heading_style))
    elements.append(
        Paragraph(
            f"Found <b>{len(primes)}</b> prime numbers less than 200:",
            body_style,
        )
    )

    col_count = 8
    rows = []
    for i in range(0, len(primes), col_count):
        rows.append(primes[i : i + col_count])
    while len(rows[-1]) < col_count:
        rows[-1].append("")

    table_style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4a90d9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )
    table = Table(rows, colWidths=[22 * mm] * col_count)
    table.setStyle(table_style)
    elements.append(table)

    elements.append(Spacer(1, 8 * mm))
    elements.append(Paragraph("7. Why It Matters", heading_style))
    elements.append(
        Paragraph(
            "Prime numbers are fundamental to cryptography (RSA, Diffie-Hellman), "
            "hash table sizing, random number generation, and number theory research. "
            "The Sieve remains the go-to algorithm for generating small-to-medium prime lists.",
            body_style,
        )
    )

    doc.build(elements)
    return path


def main() -> None:
    limit = 200
    primes = sieve_of_eratosthenes(limit)
    print(f"Found {len(primes)} primes under {limit}:")
    print(primes)

    output_dir = Path(__file__).resolve().parent.parent / "output"
    pdf_path = generate_pdf(primes, output_dir / "primes_under_200.pdf")
    print(f"PDF generated: {pdf_path}")


if __name__ == "__main__":
    main()
