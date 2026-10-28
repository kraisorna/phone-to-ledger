"""Money helpers: integer satang, VAT 700bp, half-up rounding."""

VAT_RATE_BP = 700


def to_thb(satang):
    """Format satang int as THB string with 2 decimals."""
    if satang is None:
        return ""
    sign = "-" if satang < 0 else ""
    v = abs(int(satang))
    return f"{sign}{v // 100}.{v % 100:02d}"


def to_satang(thb):
    """Parse THB float/str to satang int (half-up)."""
    return int(round(float(thb) * 100))


def vat_inclusive(grand_total, rate_bp=VAT_RATE_BP):
    """VAT embedded in an inclusive total: round(total*rate/(10000+rate))."""
    return (int(grand_total) * rate_bp + (10000 + rate_bp) // 2) // (10000 + rate_bp)


def vat_exclusive(vatable, rate_bp=VAT_RATE_BP):
    """VAT on top of an exclusive base: round(vatable*rate/10000)."""
    return (int(vatable) * rate_bp + 5000) // 10000
