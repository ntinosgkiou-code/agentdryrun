# Security policy

OmniOS is a **prototype**. It has not had an external security review.

## Reporting a vulnerability
Please do not open a public issue for something exploitable. Use GitHub's **private vulnerability reporting** (the *Security* tab of this repository, then *Report a vulnerability*) with:
what you found, how to reproduce it (a failing `bundle.zip` is ideal), and what you think it breaks.

The most valuable reports for this repository:
- a bundle that `verify.py` reports as **VERIFIED** although a record was added, removed, edited or reordered;
- a witness that cosigns a checkpoint that does not extend the one it saw before;
- a way to make the verifier accept a key it was not given;
- any parsing difference between the specification and the reference code that two implementations could disagree on.

## What counts as in scope
`verify.py`, `omnios/tlog.py`, `omnios/witnessd.py`, and the format described in `docs/`.
The commercial gateway is not in this repository.

## What I will do
Acknowledge within a few days, fix, and credit you in the changelog if you want.
