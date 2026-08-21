"""
payslip_generator.py
Generates a simple, clean PDF payslip for an employee, on demand -
for the scenario where an employee can't get to the HRIS self-service
portal and would otherwise have to ask the payroll person directly.

Uses reportlab (pure Python, no external service needed).
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import pandas as pd

from bonus_engine import calculate_bonus, POLICY_VERSION
from paye_nigeria import calculate_nigeria_paye, PENSION_RATE as NG_PENSION_RATE, NHF_RATE as NG_NHF_RATE

# Nigeria-based locations get real Nigeria Tax Act 2025 (effective 2026) PAYE.
# The synthetic dataset stores salaries in USD for comparability across
# locations, so for Nigeria-based employees we convert to NGN using a
# documented, illustrative FX assumption before running PAYE. Swap this for
# a live rate in a production version.
NIGERIA_LOCATIONS = {"Lagos", "Abuja", "Port Harcourt"}
USD_TO_NGN_RATE = 1600.0  # illustrative assumption, update as needed

# Everywhere else (remote UK/Canada/US roles) uses a simplified flat-rate
# stand-in - NOT real UK/Canada/US tax law. Flag this clearly on the payslip.
GENERIC_TAX_RATE = 0.20
GENERIC_PENSION_RATE = 0.08
HEALTH_BENEFIT_DEDUCTION = 45.00  # flat monthly employee contribution (non-Nigeria only)


def generate_payslip_pdf(employee: pd.Series, month_label: str, out_path: str):
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontSize=16, spaceAfter=4)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, textColor=colors.grey)

    currency = employee.get("currency", "USD")
    location = employee.get("location", "")
    is_nigeria = location in NIGERIA_LOCATIONS

    bb = calculate_bonus(employee)

    if is_nigeria:
        # Convert USD annual figures to NGN, then run real Nigeria Tax Act
        # 2025 (effective 2026) PAYE on the annual gross, and divide down
        # to a monthly figure - PAYE is fundamentally an annual calculation.
        currency = "NGN"
        annual_base_ngn = float(employee["annual_base_salary"]) * USD_TO_NGN_RATE
        annual_bonus_ngn = bb.total_bonus * USD_TO_NGN_RATE
        annual_gross_ngn = annual_base_ngn + annual_bonus_ngn

        paye = calculate_nigeria_paye(annual_gross_ngn)

        monthly_base = annual_base_ngn / 12
        monthly_bonus_accrual = annual_bonus_ngn / 12
        gross = monthly_base + monthly_bonus_accrual
        tax = paye.monthly_tax
        pension = paye.pension_contribution / 12
        nhf = paye.nhf_contribution / 12
        rent_relief = paye.rent_relief / 12
        net = gross - tax - pension - nhf

        deductions = [
            ["Deductions", f"Amount ({currency})"],
            ["PAYE tax (Nigeria Tax Act 2025, progressive bands)", f"{tax:,.2f}"],
            [f"Pension contribution ({NG_PENSION_RATE*100:.0f}%)", f"{pension:,.2f}"],
            [f"NHF contribution ({NG_NHF_RATE*100:.1f}%)", f"{nhf:,.2f}"],
            ["Net Pay", f"{net:,.2f}"],
        ]
        tax_note = (
            f"PAYE calculated under the Nigeria Tax Act 2025 (effective 1 Jan 2026): progressive bands "
            f"0% up to NGN 800,000, then 15/18/21/23/25% at higher bands, after deducting pension (8%), "
            f"NHF (2.5%), and rent relief (20% of gross, capped at NGN 500,000/year). Annual chargeable "
            f"income for this period: NGN {paye.chargeable_income:,.2f}. USD figures converted to NGN at "
            f"an illustrative rate of 1 USD = {USD_TO_NGN_RATE:,.0f} NGN for this demo."
        )
    else:
        # Non-Nigeria locations: simplified generic stand-in, clearly flagged
        # as illustrative rather than real local tax law.
        monthly_base = float(employee["annual_base_salary"]) / 12
        monthly_bonus_accrual = bb.total_bonus / 12
        gross = monthly_base + monthly_bonus_accrual
        tax = gross * GENERIC_TAX_RATE
        pension = gross * GENERIC_PENSION_RATE
        nhf = 0.0
        net = gross - tax - pension - HEALTH_BENEFIT_DEDUCTION

        deductions = [
            ["Deductions", f"Amount ({currency})"],
            [f"Tax (simplified flat {GENERIC_TAX_RATE*100:.0f}% - illustrative only)", f"{tax:,.2f}"],
            [f"Pension contribution ({GENERIC_PENSION_RATE*100:.0f}%)", f"{pension:,.2f}"],
            ["Health benefit contribution", f"{HEALTH_BENEFIT_DEDUCTION:,.2f}"],
            ["Net Pay", f"{net:,.2f}"],
        ]
        tax_note = (
            f"Note: this location ({location}) uses a simplified flat-rate tax stand-in for demo purposes "
            f"- it is NOT real UK/Canada/US tax law. Only Nigeria-based employees (Lagos, Abuja, Port "
            f"Harcourt) use the real Nigeria Tax Act 2025 PAYE calculation in this project."
        )

    doc = SimpleDocTemplate(out_path, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    elements = []

    elements.append(Paragraph("Payslip", title_style))
    elements.append(Paragraph(f"Pay period: {month_label}  |  Generated on demand via People Ops Agent", sub_style))
    elements.append(Spacer(1, 10))

    emp_info = [
        ["Employee", f"{employee['first_name']} {employee['last_name']}"],
        ["Employee ID", employee["employee_id"]],
        ["Department", employee["department"]],
        ["Level", employee["level"]],
        ["Location", employee["location"]],
    ]
    emp_table = Table(emp_info, colWidths=[120, 300])
    emp_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(emp_table)
    elements.append(Spacer(1, 16))

    earnings = [
        ["Earnings", f"Amount ({currency})"],
        ["Base Salary (monthly)", f"{monthly_base:,.2f}"],
        ["Bonus accrual (monthly, see note below)", f"{monthly_bonus_accrual:,.2f}"],
        ["Gross Pay", f"{gross:,.2f}"],
    ]

    def styled_table(data, header_color):
        t = Table(data, colWidths=[300, 120])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), header_color),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEABOVE", (0, -1), (-1, -1), 0.75, colors.black),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ]))
        return t

    elements.append(styled_table(earnings, colors.HexColor("#2c5f8a")))
    elements.append(Spacer(1, 10))
    elements.append(styled_table(deductions, colors.HexColor("#8a2c3a")))
    elements.append(Spacer(1, 16))

    note_style = ParagraphStyle("note", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
    annual_bonus_display = annual_bonus_ngn if is_nigeria else bb.total_bonus
    elements.append(Paragraph(
        f"Note: annual bonus (total {currency} {annual_bonus_display:,.2f} under {POLICY_VERSION}) is shown here "
        f"as a 1/12 monthly accrual for illustration; in practice it is paid out at the end of the bonus cycle, "
        f"not monthly. Ask the People Ops Agent to 'explain my bonus' for the full breakdown.",
        note_style
    ))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(tax_note, note_style))

    doc.build(elements)
    return out_path


if __name__ == "__main__":
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    output_dir = repo_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(repo_root / "data" / "hr_bonus_dataset_with_bonus.csv")

    nigeria_sample = df[df["location"].isin(NIGERIA_LOCATIONS)].iloc[0]
    path = generate_payslip_pdf(nigeria_sample, "June 2026", str(output_dir / f"payslip_{nigeria_sample['employee_id']}.pdf"))
    print(f"Generated Nigeria PAYE payslip: {path} ({nigeria_sample['location']})")

    non_nigeria_sample = df[~df["location"].isin(NIGERIA_LOCATIONS)].iloc[0]
    path2 = generate_payslip_pdf(non_nigeria_sample, "June 2026", str(output_dir / f"payslip_{non_nigeria_sample['employee_id']}.pdf"))
    print(f"Generated non-Nigeria payslip: {path2} ({non_nigeria_sample['location']})")
