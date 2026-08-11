#!/usr/bin/env python3
"""Find all prime numbers under 200 and write a PDF explaining the algorithm."""

from __future__ import annotations

import math
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

UPPER_BOUND = 200
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "output" / "primes_under_200.pdf"


def sieve_of_eratosthenes(limit: int) -> list[int]:
    """Return all primes strictly less than *limit* using the Sieve of Eratosthenes."""
    if limit < 2:
        return []
    is_prime = [True] * limit
    is_prime[0] = is_prime[1] = False
    for candidate in range(2, math.isqrt(limit - 1) + 1):
        if is_prime[candidate]:
            for multiple in range(candidate * candidate, limit, candidate):
                is_prime[multiple] = False
    return [n for n, flag in enumerate(is_prime) if flag]


def build_pdf(primes: list[int], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCN",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        spaceAfter=12,
    )
    body = ParagraphStyle(
        "BodyCN",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=16,
        spaceAfter=8,
    )
    code_style = ParagraphStyle(
        "CodeBlock",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=9,
        leading=13,
        backColor=colors.HexColor("#f4f4f4"),
        borderPadding=6,
        spaceAfter=10,
    )

    story: list[object] = [
        Paragraph(f"Prime Numbers Below {UPPER_BOUND}", title_style),
        Paragraph(
            "This document explains how we find all prime numbers less than 200 "
            "using the Sieve of Eratosthenes.",
            body,
        ),
        Paragraph("<b>Algorithm (Sieve of Eratosthenes)</b>", body),
        Paragraph(
            "1. Create a boolean list <i>is_prime[0..199]</i>, initially all True.<br/>"
            "2. Mark 0 and 1 as not prime.<br/>"
            "3. For each <i>p</i> from 2 to sqrt(199): if <i>is_prime[p]</i> is True, "
            "mark every multiple of <i>p</i> (starting at p²) as False.<br/>"
            "4. Collect indices where <i>is_prime[n]</i> is still True.",
            body,
        ),
        Paragraph("<b>Why start marking at p²?</b>", body),
        Paragraph(
            "Any composite number n = p × q with p ≤ q already has a smaller factor "
            "marked when we processed that factor. Multiples below p² were crossed out "
            "by smaller primes, so p² is the first unmarked multiple of p.",
            body,
        ),
        Paragraph("<b>Complexity</b>", body),
        Paragraph(
            "Time: O(n log log n). Space: O(n). For n=200 this is negligible.",
            body,
        ),
        Paragraph("<b>Core Python logic</b>", body),
        Paragraph(
            "<font face='Courier' size='9'>"
            "is_prime = [True] * 200<br/>"
            "is_prime[0] = is_prime[1] = False<br/>"
            "for p in range(2, int(200**0.5)+1):<br/>"
            "&nbsp;&nbsp;if is_prime[p]:<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;for m in range(p*p, 200, p): is_prime[m]=False<br/>"
            "primes = [i for i,v in enumerate(is_prime) if v]"
            "</font>",
            code_style,
        ),
        Paragraph(f"<b>Result: {len(primes)} primes found</b>", body),
        Paragraph(", ".join(str(p) for p in primes), body),
        Spacer(1, 6 * mm),
    ]

    # 10-column grid for compact display
    cols = 10
    rows: list[list[str]] = []
    row: list[str] = []
    for idx, prime in enumerate(primes, start=1):
        row.append(str(prime))
        if idx % cols == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row + [""] * (cols - len(row)))

    table = Table(rows, colWidths=[16 * mm] * cols)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef6ff")),
            ]
        )
    )
    story.append(table)
    doc.build(story)


def main() -> None:
    primes = sieve_of_eratosthenes(UPPER_BOUND)
    build_pdf(primes, OUTPUT_PATH)
    print(f"Found {len(primes)} primes below {UPPER_BOUND}")
    print("Primes:", primes)
    print(f"PDF written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
