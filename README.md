# eval-harness

A minimal harness for scoring LLM prompt configurations on a labeled dataset. It answers one question: **did this change make the output better or worse?**

Built to be small on purpose. No UI, no judge model, no provider abstraction.

## Task

Classify a CI log line into one of five failure categories:

`compile`, `test`, `flake`, `infra`, `timeout`

## Dataset

`dataset.jsonl` has 20 synthetic examples, 4 per category. Inputs are written by hand to be unambiguous; no real logs from any employer are used.

Each row: `{"id": "...", "input": "...", "expected": "..."}`

## Configurations compared

Both use the same model. Only the prompt varies.

- **A — zero-shot:** a one-line instruction with the five allowed labels, asking for the category only.
- **B — few-shot:** the same instruction, plus two worked examples and an explicit "reply with exactly one lowercase word" constraint.

## Results

Model: `openai/gpt-4o-mini`, temperature 0, 2026-11-07.

| Config | Correct | Total | Accuracy | Invalid | Median latency | Est. cost/query |
|---|---|---|---|---|---|---|
| A (zero-shot) | 19 | 20 | 95% | 0 | 716 ms | $0.000009 |
| B (few-shot) | 18 | 20 | 90% | 0 | 662 ms | $0.000016 |

### What the numbers say

1. **Few-shot prompting did not help.** It cost 78% more per query and lost one example. On a task this narrow, the extra examples added tokens without adding signal.
2. **Neither config produced an invalid output.** The strict "one word only" constraint in B was unnecessary; the model followed the format in both cases.
3. **Both failures came from the same example,** and the failure is a labeling problem, not a model problem:

   - `Attempt 1 failed, attempt 2 passed: test_session_refresh`
   - Expected `flake`, both configs said `test`.

   The taxonomy is ambiguous at this boundary. "Flaky" should require evidence of a retry passing; otherwise the line is just a test failure. The eval surfaced a defect in the dataset before it surfaced one in the model. That is the point of running it.

## Scope and limitations

- **n = 20.** Too small to generalize. This is a smoke test, not a benchmark.
- **One model, one run, temperature 0.** No sampling variance, no model comparison.
- **Exact-match scoring only.** No partial credit, no rubric.
- **Synthetic inputs.** Performance on real, messy logs is unknown.
- **Cost is estimated** from characters ÷ 4 as a token proxy, at $0.15 per 1M input tokens and $0.60 per 1M output tokens. It is an order-of-magnitude figure, not a bill.

## Reproduce

```bash
# no API calls, deterministic stub (what CI runs)
python run_eval.py --fake --configs a,b

# real run
export OPENROUTER_API_KEY=...
python run_eval.py --configs a,b --model openai/gpt-4o-mini
```

Outputs `results.md` and `predictions.jsonl`.

## Reusing it for a different task

```bash
python run_eval.py --dataset other.jsonl --labels yes,no --configs a,b
```

The runner is task-agnostic; only the prompts in `CONFIGS` are task-specific.

## Files

| File | Purpose |
|---|---|
| `run_eval.py` | Loader, model client, strict scorer, metrics, report writer |
| `dataset.jsonl` | 20 labeled examples |
| `tests/test_run_eval.py` | 10 unit tests: parsing, dataset validation, scoring, output |
| `results.md` | Generated results table |
| `predictions.jsonl` | Per-example outputs, for inspection |

## Next

- Disambiguate the `flake` label (require retry-pass evidence) and re-run.
- Reuse the scorer for a second task with a genuinely ambiguous boundary.
