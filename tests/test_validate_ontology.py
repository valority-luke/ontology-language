import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_ontology.py"
COMPILER = ROOT / "tools" / "compile_ontology_dsl.py"
sys.path.insert(0, str(ROOT / "tools"))
from compile_ontology_dsl import _render_ast  # noqa: E402
from validate_ontology import AST_NODE_TYPES  # noqa: E402


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

    def test_compiler_emits_compact_agent_dsl_for_valid_yaml(self):
        result = subprocess.run(
            [sys.executable, str(COMPILER), str(ROOT / "examples" / "saas.yaml")],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('ontology("saas", { version: "0.1", formulaVersion: "1" }, () => {', result.stdout)
        self.assertIn('account_id: dim()', result.stdout)
        self.assertIn('monthly_recurring_revenue: measure("decimal", {', result.stdout)
        self.assertIn('expr: agg("sum", "subscription", attr("subscription.monthly_recurring_revenue"))', result.stdout)
        self.assertIn('expr: safeDiv(agg("sum", "payment", attr("payment.amount")), kpiRef("invoiced_amount"), {', result.stdout)
        self.assertIn('relates("payment", "settles", "invoice", "n:1")', result.stdout)

    def test_compiler_does_not_emit_dsl_for_invalid_yaml(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "invalid.ontology.ts"
            result = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(ROOT / "tests" / "fixtures" / "bad_reference.yaml"),
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("DSL was not generated", result.stderr)
            self.assertFalse(output.exists())

    def test_compiler_preserves_formula_ast_metadata_objects(self):
        source = """\
ontology_id: test
ontology_version: "0.1"
formula_schema_version: "1"
entities:
  - id: order
    entity_type: event
    identity_attributes: [order.order_id]
    attributes:
      - {id: order.order_id, role: dimension, data_type: string}
      - {id: order.amount, role: measure, data_type: decimal, unit: currency}
kpis:
  - id: ranked_amount
    unit: currency
    expr_ast:
      type: window
      function: rank
      order_by:
        - input: {type: ref, kind: attribute, id: order.amount}
          direction: desc
          nulls: last
relationships: []
value_maps: []
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "window.yaml"
            path.write_text(source, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(COMPILER), str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('expr: window("rank", {', result.stdout)
        self.assertIn('orderBy: [{', result.stdout)
        self.assertIn('input: attr("order.amount")', result.stdout)
        self.assertNotIn('ast(null', result.stdout)

    def test_validator_and_compiler_support_least_and_greatest(self):
        source = """\
ontology_id: test
ontology_version: "0.1"
formula_schema_version: "1"
entities:
  - id: order
    entity_type: event
    identity_attributes: [order.order_id]
    attributes:
      - {id: order.order_id, role: dimension, data_type: string}
      - {id: order.amount, role: measure, data_type: decimal, unit: currency}
kpis:
  - id: clamped_amount
    unit: currency
    expr_ast:
      type: greatest
      args:
        - {type: ref, kind: attribute, id: order.amount}
        - {type: const, value: 0, data_type: decimal}
  - id: capped_amount
    unit: currency
    expr_ast:
      type: least
      args:
        - {type: ref, kind: kpi, id: clamped_amount}
        - {type: const, value: 1000, data_type: decimal}
relationships: []
value_maps: []
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "least-greatest.yaml"
            path.write_text(source, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(COMPILER), str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('greatest(attr("order.amount"), value(0, "decimal"))', result.stdout)
        self.assertIn('least(kpiRef("clamped_amount"), value(1000, "decimal"))', result.stdout)

    def test_validator_rejects_missing_and_unknown_formula_node_fields(self):
        source = """\
ontology_id: test
ontology_version: "0.1"
formula_schema_version: "1"
entities: []
kpis:
  - id: broken_ratio
    unit: ratio
    expr_ast:
      type: safe_div
      numerator: {type: const, value: 1}
      unexpected: true
relationships: []
value_maps: []
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-ast.yaml"
            path.write_text(source, encoding="utf-8")
            result = self.run_validator(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("denominator: is required", result.stdout)
        self.assertIn("unexpected: is not defined by schema 0.1", result.stdout)

    def test_validator_rejects_cyclic_kpi_references(self):
        source = """\
ontology_id: test
ontology_version: "0.1"
formula_schema_version: "1"
entities: []
kpis:
  - id: first
    unit: count
    expr_ast: {type: ref, kind: kpi, id: second}
  - id: second
    unit: count
    expr_ast: {type: ref, kind: kpi, id: first}
relationships: []
value_maps: []
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cyclic-kpis.yaml"
            path.write_text(source, encoding="utf-8")
            result = self.run_validator(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("KPI reference cycle: first -> second -> first", result.stdout)

    def test_compiler_has_a_renderer_for_every_formula_ast_v1_node(self):
        const = {"type": "const", "value": 1}
        attr = {"type": "ref", "kind": "attribute", "id": "order.amount"}
        predicate = {"type": "eq", "left": const, "right": const}
        order_by = {"input": attr, "direction": "asc", "nulls": "last"}
        nodes = {
            "ref": attr,
            "value_ref": {"type": "value_ref", "value_map": "value_map.status", "id": "open"},
            "const": const,
            "param": {"type": "param", "name": "threshold"},
            "base_metric_ref": {"type": "base_metric_ref", "default": "revenue"},
            "period_ref": {"type": "period_ref", "default": "monthly"},
            **{kind: {"type": kind, "left": const, "right": const} for kind in ("add", "sub", "mul", "mod", "eq", "ne", "gt", "gte", "lt", "lte")},
            "power": {"type": "power", "base": const, "exponent": const},
            **{kind: {"type": kind, "arg": const} for kind in ("neg", "abs", "floor", "ceil", "not", "is_null", "is_not_null", "lower", "upper", "trim", "length")},
            "round": {"type": "round", "arg": const, "precision": const},
            "safe_div": {"type": "safe_div", "numerator": const, "denominator": const, "on_zero": None},
            **{kind: {"type": kind, "args": [const, const]} for kind in ("least", "greatest", "and", "or", "coalesce")},
            "agg": {"type": "agg", "function": "sum", "scope_entity": "order", "arg": attr},
            "filter": {"type": "filter", "input": const, "where": predicate},
            "in": {"type": "in", "input": const, "values": [const]},
            "not_in": {"type": "not_in", "input": const, "values": [const]},
            "between": {"type": "between", "input": const, "low": const, "high": const},
            "like": {"type": "like", "input": const, "pattern": const, "case_sensitive": True},
            "case": {"type": "case", "branches": [{"when": predicate, "then": const}], "else": const},
            "nullif": {"type": "nullif", "left": const, "right": const},
            "concat": {"type": "concat", "args": [const], "separator": const},
            "substring": {"type": "substring", "input": const, "start": const, "length": const},
            "cast": {"type": "cast", "input": const, "to": "string"},
            "date_trunc": {"type": "date_trunc", "unit": "day", "input": const},
            "date_add": {"type": "date_add", "unit": "day", "amount": const, "input": const},
            "date_diff": {"type": "date_diff", "unit": "day", "start": const, "end": const},
            "extract": {"type": "extract", "part": "day", "input": const},
            "current_date": {"type": "current_date"},
            "current_timestamp": {"type": "current_timestamp"},
            "variance": {"type": "variance", "population": "sample", "input": const},
            "stddev": {"type": "stddev", "population": "sample", "input": const},
            "covariance": {"type": "covariance", "population": "sample", "x": const, "y": const},
            "correlation": {"type": "correlation", "x": const, "y": const},
            "percentile": {"type": "percentile", "input": const, "percentile": 0.5, "method": "continuous"},
            "median": {"type": "median", "input": const},
            "mode": {"type": "mode", "input": const, "tie_break": "min"},
            "z_score": {"type": "z_score", "input": const, "mean": const, "stddev": const, "on_zero_stddev": None},
            "window": {"type": "window", "function": "rank", "order_by": [order_by]},
            "moving_average": {"type": "moving_average", "input": const, "periods": 3, "order_by": order_by},
            "run_rate_projection": {"type": "run_rate_projection", "observed": const, "elapsed": const, "total": const},
            "target_progress": {"type": "target_progress", "actual": const, "target": const},
        }
        self.assertEqual(set(nodes), AST_NODE_TYPES)
        for node_type, node in nodes.items():
            with self.subTest(node_type=node_type):
                self.assertIsInstance(_render_ast(node), str)


if __name__ == "__main__":
    unittest.main()
