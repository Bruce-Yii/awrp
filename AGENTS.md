# Public AWRP Snapshot Instructions

## Scope

- Read `README.md`, `project.json`, `protocol/AWRP-0.1.md`, and `protocol/WORKER-CONTRACT.md` before substantive changes.
- This repository is a public-safe protocol/reference snapshot. Do not add production relay state.
- Never store credentials, tokens, cookies, private keys, real project/task identifiers, or private user/customer data.
- Do not add `projects/`, `channels/`, `contexts/`, `incidents/`, `tasks/`, or `bridge/requests/` state to this repository.

## Verification

- Run `python -m pytest -q` before completion.
- Run `python -m unittest tests/test_public_snapshot.py -v` after adding or renaming files.
- Treat `tests/test_public_snapshot.py` as the executable public-boundary contract.
- Do not weaken privacy/secret assertions to make a test pass.

## Coordination

This snapshot is a public product artifact, not the private AWRP relay. Local workspace and private Relay state never enter this repository.
