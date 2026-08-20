"""
people_ops_agent.py
"People Ops Agent" - a self-serve chat agent employees can talk to
instead of pinging the payroll/comp person directly. Solves three
real jobs-to-be-done:

  1. "How was my bonus calculated?"  -> plain-English breakdown, citing
     the exact policy and numbers (via bonus_engine.py)
  2. "Can I get my payslip?"         -> generates a PDF payslip on demand
     (via payslip_generator.py) for employees who can't reach the HRIS
  3. General people-ops questions     -> answered from a lightweight
     company policy knowledge base (via company_policies.py)

Design note: intent routing (bonus vs payslip vs general question) is
still simple keyword/pattern matching - reliable and free. General Q&A
now calls the Claude API (Messages API) with the full company policy
library passed in as context, so it can handle genuinely open-ended
phrasing instead of only exact keyword matches. If no API key is
configured, it automatically falls back to the old keyword-matching
behaviour, so this file still runs with zero setup if you just want
to see the bonus/payslip parts.
"""

import os
import re
import pandas as pd
from bonus_engine import calculate_bonus
from payslip_generator import generate_payslip_pdf
from company_policies import search_policies, POLICIES

DATA_PATH = "hr_bonus_dataset_with_bonus.csv"

# Full policy library as one text block, handed to Claude as context so it
# only answers from what's actually in the company's policies (not from
# whatever it happens to know about HR in general).
POLICY_CONTEXT = "\n\n".join(f"- {p['id']}: {p['answer']}" for p in POLICIES)

CLAUDE_SYSTEM_PROMPT = f"""You are a People Ops assistant for a company. Answer employee questions
about leave, benefits, payroll, tax, and bonus policy using ONLY the
company policy information below. Be warm, concise, and specific.

If the question isn't covered by this policy library, say so plainly and
suggest the employee contact their People Ops partner - do not guess or
invent a policy that isn't listed here.

COMPANY POLICY LIBRARY:
{POLICY_CONTEXT}
"""


class PeopleOpsAgent:
    def __init__(self, data_path: str = DATA_PATH, use_claude: bool = True):
        self.df = pd.read_csv(data_path)
        self.df["employee_id"] = self.df["employee_id"].astype(str)
        # Only attempt the Claude API path if the caller wants it AND a key
        # is actually configured - otherwise fall back silently so the demo
        # still runs with zero setup.
        self.use_claude = use_claude and bool(os.environ.get("ANTHROPIC_API_KEY"))
        self._claude_client = None
        if self.use_claude:
            try:
                import anthropic
                self._claude_client = anthropic.Anthropic()
            except ImportError:
                print("anthropic package not installed - run `pip install anthropic`. "
                      "Falling back to keyword-based Q&A for now.")
                self.use_claude = False

    def _lookup_employee(self, employee_id: str):
        employee_id = employee_id.strip().upper()
        match = self.df[self.df["employee_id"].str.upper() == employee_id]
        if match.empty:
            return None
        return match.iloc[0]

    def explain_bonus(self, employee_id: str) -> str:
        employee = self._lookup_employee(employee_id)
        if employee is None:
            return f"I couldn't find employee ID '{employee_id}'. Could you double-check it?"
        bb = calculate_bonus(employee)
        return bb.as_plain_english(employee["first_name"], employee["currency"])

    def get_payslip(self, employee_id: str, month_label: str = "Current Period") -> str:
        employee = self._lookup_employee(employee_id)
        if employee is None:
            return f"I couldn't find employee ID '{employee_id}'. Could you double-check it?"
        out_path = f"payslip_{employee['employee_id']}.pdf"
        generate_payslip_pdf(employee, month_label, out_path)
        return (
            f"Done - I've generated a payslip for {employee['first_name']} {employee['last_name']} "
            f"({employee['employee_id']}) for {month_label}: {out_path}"
        )

    def answer_general_question(self, question: str) -> str:
        if self.use_claude:
            try:
                return self._call_claude_api(question)
            except Exception as e:
                # Network/auth/rate-limit errors etc: don't crash the agent,
                # just fall back to keyword search for this one turn.
                print(f"[Claude API call failed, falling back to keyword search: {e}]")

        results = search_policies(question, top_k=1)
        if results:
            return results[0]["answer"]
        return (
            "I don't have a policy on file that directly answers that yet - "
            "I'd recommend checking the HR handbook or looping in your People Ops "
            "partner."
        )

    def _call_claude_api(self, question: str) -> str:
        """Genuinely open-ended Q&A: sends the question plus the full policy
        library as context to Claude, instead of matching keywords. This is
        the upgrade path referenced in the README - same agent loop, smarter
        answers for phrasing the keyword matcher wouldn't catch."""
        msg = self._claude_client.messages.create(
            model="claude-sonnet-5",
            max_tokens=400,
            system=CLAUDE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": question}],
        )
        return msg.content[0].text

    def handle(self, message: str) -> str:
        """Simple intent router: bonus explanation, payslip request, or
        general question. A production agent would use an LLM for intent
        classification too - pattern matching keeps this demo dependency-free."""
        msg = message.lower()

        id_match = re.search(r"\b(emp\d{3,5})\b", msg, re.IGNORECASE)

        if any(kw in msg for kw in ["explain my bonus", "how was my bonus", "bonus calculated", "breakdown of my bonus"]):
            if id_match:
                return self.explain_bonus(id_match.group(1))
            return "Sure - what's your employee ID?"

        if any(kw in msg for kw in ["payslip", "pay slip", "pay stub"]):
            if id_match:
                return self.get_payslip(id_match.group(1))
            return "I can generate that - what's your employee ID?"

        return self.answer_general_question(message)


if __name__ == "__main__":
    agent = PeopleOpsAgent()

    demo_conversation = [
        "Hi, can you explain my bonus? My employee ID is EMP1335",
        "Can I get my payslip? EMP1335",
        "How much annual leave do I get?",
        "Why is my net pay lower than usual this month?",
        "What's the deal with benefits enrollment?",
    ]

    print("=" * 70)
    print("PEOPLE OPS AGENT - DEMO CONVERSATION")
    print(f"(Claude API mode: {'ON' if agent.use_claude else 'OFF (no ANTHROPIC_API_KEY set - using keyword fallback)'})")
    print("=" * 70)
    for turn in demo_conversation:
        print(f"\nEmployee: {turn}")
        print(f"Agent: {agent.handle(turn)}")
