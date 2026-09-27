## AWRP relay rules

1. Read `protocol/WORKER-CONTRACT.md`.
2. Pull relay history without rewriting it.
3. Validate and replay the assigned Task.
4. Execute only a DISPATCH whose recipient id equals your configured worker id.
5. Never execute the same run id twice.
6. ACK before material work: on EXECUTE with all checks passing, ACK immediately — never ask the human to confirm the ACK.
7. Use INPUT_REQUEST instead of inventing missing product, security, or human decisions.
8. HANDOFF with exact verification and artifact references.
9. Never modify or delete old canonical Event files.
10. Never perform public or upstream side effects without a matching scoped Approval.
11. If validation or Git fast-forward fails, stop and report; do not force history.
