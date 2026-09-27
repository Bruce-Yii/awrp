# 2026-09-27 · First public CI exposed two environment assumptions

## Impact

The first public GitHub Actions run failed with three test failures. The
repository was already public, so the release had a visible red CI state until
the correction was pushed.

## Evidence

Two execution-view tests failed because temporary clones tried to create commits
without a configured Git author. They passed locally only because the developer
machine had a global `user.name` and `user.email`.

The public-volume test passed on Windows but failed on the Linux runner. It
measured working-tree bytes; Windows line-ending expansion inflated the result.
The canonical Git blobs were 989,274 bytes.

## Root cause

1. The execution-view test helper configured identity in its seed repository but
   not in cloned execution views. The tests depended on ambient global Git
   configuration.
2. The volume assertion used platform-dependent working-tree file sizes instead
   of the canonical blobs that GitHub publishes and stores.

## Correction

- The test helper now configures repository-local identity for every acquired
  execution view. Production code was not changed.
- The volume check reads `git cat-file -s :<path>` for each tracked file, so it
  measures the exact staged blob size on every platform.
- `docs/STATE-MACHINES.md` adds useful protocol documentation and brings the
  canonical tree above the intended threshold without filler.

## Verification

The three previously failing tests pass with `GIT_CONFIG_GLOBAL` pointed at a
nonexistent file and system Git config disabled. The complete suite is run under
the same isolated Git configuration before the correction is published.
