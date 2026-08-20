"""
Synthetic HR / Payroll / Bonus dataset generator
for the "Bonus & Comp Transparency Suite" portfolio project.

Generates a realistic (but fully synthetic) mid-size company workforce
with the fields needed to:
  - run pay equity analysis (gender / role / location / tenure)
  - run comp benchmarking vs "market" bands
  - compute a multi-component bonus (performance + sales commission +
    retention + spot bonus) transparently, per employee
  - drive an attrition-risk-vs-comp analysis
  - power the "Explain My Bonus" / payslip agent

No real company or person data is used anywhere.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker
import random

fake = Faker()
Faker.seed(42)
np.random.seed(42)
random.seed(42)

N = 1200  # employees

DEPARTMENTS = {
    "Sales": {"weight": 0.20, "base_range": (28000, 65000), "commission_eligible": True},
    "Engineering": {"weight": 0.22, "base_range": (35000, 95000), "commission_eligible": False},
    "Customer Support": {"weight": 0.12, "base_range": (22000, 42000), "commission_eligible": False},
    "Operations": {"weight": 0.13, "base_range": (24000, 55000), "commission_eligible": False},
    "Finance": {"weight": 0.08, "base_range": (30000, 70000), "commission_eligible": False},
    "HR & People": {"weight": 0.07, "base_range": (26000, 60000), "commission_eligible": False},
    "Marketing": {"weight": 0.10, "base_range": (27000, 62000), "commission_eligible": False},
    "Product": {"weight": 0.08, "base_range": (38000, 90000), "commission_eligible": False},
}

LEVELS = ["Junior", "Mid", "Senior", "Lead", "Manager", "Director"]
LEVEL_MULT = {"Junior": 1.0, "Mid": 1.25, "Senior": 1.55, "Lead": 1.85, "Manager": 2.2, "Director": 2.9}
LEVEL_WEIGHTS = [0.28, 0.28, 0.20, 0.10, 0.10, 0.04]

LOCATIONS = {
    "Lagos": 1.00, "Abuja": 0.97, "Port Harcourt": 0.93,
    "Remote - UK": 1.65, "Remote - Canada": 1.55, "Remote - US": 1.85,
}
LOCATION_WEIGHTS = [0.34, 0.18, 0.10, 0.14, 0.12, 0.12]

GENDERS = ["Female", "Male", "Non-binary"]
GENDER_WEIGHTS = [0.47, 0.51, 0.02]

CURRENCY = "USD"  # keep single currency for simplicity/comparability

rows = []
for i in range(N):
    emp_id = f"EMP{1000+i}"
    dept = np.random.choice(list(DEPARTMENTS.keys()), p=[d["weight"] for d in DEPARTMENTS.values()])
    dept_info = DEPARTMENTS[dept]
    level = np.random.choice(LEVELS, p=LEVEL_WEIGHTS)
    location = np.random.choice(list(LOCATIONS.keys()), p=LOCATION_WEIGHTS)
    gender = np.random.choice(GENDERS, p=GENDER_WEIGHTS)

    tenure_years = round(np.random.exponential(2.5) + 0.1, 1)
    tenure_years = min(tenure_years, 22.0)

    lo, hi = dept_info["base_range"]
    base_role_salary = np.random.uniform(lo, hi)
    salary = base_role_salary * LEVEL_MULT[level] * LOCATIONS[location]

    # --- a deliberate, modest, "unexplained" gender pay gap for the equity
    # analysis to detect (mirrors what real audits often find: a few % gap
    # not explainable by role/level/tenure) ---
    if gender == "Female":
        salary *= np.random.normal(0.955, 0.02)
    elif gender == "Non-binary":
        salary *= np.random.normal(0.965, 0.02)

    salary = round(max(salary, 18000), -2)  # round to nearest 100

    performance_rating = np.clip(np.random.normal(3.4, 0.7), 1, 5)
    performance_rating = round(performance_rating * 2) / 2  # nearest 0.5

    # engagement / satisfaction survey score (drives attrition-comp link)
    comp_satisfaction = np.clip(np.random.normal(6.5, 1.8) - (0.5 if gender == "Female" else 0), 1, 10)

    # attrition risk: higher if underpaid vs role median (computed after) +
    # low comp satisfaction + low performance recognition mismatch
    sales_target_pct = None
    sales_commission_base = None
    if dept_info["commission_eligible"]:
        sales_target_pct = np.clip(np.random.normal(100, 25), 40, 180)
        sales_commission_base = salary * 0.35  # commission pool sized off base

    is_manager_recommended_retention = np.random.rand() < (0.06 if tenure_years > 3 else 0.02)
    had_spot_bonus_event = np.random.rand() < 0.12  # e.g. shipped a project, saved a client

    hire_date = fake.date_between(start_date=f"-{int(tenure_years*365)+30}d", end_date=f"-{max(int(tenure_years*365)-30,1)}d")

    rows.append({
        "employee_id": emp_id,
        "first_name": fake.first_name(),
        "last_name": fake.last_name(),
        "department": dept,
        "level": level,
        "location": location,
        "gender": gender,
        "hire_date": hire_date,
        "tenure_years": tenure_years,
        "annual_base_salary": salary,
        "currency": CURRENCY,
        "performance_rating": performance_rating,
        "comp_satisfaction_score": round(comp_satisfaction, 1),
        "commission_eligible": dept_info["commission_eligible"],
        "sales_target_attainment_pct": None if sales_target_pct is None else round(sales_target_pct, 1),
        "sales_commission_base": None if sales_commission_base is None else round(sales_commission_base, 2),
        "retention_bonus_flag": is_manager_recommended_retention,
        "spot_bonus_event": had_spot_bonus_event,
    })

df = pd.DataFrame(rows)

# Role median (department + level + location) for pay-equity / benchmarking
# comparisons. Location is included deliberately: salaries here carry a real
# geographic multiplier (Lagos = 1.0x vs. Remote - US = 1.85x, see LOCATIONS
# above), so a median computed only on department+level would compare, say,
# a Lagos engineer against a blended dept/level median that's pulled up by
# US/UK/Canada remote pay - making every Nigeria-based employee look
# "underpaid" and every high-cost-location employee look "overpaid" purely
# from the geo mix, not from any real pay decision. Grouping in the
# geo-banded salary structure this data actually has.
df["role_median_salary"] = df.groupby(["department", "level", "location"])["annual_base_salary"].transform("median")
df["pct_vs_role_median"] = round((df["annual_base_salary"] / df["role_median_salary"] - 1) * 100, 1)

# Synthetic "market benchmark" salary (external survey data stand-in):
# role median * small market premium/discount noise, so it's independent info
market_noise = np.random.normal(1.03, 0.06, size=len(df))
df["market_benchmark_salary"] = round(df["role_median_salary"] * market_noise, -2)
df["pct_vs_market"] = round((df["annual_base_salary"] / df["market_benchmark_salary"] - 1) * 100, 1)

# Attrition risk score (0-100), used for the attrition-comp analysis;
# purely synthetic but internally consistent with comp variables.
# CAVEAT (flagged for technical reviewers): left_company is generated as a
# noisy threshold on a score that is itself a direct linear function of
# pct_vs_market, comp_satisfaction_score, performance_rating and
# tenure_years - the same variables the notebook's logistic regression
# uses as predictors. That means the regression substantially recovers its
# own generating formula, so the coefficients demonstrate the *methodology*
# (how you'd quantify a comp-attrition link) rather than an independently
# discovered real-world effect. A real dataset's attrition wouldn't be this
# clean. See the attrition section of analysis.ipynb for the same note.
risk = (
    (10 - df["comp_satisfaction_score"]) * 6.0
    + np.clip(-df["pct_vs_market"], 0, None) * 1.4
    + np.clip(4 - df["performance_rating"], 0, None) * 3.0
    + np.clip(3 - df["tenure_years"], 0, None) * 1.5
    + np.random.normal(0, 6, size=len(df))
)
df["attrition_risk_score"] = np.clip(round(risk, 1), 0, 100)
df["left_company"] = (df["attrition_risk_score"] > np.random.normal(62, 10, size=len(df))).astype(int)

out_path = Path(__file__).resolve().parent / "hr_bonus_dataset.csv"
df.to_csv(out_path, index=False)
print(f"Saved {len(df)} rows to {out_path}")
print(df.head(3).to_string())
print("\nColumns:", list(df.columns))
