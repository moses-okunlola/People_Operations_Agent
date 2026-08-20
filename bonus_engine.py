"""
bonus_engine.py
Transparent, auditable multi-component bonus calculation engine.

This is the "single source of truth" for how bonuses are computed.
Every function returns not just a number but a structured breakdown
(inputs used, formula, intermediate steps) so that:
  - the analysis notebook can compute company-wide bonus figures
  - the People Ops Agent can explain any individual's bonus in plain
    English, citing the exact numbers that went into it

Bonus components (an employee may receive any combination):
  1. Performance Bonus   - everyone, based on performance_rating
  2. Sales Commission    - commission-eligible roles only, based on
                           target attainment %
  3. Retention Bonus     - flagged employees only (manager-nominated
                           retention risk), flat % of base salary
  4. Spot Bonus          - flagged "moment of excellence" events,
                           flat fixed amount

COMPANY POLICY CONSTANTS are defined at the top so they are easy to
find, audit, and cite back to an employee.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import pandas as pd

# ---------------------------------------------------------------------------
# COMPANY BONUS POLICY (documented + versioned so it can be cited to
# employees exactly like a real comp team would cite "the FY25 bonus plan")
# ---------------------------------------------------------------------------
POLICY_VERSION = "FY2026 Bonus Plan v1.0"

PERFORMANCE_BONUS_TABLE = {
    # rating range (inclusive lower bound) -> % of base salary
    5.0: 0.12,
    4.5: 0.10,
    4.0: 0.08,
    3.5: 0.05,
    3.0: 0.03,
    2.5: 0.01,
    1.0: 0.00,
}

COMMISSION_RATE = 0.10          # 10% of commission base at 100% target attainment
COMMISSION_ACCELERATOR_ABOVE = 100  # target % above which commission accelerates
COMMISSION_ACCELERATOR_RATE = 0.15  # accelerated rate applied to the portion above 100%

RETENTION_BONUS_PCT_OF_BASE = 0.08   # flat 8% of base salary
SPOT_BONUS_FLAT_AMOUNT = 500.00      # flat fixed amount, same currency as salary

# Employees with less than a full year of tenure get their annual, service-
# based bonus components (Performance, Retention) pro-rated to the portion
# of the year actually worked - standard practice in real bonus plans, and
# without it a new hire with 2 months of tenure would get a full year's
# bonus rate. Commission and Spot Bonus are NOT pro-rated: commission is
# already tied to actual attainment during however long they worked, and a
# spot bonus is a one-off recognition amount, not a service-accrued one.
PRORATE_BELOW_TENURE_YEARS = 1.0


def _performance_bonus_rate(rating: float) -> float:
    for threshold in sorted(PERFORMANCE_BONUS_TABLE.keys(), reverse=True):
        if rating >= threshold:
            return PERFORMANCE_BONUS_TABLE[threshold]
    return 0.0


@dataclass
class BonusBreakdown:
    employee_id: str
    policy_version: str = POLICY_VERSION
    performance_component: float = 0.0
    performance_explanation: str = ""
    commission_component: float = 0.0
    commission_explanation: str = ""
    retention_component: float = 0.0
    retention_explanation: str = ""
    spot_component: float = 0.0
    spot_explanation: str = ""
    total_bonus: float = 0.0
    lines: list = field(default_factory=list)

    def as_plain_english(self, name: str, currency: str) -> str:
        parts = [f"Hi {name}, here's how your bonus was calculated under the {self.policy_version}:\n"]
        for label, amt, expl in [
            ("Performance Bonus", self.performance_component, self.performance_explanation),
            ("Sales Commission", self.commission_component, self.commission_explanation),
            ("Retention Bonus", self.retention_component, self.retention_explanation),
            ("Spot Bonus", self.spot_component, self.spot_explanation),
        ]:
            if amt and amt > 0:
                parts.append(f"• {label}: {currency} {amt:,.2f}\n   {expl}")
        parts.append(f"\nTotal bonus: {currency} {self.total_bonus:,.2f}")
        return "\n".join(parts)


def calculate_bonus(employee: pd.Series) -> BonusBreakdown:
    """Compute the full bonus breakdown for a single employee row
    (a pandas Series from the hr_bonus_dataset.csv)."""

    bb = BonusBreakdown(employee_id=employee["employee_id"])
    base = float(employee["annual_base_salary"])
    currency = employee.get("currency", "USD")

    tenure_years = float(employee.get("tenure_years", PRORATE_BELOW_TENURE_YEARS))
    proration_factor = (
        round(min(tenure_years / PRORATE_BELOW_TENURE_YEARS, 1.0), 4)
        if tenure_years < PRORATE_BELOW_TENURE_YEARS
        else 1.0
    )

    # 1. Performance Bonus (everyone, pro-rated for <1 year tenure)
    rating = float(employee["performance_rating"])
    perf_rate = _performance_bonus_rate(rating)
    perf_amount = round(base * perf_rate * proration_factor, 2)
    bb.performance_component = perf_amount
    bb.performance_explanation = (
        f"Your performance rating was {rating}/5, which maps to a "
        f"{perf_rate*100:.0f}% performance bonus rate under the {POLICY_VERSION} "
        f"rating table. {perf_rate*100:.0f}% x {currency} {base:,.0f} base salary "
        f"= {currency} {round(base * perf_rate, 2):,.2f}"
    )
    if proration_factor < 1.0:
        bb.performance_explanation += (
            f", pro-rated to {proration_factor*100:.0f}% for your {tenure_years:.1f} "
            f"year(s) of tenure (less than a full year) = {currency} {perf_amount:,.2f}."
        )
    else:
        bb.performance_explanation += "."

    # 2. Sales Commission (commission-eligible only)
    if bool(employee.get("commission_eligible", False)) and pd.notna(employee.get("sales_target_attainment_pct")):
        attainment = float(employee["sales_target_attainment_pct"])
        comm_base = float(employee["sales_commission_base"])
        base_portion = min(attainment, 100) / 100 * comm_base * COMMISSION_RATE
        accel_portion = 0.0
        if attainment > COMMISSION_ACCELERATOR_ABOVE:
            accel_pct = attainment - COMMISSION_ACCELERATOR_ABOVE
            accel_portion = (accel_pct / 100) * comm_base * COMMISSION_ACCELERATOR_RATE
        comm_amount = round(base_portion + accel_portion, 2)
        bb.commission_component = comm_amount
        expl = (
            f"You hit {attainment:.1f}% of your sales target. Commission is "
            f"{COMMISSION_RATE*100:.0f}% of your {currency} {comm_base:,.0f} commission base "
            f"for the first 100% of target"
        )
        if accel_portion > 0:
            expl += (
                f", plus an accelerated {COMMISSION_ACCELERATOR_RATE*100:.0f}% rate on the "
                f"{attainment-100:.1f}% you achieved above target"
            )
        expl += f". Total commission = {currency} {comm_amount:,.2f}."
        bb.commission_explanation = expl

    # 3. Retention Bonus (flagged only, pro-rated for <1 year tenure)
    if bool(employee.get("retention_bonus_flag", False)):
        ret_amount = round(base * RETENTION_BONUS_PCT_OF_BASE * proration_factor, 2)
        bb.retention_component = ret_amount
        bb.retention_explanation = (
            f"Your manager flagged you as a retention priority this cycle, which "
            f"triggers a flat {RETENTION_BONUS_PCT_OF_BASE*100:.0f}% of base salary retention bonus: "
            f"{RETENTION_BONUS_PCT_OF_BASE*100:.0f}% x {currency} {base:,.0f} = "
            f"{currency} {round(base * RETENTION_BONUS_PCT_OF_BASE, 2):,.2f}"
        )
        if proration_factor < 1.0:
            bb.retention_explanation += (
                f", pro-rated to {proration_factor*100:.0f}% for your {tenure_years:.1f} "
                f"year(s) of tenure = {currency} {ret_amount:,.2f}."
            )
        else:
            bb.retention_explanation += "."

    # 4. Spot Bonus (flagged only)
    if bool(employee.get("spot_bonus_event", False)):
        bb.spot_component = SPOT_BONUS_FLAT_AMOUNT
        bb.spot_explanation = (
            f"You were recognized for a specific moment of excellence this cycle, "
            f"which comes with a flat spot bonus of {currency} {SPOT_BONUS_FLAT_AMOUNT:,.2f}."
        )

    bb.total_bonus = round(
        bb.performance_component + bb.commission_component + bb.retention_component + bb.spot_component, 2
    )
    return bb


def calculate_bonus_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized-ish wrapper: run calculate_bonus for every row and
    return a DataFrame of the four components + total, keyed by employee_id."""
    records = []
    for _, row in df.iterrows():
        bb = calculate_bonus(row)
        records.append({
            "employee_id": bb.employee_id,
            "performance_bonus": bb.performance_component,
            "sales_commission": bb.commission_component,
            "retention_bonus": bb.retention_component,
            "spot_bonus": bb.spot_component,
            "total_bonus": bb.total_bonus,
        })
    return pd.DataFrame(records)


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    df = pd.read_csv(here / "hr_bonus_dataset.csv")
    bonus_df = calculate_bonus_dataframe(df)
    merged = df.merge(bonus_df, on="employee_id")
    out_path = here / "hr_bonus_dataset_with_bonus.csv"
    merged.to_csv(out_path, index=False)
    print(f"Computed bonuses for {len(merged)} employees -> {out_path}")
    print(merged[["employee_id", "department", "performance_bonus", "sales_commission",
                   "retention_bonus", "spot_bonus", "total_bonus"]].head(5).to_string())

    # sanity check: print one full explanation
    sample = df[df["commission_eligible"] == True].iloc[0]
    bb = calculate_bonus(sample)
    print("\n--- Sample explanation ---")
    print(bb.as_plain_english(sample["first_name"], sample["currency"]))
