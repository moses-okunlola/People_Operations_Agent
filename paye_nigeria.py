"""
paye_nigeria.py
Nigeria PAYE (Pay-As-You-Earn) calculation under the Nigeria Tax Act
2025 (effective 1 January 2026).

SOURCE / BASIS (checked via web search, July 2026 — cite before trusting
in production, tax law changes):
  - Four tax reform bills signed into law 26 June 2025; new regime
    effective 1 January 2026.
  - Annual tax bands (chargeable income, NGN):
        0            - 800,000     : 0%
        800,001      - 3,000,000   : 15%
        3,000,001    - 12,000,000  : 18%
        12,000,001   - 25,000,000  : 21%
        25,000,001   - 50,000,000  : 23%
        above 50,000,000           : 25%
  - The old Consolidated Relief Allowance (CRA) is abolished.
  - New reliefs before tax is applied:
        - Rent relief: 20% of gross income, capped at NGN 500,000/year
        - Pension contribution: 8% of gross (statutory, employee share)
          — deducted before tax, same as before
        - NHF (National Housing Fund): 2.5% of gross, statutory for
          many employees — deducted before tax if applicable

This module is intentionally self-contained (one function you can unit
test) so the tax logic is easy to audit and easy to update if/when the
Finance/Tax Act changes again — do not bury tax rules inside PDF layout
code.
"""

from dataclasses import dataclass

# --- 2026 Nigeria Tax Act annual PAYE bands (lower_bound, rate) ---
PAYE_BANDS_2026 = [
    (0, 800_000, 0.00),
    (800_000, 3_000_000, 0.15),
    (3_000_000, 12_000_000, 0.18),
    (12_000_000, 25_000_000, 0.21),
    (25_000_000, 50_000_000, 0.23),
    (50_000_000, float("inf"), 0.25),
]

RENT_RELIEF_RATE = 0.20
RENT_RELIEF_CAP = 500_000
PENSION_RATE = 0.08          # employee statutory contribution
NHF_RATE = 0.025             # National Housing Fund, employee contribution


@dataclass
class NigeriaPayeResult:
    gross_annual: float
    pension_contribution: float
    nhf_contribution: float
    rent_relief: float
    chargeable_income: float
    annual_tax: float
    monthly_tax: float
    band_breakdown: list  # list of (band_low, band_high, rate, tax_in_band)


def calculate_nigeria_paye(gross_annual_ngn: float, include_nhf: bool = True) -> NigeriaPayeResult:
    """Compute Nigeria PAYE tax on an annual gross salary (NGN),
    under the Nigeria Tax Act 2025 / effective 2026 regime.

    Deduction order (all before tax is applied to what's left):
      1. Pension contribution (8% of gross)
      2. NHF (2.5% of gross) - optional, some employees/sectors are exempt
      3. Rent relief (20% of gross, capped at NGN 500,000)
    """
    pension = gross_annual_ngn * PENSION_RATE
    nhf = gross_annual_ngn * NHF_RATE if include_nhf else 0.0
    rent_relief = min(gross_annual_ngn * RENT_RELIEF_RATE, RENT_RELIEF_CAP)

    chargeable_income = max(gross_annual_ngn - pension - nhf - rent_relief, 0)

    tax = 0.0
    band_breakdown = []
    remaining = chargeable_income
    for low, high, rate in PAYE_BANDS_2026:
        if remaining <= 0:
            break
        band_width = high - low
        amount_in_band = min(remaining, band_width)
        band_tax = amount_in_band * rate
        if amount_in_band > 0:
            band_breakdown.append((low, high, rate, round(band_tax, 2)))
        tax += band_tax
        remaining -= amount_in_band

    return NigeriaPayeResult(
        gross_annual=gross_annual_ngn,
        pension_contribution=round(pension, 2),
        nhf_contribution=round(nhf, 2),
        rent_relief=round(rent_relief, 2),
        chargeable_income=round(chargeable_income, 2),
        annual_tax=round(tax, 2),
        monthly_tax=round(tax / 12, 2),
        band_breakdown=band_breakdown,
    )


def explain_paye(result: NigeriaPayeResult) -> str:
    lines = [
        f"Gross annual income: NGN {result.gross_annual:,.2f}",
        f"Less: Pension contribution (8%): NGN {result.pension_contribution:,.2f}",
        f"Less: NHF contribution (2.5%): NGN {result.nhf_contribution:,.2f}",
        f"Less: Rent relief (20% of gross, capped at NGN 500,000): NGN {result.rent_relief:,.2f}",
        f"= Chargeable (taxable) income: NGN {result.chargeable_income:,.2f}",
        "",
        "Tax by band:",
    ]
    for low, high, rate, band_tax in result.band_breakdown:
        high_label = f"{high:,.0f}" if high != float("inf") else "and above"
        lines.append(f"  NGN {low:,.0f} - {high_label} @ {rate*100:.0f}% = NGN {band_tax:,.2f}")
    lines.append(f"\nTotal annual PAYE tax: NGN {result.annual_tax:,.2f}")
    lines.append(f"Monthly PAYE tax: NGN {result.monthly_tax:,.2f}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Quick sanity check against a couple of round numbers
    for gross in [1_200_000, 6_000_000, 15_000_000, 60_000_000]:
        r = calculate_nigeria_paye(gross)
        print(f"\n=== Gross annual: NGN {gross:,.0f} ===")
        print(explain_paye(r))
