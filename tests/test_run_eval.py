import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_eval  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class TestParseLabel(unittest.TestCase):
    def test_accepts_exact_label(self):
        self.assertEqual(run_eval.parse_label("compile", run_eval.DEFAULT_LABELS), "compile")

    def test_normalizes_case_and_whitespace(self):
        self.assertEqual(run_eval.parse_label("  TIMEOUT.\n", run_eval.DEFAULT_LABELS), "timeout")

    def test_rejects_sentence(self):
        self.assertIsNone(run_eval.parse_label("This is a test failure.", run_eval.DEFAULT_LABELS))

    def test_rejects_unknown_word(self):
        self.assertIsNone(run_eval.parse_label("compile error", run_eval.DEFAULT_LABELS))

    def test_rejects_none(self):
        self.assertIsNone(run_eval.parse_label(None, run_eval.DEFAULT_LABELS))


class TestDataset(unittest.TestCase):
    def test_shipped_dataset_is_valid(self):
        rows = run_eval.load_dataset(str(ROOT / "dataset.jsonl"))
        self.assertEqual(len(rows), 20)
        for row in rows:
            self.assertIn(row["expected"], run_eval.DEFAULT_LABELS)
            self.assertTrue(row["input"].strip())
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)))

    def test_missing_key_raises(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write(json.dumps({"id": "x", "input": "y"}) + "\n")
            path = fh.name
        with self.assertRaises(ValueError):
            run_eval.load_dataset(path)


class TestScoring(unittest.TestCase):
    def test_fake_run_is_deterministic(self):
        rows = run_eval.load_dataset(str(ROOT / "dataset.jsonl"))
        result = run_eval.run_config("a", rows, run_eval.DEFAULT_LABELS, "m", fake=True)
        self.assertEqual(result["total"], 20)
        self.assertEqual(result["invalid"], 0)
        # The fake model always answers "compile", so only compile examples score.
        self.assertEqual(result["correct"], 4)

    def test_median_latency_is_non_negative(self):
        rows = run_eval.load_dataset(str(ROOT / "dataset.jsonl"))
        result = run_eval.run_config("b", rows, run_eval.DEFAULT_LABELS, "m", fake=True, limit=3)
        self.assertGreaterEqual(result["median_latency_ms"], 0.0)
        self.assertEqual(result["total"], 3)


class TestOutput(unittest.TestCase):
    def test_write_results_creates_both_files(self):
        import os

        rows = run_eval.load_dataset(str(ROOT / "dataset.jsonl"))
        result = run_eval.run_config("a", rows, run_eval.DEFAULT_LABELS, "m", fake=True, limit=2)
        predictions = result.pop("predictions")
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                run_eval.write_results([result], predictions, "results.md")
                text = Path("results.md").read_text(encoding="utf-8")
                self.assertIn("| Config |", text)
                self.assertEqual(len(Path("predictions.jsonl").read_text().strip().splitlines()), 2)
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
