"""
company_policies.py
Synthetic "People Ops knowledge base" — the kind of content a real
company would keep in an HR wiki / handbook. Used by the People Ops
Agent to answer general questions (leave, benefits, payslip access,
how bonus works) without needing a live HR system.

Each entry has: id, topic keywords (for simple retrieval), and the
answer text. This is intentionally a lightweight keyword-retrieval
knowledge base (no vector DB needed for a portfolio demo) — but is
structured so it could be dropped straight into a RAG pipeline later.
"""

POLICIES = [
    {
        "id": "bonus_plan_overview",
        "keywords": ["bonus", "how is my bonus calculated", "bonus plan", "incentive"],
        "answer": (
            "Bonuses are made up of up to four components: a Performance Bonus (everyone, "
            "based on your rating), Sales Commission (commission-eligible roles only, based "
            "on target attainment), a Retention Bonus (if your manager flags you as a "
            "retention priority), and a Spot Bonus (for a specific recognized achievement). "
            "For your exact numbers, ask me to 'explain my bonus' and give me your employee ID."
        ),
    },
    {
        "id": "payslip_access",
        "keywords": ["payslip", "pay slip", "pay stub", "download payslip", "where is my payslip"],
        "answer": (
            "You can normally download your payslip from the HRIS self-service portal under "
            "Pay > Payslips. If you don't have access or the portal is down, I can generate a "
            "copy for you right here — just give me your employee ID and I'll produce a PDF."
        ),
    },
    {
        "id": "leave_policy",
        "keywords": ["annual leave", "vacation", "pto", "time off", "leave policy", "sick leave"],
        "answer": (
            "Employees accrue 20 days of annual leave per year (pro-rated in your first year), "
            "plus 10 paid sick days. Leave requests go through the HRIS leave module and need "
            "manager approval at least 3 working days in advance for planned leave."
        ),
    },
    {
        "id": "benefits_enrollment",
        "keywords": ["benefits", "health insurance", "enrollment", "medical cover", "dependents"],
        "answer": (
            "Benefits enrollment (health insurance, dependents, pension/retirement contributions) "
            "opens once a year during Open Enrollment, and also triggers on qualifying life events "
            "(marriage, new child, relocation). Reach out to People Ops within 30 days of a "
            "qualifying event to update your elections outside the normal window."
        ),
    },
    {
        "id": "salary_review_cycle",
        "keywords": ["salary review", "raise", "pay increase", "promotion", "when is my review"],
        "answer": (
            "Compensation reviews happen once a year, tied to the performance review cycle. "
            "Off-cycle adjustments can happen for promotions, market corrections, or retention "
            "cases, and are approved by your manager plus People Ops."
        ),
    },
    {
        "id": "tax_deductions",
        "keywords": ["tax", "deduction", "net pay", "gross pay", "why is my pay lower"],
        "answer": (
            "Your payslip breaks down gross pay, statutory deductions (tax, pension), and any "
            "benefits contributions to arrive at net pay. If a specific month looks off, the most "
            "common causes are a bonus payment moving you into a higher tax bracket for that period, "
            "a benefits election change, or a one-off adjustment — I can pull your payslip so we can "
            "look at the actual line items together."
        ),
    },
]


def search_policies(query: str, top_k: int = 1):
    """Very simple keyword-overlap retrieval. Returns the best-matching
    policy entries. This is deliberately simple (no embeddings) so the
    demo has zero external dependencies — swap in a vector search or
    the Claude API for a production version."""
    query_lower = query.lower()
    scored = []
    for entry in POLICIES:
        score = sum(1 for kw in entry["keywords"] if kw in query_lower)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:top_k]]
