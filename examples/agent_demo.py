"""A toy front-office assistant, recorded with two lines of agentdryrun. Everything here is invented; there is no model, no
network and no real customer: the "agent" replays a fixed list of calls, the way a real one would make them.

    python examples/agent_demo.py                      # writes agent-events.jsonl
    python -m agentdryrun shadow --rules examples/rules-front-office.json --events agent-events.jsonl --out report.html

The point: your own agent only needs `@rec.tool("name")` on each function it can call. Compare examples/rules-front-office.json.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from agentdryrun.record import Recorder  # noqa: E402

RULES = os.path.join(HERE, "rules-front-office.json")


def build(out_path):
    clock_state = {"t": 1_791_190_800.0}               # 2026-10-05 09:00 UTC; each call a little later, so windows behave like a real week

    def clock():
        clock_state["t"] += 3 * 3600 + 17 * 60
        return clock_state["t"]

    rec = Recorder(out_path, rules=RULES, clock=clock)  # `rules=` keeps ONLY the fields the rules look at: names never reach the file

    @rec.tool("appointments.book")
    def book_appointment(customer, date, service):
        return {"ok": True}

    @rec.tool("appointments.reschedule")
    def reschedule_appointment(customer, new_date):
        return {"ok": True}

    @rec.tool("appointments.cancel")
    def cancel_appointment(customer, hours_before):
        return {"ok": True}

    @rec.tool("customers.add")
    def add_customer(name, phone):
        return {"ok": True}

    @rec.tool("customers.note")
    def add_note(customer, text):
        return {"ok": True}

    @rec.tool("invoices.create")
    def create_invoice(customer, amount_eur):
        return {"ok": True}

    @rec.tool("payments.record")
    def record_payment(customer, amount_eur):
        return {"ok": True}

    @rec.tool("refunds.issue")
    def issue_refund(customer, amount_eur):
        return {"ok": True}

    @rec.tool("messages.send")
    def send_message(channel, recipients, body):
        return {"ok": True}

    @rec.tool("winback.send")
    def send_winback(recipients):
        return {"ok": True}

    @rec.tool("calendar.share")                          # a tool the rules file does not cover: the report will say so
    def share_calendar(with_whom):
        return {"ok": True}

    return {f.__name__: f for f in (book_appointment, reschedule_appointment, cancel_appointment, add_customer, add_note,
                                    create_invoice, record_payment, issue_refund, send_message, send_winback, share_calendar)}


def replay(tools):
    t = tools
    plan = []
    for i in range(14):
        plan.append((t["book_appointment"], dict(customer=f"C-{100 + i}", date=f"2026-10-{6 + i % 9:02d}", service="consultation")))
    for hrs in (30, 26, 5, 1):
        plan.append((t["cancel_appointment"], dict(customer="C-104", hours_before=hrs)))
    for i in range(3):
        plan.append((t["reschedule_appointment"], dict(customer=f"C-{110 + i}", new_date="2026-10-20")))
    for i in range(3):
        plan.append((t["add_customer"], dict(name=f"Customer {i}", phone="(invented)")))
    plan.append((t["add_note"], dict(customer="C-101", text="prefers morning slots")))
    for amount in (60, 80, 120, 450, 650, 5200):
        plan.append((t["create_invoice"], dict(customer="C-105", amount_eur=amount)))
    for amount in (60, 80, 120, 450, 1500):
        plan.append((t["record_payment"], dict(customer="C-105", amount_eur=amount)))
    for amount in (80, 250, 1200):
        plan.append((t["issue_refund"], dict(customer="C-106", amount_eur=amount)))
    for n in (1, 1, 1, 1, 1, 40):
        plan.append((t["send_message"], dict(channel="sms", recipients=n, body="(message text, never recorded)")))
    for n in (25, 60, 18):
        plan.append((t["send_winback"], dict(recipients=n)))
    plan.append((t["share_calendar"], dict(with_whom="someone@example.invalid")))
    plan.append((t["share_calendar"], dict(with_whom="other@example.invalid")))
    for fn, kwargs in plan:
        fn(**kwargs)
    return len(plan)


def main(out_path="agent-events.jsonl"):
    if os.path.exists(out_path):
        os.remove(out_path)                              # the demo starts from an empty file; real use appends forever
    n = replay(build(out_path))
    print(f"the toy agent made {n} tool calls; recorded to {out_path} (only the fields the rules look at)")
    print(f"next: python -m agentdryrun shadow --rules examples/rules-front-office.json --events {out_path} --out report.html")
    return n


if __name__ == "__main__":
    main(*sys.argv[1:2])
