# AGENTS.md — AWRP workspace adapter (thin)

> This file is a pointer, not a contract. The canonical worker rules live in
> `protocol/WORKER-CONTRACT.md`. If anything here conflicts with the canonical
> contract, the contract wins. First-read entrypoint: `AWRP-BOOTSTRAP.md`.

## Every AWRP task, in order

1. Sync relay history without rewriting it (`git pull --ff-only`; stop on failure).
2. Read `tasks/<task_id>/task.json` and the complete `events/*` history.
3. Validate (`python tools/awrp.py validate --task-dir tasks/<task_id>`) and
   replay (`python tools/awrp.py replay --task-dir tasks/<task_id>`) to derive
   state, phase, waiting-on, Run, recipient, and authority.
4. Execute only a valid matching `DISPATCH`: recipient id equals your worker
   id, the `run_id` never executed before, the Task is non-terminal, and the
   side effect is permitted. Discover through an exact channel, endpoint, lane,
   or Task id; never guess across projects or channels.
5. **ACK the same `run_id` before material work.** On an EXECUTE verdict with
   all checks passing, ACK immediately with the reported expected head and
   begin authorized work — never ask the human to confirm the ACK.
6. **Never execute the same `run_id` side effects twice.** A restart is not
   authorization; a retry or revision needs a new Run.
7. **Persist HANDOFF before declaring success.** A Run is complete only after
   canonical HANDOFF delivery is durable and verified.
8. Obey the action × target authority matrix: relay reads/writes are ordinary;
   source, fork, upstream, or public side effects require scoped approval bound
   to the exact output.
9. Fail closed on integrity or authority ambiguity. Never guess, force-push,
   merge away, rebase away, or repair canonical history to hide a failure.
10. Publish appends optimistically: preflight, compose, then plain push. On a
    race or non-fast-forward result, re-sync, replay, and recompose a new
    append. A bounded worker retry must recompose byte-identical canonical
    content and fail closed.
11. A fresh wake reads `.awrp/binding.json`, runs `resume`, and obeys
    NO_TASK / EXECUTE / AMBIGUOUS / OWNED. One ACK per Run.
12. A first window on a project uses `first-bind` with exact relay, project,
    channel, endpoint, and Task id — never a global scan.
13. Multi-project windows attach and switch focus explicitly. Verify pasted
    lineage with `check-lineage` before acting.
14. Parallel Runs do not share one mutable checkout by default. Acquire a
    task-run-scoped clean view, bind against it, and release it only after
    verified HANDOFF delivery.
15. Coordinators acquire the channel claim before routed writes, then fence
    every write with the claim owner. Plan route-sensitive dispatches and
    publish them through the guarded path.

Full rules: `protocol/WORKER-CONTRACT.md`.
Protocol: `protocol/AWRP-0.1.md`.
