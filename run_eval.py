#!/usr/bin/env python3
"""Minimal LLM eval harness: score two prompt configurations on a labeled dataset.

Usage:
    python run_eval.py --configs a,b --model openai/gpt-4o-mini
    python run_eval.py --configs a,b --fake        # no API calls, for tests/CI

Outputs predictions.jsonl and results.md.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

DEFAULT_LABELS = ["compile", "test", "flake", "infra", "timeout"]
API_URL = "https://openrouter.ai/api/v1/chat/completions"

CONFIGS = {
    "a": {
        "system": "You classify CI log lines.",
        "user": (
            "Classify this CI failure into exactly one category: "
            "compile, test, flake, infra, timeout.\n"
            "Answer with the category only.\n\n"
            "Log line: {input}"
        ),
    },
    "b": {
        "system": (
            "You classify CI log lines. Reply with exactly one lowercase word "
            "from the allowed set and nothing else."
        ),
        "user": (
            "Allowed categories: compile, test, flake, infra, timeout.\n\n"
            "Example 1\nLog: error TS2304: Cannot find name 'userId'\nCategory: compile\n\n"
            "Example 2\nLog: Job exceeded the 60 minute timeout and was cancelled\nCategory: timeout\n\n"
            "Now classify this line.\nLog: {input}\nCategory:"
        ),
    },
}

# Approximate USD per 1M tokens. State the numbers you use in the README.
PRICING = {"input_per_mt": 0.15, "output_per_mt": 0.60}


def load_dataset(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            for key in ("id", "input", "expected"):
                if key not in row:
                    raise ValueError(f"{path}:{lineno}: missing key {key!r}")
            rows.append(row)
    if not rows:
        raise ValueError(f"{path}: dataset is empty")
    return rows


def parse_label(raw: str, labels: list[str]) -> str | None:
    """Strict parse: strip whitespace and a trailing period, then match a label."""
    if raw is None:
        return None
    text = raw.strip().lower().rstrip(".")
    return text if text in labels else None


def est_tokens(text: str) -> int:
    """Rough token estimate: 4 characters per token."""
    return max(1, math.ceil(len(text) / 4))


def call_model(model: str, system: str, user: str, timeout: int = 60) -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (use --fake to skip API calls)")
    body = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
    ).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode())
    return payload["choices"][0]["message"]["content"]


def fake_model(system: str, user: str) -> str:
    """Deterministic stand-in so tests and CI never need an API key."""
    return "compile"


def run_config(
    config_name: str,
    rows: list[dict],
    labels: list[str],
    model: str,
    fake: bool,
    limit: int | None = None,
) -> dict:
    cfg = CONFIGS[config_name]
    predictions = []
    latencies = []
    cost = 0.0
    invalid = 0
    correct = 0

    for row in rows[: limit or len(rows)]:
        prompt = cfg["user"].format(input=row["input"])
        start = time.perf_counter()
        if fake:
            raw = fake_model(cfg["system"], prompt)
        else:
            raw = call_model(model, cfg["system"], prompt)
        latencies.append((time.perf_counter() - start) * 1000)

        got = parse_label(raw, labels)
        if got is None:
            invalid += 1
        elif got == row["expected"]:
            correct += 1

        cost += (
            est_tokens(cfg["system"]) + est_tokens(prompt)
        ) / 1_000_000 * PRICING["input_per_mt"] + (
            est_tokens(raw or "")
        ) / 1_000_000 * PRICING["output_per_mt"]

        predictions.append(
            {
                "config": config_name,
                "id": row["id"],
                "input": row["input"],
                "expected": row["expected"],
                "raw": raw,
                "parsed": got,
            }
        )

    total = len(predictions)
    return {
        "config": config_name,
        "total": total,
        "correct": correct,
        "invalid": invalid,
        "accuracy": correct / total if total else 0.0,
        "median_latency_ms": statistics.median(latencies) if latencies else 0.0,
        "est_cost_per_query": cost / total if total else 0.0,
        "predictions": predictions,
    }


def write_results(results: list[dict], predictions: list[dict], out: str) -> None:
    with open("predictions.jsonl", "w", encoding="utf-8") as fh:
        for p in predictions:
            fh.write(json.dumps(p) + "\n")

    lines = [
        "# Results",
        "",
        "| Config | Correct | Total | Accuracy | Invalid | Median latency (ms) | Est. cost/query (USD) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            "| {config} | {correct} | {total} | {acc:.2f} | {invalid} | {lat:.0f} | ${cost:.6f} |".format(
                config=r["config"],
                correct=r["correct"],
                total=r["total"],
                acc=r["accuracy"],
                invalid=r["invalid"],
                lat=r["median_latency_ms"],
                cost=r["est_cost_per_query"],
            )
        )
    lines += [
        "",
        "Sample size is small and the scoring is exact-match only. See the README Scope section.",
    ]
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score prompt configs on a labeled dataset.")
    parser.add_argument("--dataset", default="dataset.jsonl")
    parser.add_argument("--labels", default=",".join(DEFAULT_LABELS))
    parser.add_argument("--configs", default="a,b")
    parser.add_argument("--model", default="openai/gpt-4o-mini")
    parser.add_argument("--out", default="results.md")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--fake", action="store_true", help="no API calls; deterministic stub")
    args = parser.parse_args(argv)

    labels = [s.strip() for s in args.labels.split(",") if s.strip()]
    configs = [s.strip() for s in args.configs.split(",") if s.strip()]
    unknown = [c for c in configs if c not in CONFIGS]
    if unknown:
        parser.error(f"unknown config(s): {', '.join(unknown)}")

    rows = load_dataset(args.dataset)
    bad = [r["id"] for r in rows if r["expected"] not in labels]
    if bad:
        parser.error(f"expected values not in label set: {', '.join(bad)}")

    results = []
    predictions = []
    for name in configs:
        r = run_config(name, rows, labels, args.model, args.fake, args.limit)
        predictions.extend(r.pop("predictions"))
        results.append(r)

    write_results(results, predictions, args.out)

    for r in results:
        print(
            f"config {r['config']}: {r['correct']}/{r['total']} correct "
            f"({r['accuracy']:.0%}), {r['invalid']} invalid, "
            f"{r['median_latency_ms']:.0f} ms median, "
            f"${r['est_cost_per_query']:.6f}/query"
        )
    print(f"wrote {args.out} and predictions.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
