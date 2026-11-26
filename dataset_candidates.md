# Dataset candidates: harder edge cases

20 proposed examples, weighted toward the boundaries that actually discriminate between configs. **Proposed labels are mine.** Review them, override anything you disagree with, and mark anything you would drop.

## Label rules to adopt first

- **flake** = there is evidence a retry passed. No retry evidence means it is `test`, even if the test name or message says "flaky".
- **compile** includes lint and type-check failures.
- **infra** = the environment or runner failed, not the code.
- **timeout** = an explicit time limit was exceeded.
- **test** = the code ran and an assertion or test body failed.

## Candidates

| # | Log line | Proposed | Why it is hard |
|---|---|:-:|---|
| 1 | `Test passed on retry: test_checkout_flow` | flake | Clean retry-pass evidence |
| 2 | `test_upload failed, passed on rerun after cache clear` | flake | Retry passed, but the fix implies an environment issue |
| 3 | `Test failed: expected 1 got 2; failed consistently across 3 retries` | test | Retries all failed, so not a flake |
| 4 | `Intermittent connection reset in test_db_connect` | flake | "Intermittent" hints flake, but no retry evidence. You may want `test` per the rule |
| 5 | `Test failed on first attempt only; retries not configured` | test | Tempting to call it flake. Rule says no retry evidence, so test |
| 6 | `Retry 1/3 failed, retry 2/3 passed: test_rate_limit` | flake | Explicit retry-pass |
| 7 | `Assertion failed: 5 != 6. Passes locally, fails in CI` | test | Environment-dependent, but the assertion itself failed |
| 8 | `Different test fails on each run; no test fails twice` | flake | Pattern implies flake without a single retry-pass |
| 9 | `Timeout waiting for port 5432 to accept connections` | infra | Timeout wording, infra cause. Genuine tie |
| 10 | `Step exceeded the 3600s limit` | timeout | Straightforward |
| 11 | `Health check timed out; pod never became ready` | infra | Timeout wording again, environment cause |
| 12 | `TS2345: Argument of type 'string' is not assignable to 'number'` | compile | Straightforward type error |
| 13 | `Module not found: Can't resolve './utils'` | compile | Resolution failure, not a test body |
| 14 | `Lint error: 'x' is defined but never used` | compile | Only correct if the rule says lint is compile |
| 15 | `Type error in checkout.test.ts: Property 'foo' does not exist` | compile | "test" in the filename invites `test` |
| 16 | `Registry returned 429; retry after 60s` | infra | Could be argued as flake. It is an external service limit |
| 17 | `Disk quota exceeded while writing build cache` | infra | Straightforward |
| 18 | `Failed to pull image: manifest unknown` | infra | Straightforward |
| 19 | `flaky_test_runner.py exited with code 1` | test | **Trap:** the word "flaky" is in a filename, not evidence |
| 20 | `TimeoutException thrown during test_timeout_handling` | test | **Trap:** the test is about timeouts and the test itself failed |

## Deliberately ambiguous: decide and document

- **#4, #8:** pattern-level flakiness without a retry-pass. Either extend the rule or relabel as `test`.
- **#9, #11:** timeout wording with an infrastructure cause. Decide whether cause or symptom wins.
- **#16:** external rate limit. Decide whether that is infra or flake.

Write the answers into the README so the labels are reproducible.

## What to send back

Reply with changes only, for example: `4 → test`, `14 → drop`, `16 → flake`. Anything you do not mention stays as proposed. Then the JSONL gets regenerated and the run repeats.
