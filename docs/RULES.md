# The rules language

Rules are a JSON file that says, for each tool an agent may call, what is allowed, with which limits, and how many people must approve.
The same file is read by the shadow command in this repository and by the gateway. Check yours with:

```bash
python -m agentdryrun rules check my-rules.json
```

A file that cannot be understood is refused **whole**, never partly applied.

## A complete example

```json
{
  "version": 1,
  "default_unknown_tool": "deny",
  "tools": {
    "payments.send": {
      "description": "Pay a supplier invoice",
      "permission": "finance:pay",
      "reversibility": "one_way_recoverable",
      "risk": "high",
      "deny": [
        {"when": {"field": "amount_eur", "op": ">", "value": 10000}, "reason": "Above the ceiling of 10,000 EUR per payment"}
      ],
      "limits": [
        {"field": "amount_eur", "per": "day", "max": 15000, "on_exceed": "deny"}
      ],
      "approvals": {
        "required": 1,
        "extra": [{"when": {"field": "amount_eur", "op": ">", "value": 1000}, "required": 2}]
      }
    },
    "invoices.mark_paid": {
      "permission": "finance:books",
      "reversibility": "two_way",
      "risk": "low"
    }
  }
}
```

## Top level

| Key | Meaning |
|---|---|
| `version` | must be `1` |
| `default_unknown_tool` | what happens to a tool that is not in `tools`: `"deny"` (default) or `"pending"` (a human decides) |
| `tools` | an object: tool name → rules for that tool |

## A tool

| Key | Required | Meaning |
|---|---|---|
| `reversibility` | **yes** | `two_way`, `one_way_recoverable`, `one_way_consequential` or `one_way_terminal`. An irreversible tool can never be `risk: "low"` |
| `risk` | no (default `high`) | `low` runs without a human unless a rule escalates it; `high` always waits for approval |
| `permission` | no | the permission an agent must hold to call this tool. If the key is absent, no permission check is made |
| `deny` | no | a list of `{"when": <condition>, "reason": "..."}`. A match refuses the action |
| `escalate` | no | the same shape. A match sends the action to a human |
| `limits` | no | a list of rolling limits (below) |
| `approvals` | no | how many distinct approvers, and from which groups (below) |
| `description`, `effect_key`, `execution` | no | used by the gateway (documentation, de-duplication, who performs the call). Ignored by the shadow command |

## Conditions

A condition looks at one field of the action's parameters, using dot paths for nested fields (`customer.country`):

```json
{"field": "amount_eur", "op": ">", "value": 1000}
```

Operators: `>`, `>=`, `<`, `<=`, `==`, `!=`, `in`, `not_in` (value is a list), `contains` (case-insensitive text), `exists`, `missing` (no value needed).
Combine with `{"all": [ ... ]}`, `{"any": [ ... ]}`, `{"not": { ... }}` (nesting up to 6 deep).

### Three-valued, and fail-closed

A condition is **true**, **false** or **cannot be evaluated** (the field is missing, or is not a number where a number is needed).
"Cannot be evaluated" is never treated as "fine": a `deny` or `escalate` rule that cannot be evaluated sends the action to a human, and the reason says so.

Numbers are read strictly: plain decimals such as `1200.50` or the text `"1200.50"` are numbers; `"1_000"`, `"NaN"`, non-ASCII digits and `"1 200,50"` are not.
That is deliberate: if the gate and the system behind it read an amount differently, one of them is wrong.

## Limits

```json
{"field": "amount_eur", "per": "day", "max": 15000, "on_exceed": "deny", "scope": "tool"}
```

| Key | Meaning |
|---|---|
| `field` | the numeric parameter to add up |
| `per` | rolling window: `hour`, `day`, `week` (7 days) or `month` (30 days) |
| `max` | the total allowed inside the window, greater than 0 |
| `on_exceed` | `deny` (default) or `escalate` |
| `scope` | `tool` (everyone who calls this tool, default) or `agent` (each agent separately) |

In the shadow command the window is measured on the time you report (`occurred_at`) and counts every event you reported, because it all happened.

## Approvals

```json
"approvals": {"required": 2, "groups": ["finance"], "extra": [{"when": {"field": "amount_eur", "op": ">", "value": 1000}, "required": 3}]}
```

`required` is the number of **distinct** people (1 to 5). `extra` raises it when a condition holds (or cannot be evaluated). `groups` limits who may approve.
The agent is never one of the approvers. Approvals only apply to `risk: "high"` actions and to actions that a rule escalated.

## The order in which a verdict is decided

1. Unknown tool: refused (or sent to a human, per `default_unknown_tool`).
2. The agent lacks the tool's `permission`: refused.
3. `risk: "high"` starts the action on the human path.
4. `deny` rules, in order: a match refuses; "cannot be evaluated" escalates.
5. `escalate` rules: a match (or "cannot be evaluated") escalates.
6. `limits`: over the limit is refused or escalated; a missing or unreadable field escalates.
7. If the action is on the human path: `approvals.required`, raised by any `extra` that holds.
8. Otherwise it is allowed.

In the report these are the three outcomes: *would pass*, *would need approval*, *would be refused*.
