#!/usr/bin/env python3
"""Compile a validated ontology YAML document into the Agent DSL projection.

Usage:
    python tools/compile_ontology_dsl.py examples/saas.yaml
    python tools/compile_ontology_dsl.py examples/saas.yaml --output saas.ontology.ts

The generated file is declarative agent context, not executable TypeScript.
"""

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

from validate_ontology import validate


def _literal(value):
    """Return a deterministic TypeScript literal for YAML scalar/container data."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ": "), default=_json_default)


def _json_default(value):
    """Preserve YAML-native date/time scalars in the TypeScript-shaped output."""
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    raise TypeError(f"cannot render {type(value).__name__} as an Agent DSL literal")


def _property(name, value, indent):
    """Render a TypeScript object property, quoting non-identifiers when needed."""
    key = name if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name) else _literal(name)
    return f"{' ' * indent}{key}: {value}"


def _object(properties, indent=0):
    if not properties:
        return "{}"
    lines = ["{"]
    for index, (name, value) in enumerate(properties):
        suffix = "," if index < len(properties) - 1 else ""
        lines.append(_property(name, value, indent + 2) + suffix)
    lines.append(" " * indent + "}")
    return "\n".join(lines)


def _inline_object(properties):
    """Render small option bags on one line to keep field declarations scannable."""
    rendered = []
    for name, value in properties:
        key = name if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name) else _literal(name)
        rendered.append(f"{key}: {value}")
    return "{ " + ", ".join(rendered) + " }"


def _call(name, *args):
    return f"{name}({', '.join(args)})"


def _options(data, mapping):
    return [(target, _literal(data[source])) for source, target in mapping if source in data]


def _render_attribute(attribute):
    """Render one attribute. The surrounding entity supplies its local name."""
    role = attribute["role"]
    data_type = attribute["data_type"]
    options = _options(
        attribute,
        (
            ("description", "desc"),
            ("synonyms", "aka"),
            ("reference", "ref"),
            ("value_map", "values"),
            ("required", "required"),
            ("format", "format"),
            ("granularity", "grain"),
            ("unit", "unit"),
        ),
    )
    # Defaults are explicit in the specification: dim() means dimension:string.
    type_arg = [] if role == "dimension" and data_type == "string" else [_literal(data_type)]
    if options:
        type_arg.append(_inline_object(options))
    return _call({"dimension": "dim", "time": "time", "measure": "measure"}[role], *type_arg)


def _render_ast(node):
    """Render every validated Formula AST v1 node in canonical Agent DSL notation."""
    if isinstance(node, list):
        return "[" + ", ".join(_render_ast(item) for item in node) + "]"
    if not isinstance(node, dict):
        return _literal(node)

    node_type = node.get("type")
    # Formula AST includes ordinary data objects inside nodes (for example,
    # window.order_by entries and case branches). Only objects with a `type`
    # are AST nodes; the others remain regular object literals.
    if node_type is None:
        return _object([(key, _render_ast(value)) for key, value in node.items()], 0)
    if node_type == "ref":
        function = "attr" if node.get("kind") == "attribute" else "kpiRef"
        return _call(function, _literal(node["id"]))
    if node_type == "value_ref":
        return _call("valueRef", _literal(node["value_map"]), _literal(node["id"]))
    if node_type == "const":
        if "data_type" in node:
            return _call("value", _literal(node.get("value")), _literal(node["data_type"]))
        return _literal(node.get("value"))
    if node_type == "param":
        return _call("param", _literal(node["name"]))
    if node_type == "base_metric_ref":
        return _call("baseMetric", _literal(node["default"]))
    if node_type == "period_ref":
        return _call("period", _literal(node["default"]))
    if node_type in {"add", "sub", "mul", "mod"}:
        return _call(node_type, _render_ast(node["left"]), _render_ast(node["right"]))
    if node_type == "power":
        return _call("power", _render_ast(node["base"]), _render_ast(node["exponent"]))
    if node_type in {"neg", "abs", "floor", "ceil", "lower", "upper", "trim", "length", "is_null", "is_not_null", "not"}:
        names = {"is_null": "isNull", "is_not_null": "isNotNull"}
        return _call(names.get(node_type, node_type), _render_ast(node["arg"]))
    if node_type == "round":
        return _call("round", _render_ast(node["arg"]), _render_ast(node["precision"]))
    if node_type == "agg":
        args = [_literal(node["function"]), _literal(node["scope_entity"]), _render_ast(node["arg"])]
        if "distinct" in node:
            args.append(_inline_object([("distinct", _literal(node["distinct"]))]))
        return _call("agg", *args)
    if node_type == "safe_div":
        args = [_render_ast(node["numerator"]), _render_ast(node["denominator"])]
        if "on_zero" in node:
            args.append(_inline_object([("onZero", _literal(node["on_zero"]))]))
        return _call("safeDiv", *args)
    if node_type in {"least", "greatest"}:
        return _call(node_type, *(_render_ast(item) for item in node["args"]))
    if node_type == "filter":
        return _call("filter", _render_ast(node["input"]), _render_ast(node["where"]))
    if node_type in {"and", "or"}:
        return _call(node_type, *(_render_ast(item) for item in node["args"]))
    if node_type in {"eq", "ne", "gt", "gte", "lt", "lte"}:
        return _call(node_type, _render_ast(node["left"]), _render_ast(node["right"]))
    if node_type in {"in", "not_in"}:
        name = "inSet" if node_type == "in" else "notIn"
        return _call(name, _render_ast(node["input"]), *(_render_ast(item) for item in node["values"]))
    if node_type == "between":
        return _call("between", _render_ast(node["input"]), _render_ast(node["low"]), _render_ast(node["high"]))
    if node_type == "like":
        args = [_render_ast(node["input"]), _render_ast(node["pattern"])]
        if "case_sensitive" in node:
            args.append(_inline_object([("caseSensitive", _literal(node["case_sensitive"]))]))
        return _call("like", *args)
    if node_type == "case":
        branches = []
        for branch in node["branches"]:
            branches.append(_inline_object([("when", _render_ast(branch["when"])), ("then", _render_ast(branch["then"]))]))
        return _call("caseWhen", "[" + ", ".join(branches) + "]", _render_ast(node["else"]))
    if node_type == "coalesce":
        return _call("coalesce", *(_render_ast(item) for item in node["args"]))
    if node_type == "nullif":
        return _call("nullIf", _render_ast(node["left"]), _render_ast(node["right"]))
    if node_type == "concat":
        args = [_render_ast(item) for item in node["args"]]
        if "separator" in node:
            args.append(_inline_object([("separator", _render_ast(node["separator"]))]))
        return _call("concat", *args)
    if node_type == "substring":
        args = [_render_ast(node["input"]), _render_ast(node["start"])]
        if "length" in node:
            args.append(_render_ast(node["length"]))
        return _call("substring", *args)
    if node_type == "cast":
        return _call("cast", _render_ast(node["input"]), _literal(node["to"]))
    if node_type == "date_trunc":
        return _call("dateTrunc", _literal(node["unit"]), _render_ast(node["input"]))
    if node_type == "date_add":
        return _call("dateAdd", _literal(node["unit"]), _render_ast(node["amount"]), _render_ast(node["input"]))
    if node_type == "date_diff":
        return _call("dateDiff", _literal(node["unit"]), _render_ast(node["start"]), _render_ast(node["end"]))
    if node_type == "extract":
        return _call("extract", _literal(node["part"]), _render_ast(node["input"]))
    if node_type == "current_date":
        return _call("currentDate")
    if node_type == "current_timestamp":
        return _call("currentTimestamp")
    if node_type in {"variance", "stddev"}:
        return _call(node_type, _literal(node["population"]), _render_ast(node["input"]))
    if node_type == "covariance":
        return _call("covariance", _literal(node["population"]), _render_ast(node["x"]), _render_ast(node["y"]))
    if node_type == "correlation":
        return _call("correlation", _render_ast(node["x"]), _render_ast(node["y"]))
    if node_type == "percentile":
        return _call("percentile", _render_ast(node["input"]), _literal(node["percentile"]), _literal(node["method"]))
    if node_type == "median":
        return _call("median", _render_ast(node["input"]))
    if node_type == "mode":
        return _call("mode", _render_ast(node["input"]), _literal(node["tie_break"]))
    if node_type == "z_score":
        return _call("zScore", _render_ast(node["input"]), _render_ast(node["mean"]), _render_ast(node["stddev"]), _inline_object([("onZeroStddev", _literal(node["on_zero_stddev"]))]))
    if node_type == "window":
        properties = []
        for key, value in node.items():
            if key not in {"type", "function"}:
                properties.append((_camel_case(key), _render_ast(value)))
        return _call("window", _literal(node["function"]), _object(properties, 0))
    if node_type == "moving_average":
        properties = [("orderBy", _render_ast(node["order_by"]))]
        if "partition_by" in node:
            properties.append(("partitionBy", _render_ast(node["partition_by"])))
        return _call("movingAverage", _render_ast(node["input"]), _literal(node["periods"]), _object(properties, 0))
    if node_type == "run_rate_projection":
        args = [_render_ast(node["observed"]), _render_ast(node["elapsed"]), _render_ast(node["total"])]
        if "on_zero" in node:
            args.append(_inline_object([("onZero", _literal(node["on_zero"]))]))
        return _call("runRateProjection", *args)
    if node_type == "target_progress":
        args = [_render_ast(node["actual"]), _render_ast(node["target"])]
        if "on_zero" in node:
            args.append(_inline_object([("onZero", _literal(node["on_zero"]))]))
        return _call("targetProgress", *args)

    raise ValueError(f"Formula AST node '{node_type}' has no Agent DSL renderer")


def _camel_case(value):
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


def _local_attribute_id(entity_id, attribute_id):
    prefix = entity_id + "."
    return attribute_id[len(prefix):] if attribute_id.startswith(prefix) else attribute_id


def _render_entity(entity):
    entity_id = entity["id"]
    attrs = []
    for attribute in entity["attributes"]:
        attrs.append((_local_attribute_id(entity_id, attribute["id"]), _render_attribute(attribute)))
    properties = [("kind", _literal(entity["entity_type"]))]
    properties.extend(_options(entity, (("description", "desc"), ("synonyms", "aka"))))
    properties.append(("key", _literal([_local_attribute_id(entity_id, item) for item in entity["identity_attributes"]])))
    if "time_attributes" in entity:
        properties.append(("time", _literal([_local_attribute_id(entity_id, item) for item in entity["time_attributes"]])))
    properties.append(("attrs", _object(attrs, 2)))
    return _call("entity", _literal(entity_id), _object(properties, 0))


def _render_kpi(kpi):
    properties = [("unit", _literal(kpi["unit"]))]
    properties.extend(
        _options(kpi, (("description", "desc"), ("synonyms", "aka"), ("influenced_by", "influencedBy"), ("parameters", "parameters")))
    )
    properties.append(("expr", _render_ast(kpi["expr_ast"])))
    return _call("kpi", _literal(kpi["id"]), _object(properties, 0))


def _render_value_map(value_map):
    properties = [("for", _literal(value_map["reference"]))]
    properties.extend(_options(value_map, (("description", "desc"),)))
    properties.append(("values", _literal(value_map["values"])))
    return _call("valueMap", _literal(value_map["id"]), _object(properties, 0))


def compile_dsl(data, source_name=None):
    """Return the deterministic Agent DSL projection for validated YAML data."""
    source = f" Source: {source_name}." if source_name else ""
    lines = [
        "// Generated Agent Ontology DSL. Do not execute as TypeScript.",
        f"// Canonical source remains YAML.{source}",
        "// Conventions: dim() means dimension:string; attribute names are scoped to their entity.",
        "",
        f"ontology({_literal(data['ontology_id'])}, {{ version: {_literal(data['ontology_version'])}, formulaVersion: {_literal(data['formula_schema_version'])} }}, () => {{",
    ]
    sections = (
        ("entities", _render_entity),
        ("kpis", _render_kpi),
        ("relationships", lambda relationship: _call("relates", _literal(relationship["from"]), _literal(relationship["relationship"]), _literal(relationship["to"]), _literal(relationship["cardinality"]))),
        ("value_maps", _render_value_map),
    )
    for section_name, renderer in sections:
        values = data[section_name]
        if not values:
            continue
        lines.append("")
        for item in values:
            rendered = renderer(item).replace("\n", "\n  ")
            lines.append(f"  {rendered};")
    lines.extend(["", "});", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Validate an ontology YAML file and compile its Agent DSL projection"
    )
    parser.add_argument("file", type=Path, help="canonical ontology YAML input")
    parser.add_argument("-o", "--output", type=Path, help="write DSL to this path instead of stdout")
    args = parser.parse_args()

    report, data = validate(args.file)
    if report.errors:
        print(f"INVALID: {args.file} ({len(report.errors)} problem(s)); DSL was not generated", file=sys.stderr)
        for item in report.errors:
            print(f"  ERROR  {item}", file=sys.stderr)
        return 1

    output = compile_dsl(data, args.file.name)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"COMPILED: {args.file} -> {args.output}")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
