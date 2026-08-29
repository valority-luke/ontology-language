import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_ontology.py"


class ValidateOntologyTests(unittest.TestCase):
    def run_validator(self, path, *args):
        return subprocess.run(
            [sys.executable, str(VALIDATOR), str(path), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_examples_are_valid(self):
        for name in ("retail.yaml", "saas.yaml"):
            result = self.run_validator(ROOT / "examples" / name)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("VALID:", result.stdout)

    def test_reports_a_bad_reference_with_its_location(self):
        result = self.run_validator(ROOT / "tests" / "fixtures" / "bad_reference.yaml")
        self.assertEqual(result.returncode, 1)
        self.assertIn("reference", result.stdout)
        self.assertIn("existing dimension attribute", result.stdout)

    def test_fix_adds_missing_empty_lists_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "ontology.yaml"
            shutil.copy2(ROOT / "tests" / "fixtures" / "missing_lists.yaml", target)
            result = self.run_validator(target, "--fix")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(target.with_suffix(".yaml.bak").exists())
            self.assertIn("value_maps: []", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
