#!/usr/bin/env python3
"""Validate an Ontology Language YAML file.

Usage:
    python tools/validate_ontology.py examples/retail.yaml
    python tools/validate_ontology.py examples/retail.yaml --fix
"""

import argparse
import shutil
import sys
from pathlib import Path

import yaml


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that reports duplicate keys instead of losing one."""


def _unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.YAMLError(f"duplicate key {key!r} (line {key_node.start_mark.line + 1})")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)

TOP_LEVEL_LISTS = ("entities", "kpis", "relationships", "value_maps")
ROLES = {"dimension", "time", "measure"}
TYPES = {"string", "integer", "decimal", "boolean", "date", "datetime"}
UNITS = {"count", "currency", "ratio", "percent", "seconds", "bytes", "unitless"}
ENTITY_TYPES = {"definition", "event", "target"}
GRANULARITIES = {"minute", "hour", "day", "week", "month", "quarter", "year"}
CARDINALITIES = {"1:1", "1:n", "n:1", "n:n"}
AST_NODE_TYPES = {
    "ref", "value_ref", "const", "param", "base_metric_ref", "period_ref",
    "add", "sub", "mul", "safe_div", "mod", "neg", "abs", "round",
    "floor", "ceil", "power", "agg", "filter", "and", "or", "not",
    "eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "is_null",
    "is_not_null", "between", "like", "case", "coalesce", "nullif",
    "concat", "lower", "upper", "trim", "substring", "length", "cast",
    "date_trunc", "date_add", "date_diff", "extract", "current_date",
    "current_timestamp", "variance", "stddev", "covariance", "correlation",
    "percentile", "median", "mode", "z_score", "window", "moving_average",
    "run_rate_projection", "target_progress",
}


class Report:
    def __init__(self):
        self.errors, self.fixes = [], []

    def error(self, path, message):
        self.errors.append(f"{path}: {message}")

    def fixed(self, path, message):
        self.fixes.append(f"{path}: {message}")


def validate(path, fix=False):
    report = Report()
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, yaml.YAMLError) as exc:
        report.error("YAML", str(exc))
        return report, None
    if not isinstance(data, dict):
        report.error("document", "must be a YAML mapping")
        return report, None
    _reject_unknown_fields(
        data,
        {"ontology_id", "ontology_version", "formula_schema_version", *TOP_LEVEL_LISTS},
        "document",
        report,
    )

    # These are unambiguous defaults. Everything else is reported for a person to decide.
    for key in TOP_LEVEL_LISTS:
        if key not in data and fix:
            data[key] = []
            report.fixed(key, "added empty required list")
    for key in ("ontology_id", "formula_schema_version", "ontology_version", *TOP_LEVEL_LISTS):
        if key not in data:
            report.error(key, "is required")
    for key in TOP_LEVEL_LISTS:
        if key in data and not isinstance(data[key], list):
            report.error(key, "must be a list")

    _check_identifier(data.get("ontology_id"), "ontology_id", report, simple=True)
    if not isinstance(data.get("ontology_version"), str):
        report.error("ontology_version", "must be a string")
    if data.get("formula_schema_version") != "1":
        report.error("formula_schema_version", 'must be the string "1"')

    entities = data.get("entities", []) if isinstance(data.get("entities"), list) else []
    kpis = data.get("kpis", []) if isinstance(data.get("kpis"), list) else []
    value_maps = data.get("value_maps", []) if isinstance(data.get("value_maps"), list) else []
    relationships = data.get("relationships", []) if isinstance(data.get("relationships"), list) else []

    entity_ids, attribute_ids, attributes, kpi_ids, value_map_ids = set(), set(), {}, set(), set()
    for i, entity in enumerate(entities):
        label = f"entities[{i}]"
        if not isinstance(entity, dict):
            report.error(label, "must be an object")
            continue
        _reject_unknown_fields(entity, {"id", "entity_type", "description", "synonyms", "identity_attributes", "time_attributes", "attributes"}, label, report)
        entity_id = _required_identifier(entity, "id", label, report, simple=True)
        if entity_id:
            _unique(entity_ids, entity_id, f"{label}.id", "entity", report)
        if entity.get("entity_type") not in ENTITY_TYPES:
            report.error(f"{label}.entity_type", f"must be one of {', '.join(sorted(ENTITY_TYPES))}")
        owned = set()
        attrs = entity.get("attributes")
        if not isinstance(attrs, list):
            report.error(f"{label}.attributes", "is required and must be a list")
            attrs = []
        for j, attr in enumerate(attrs):
            attr_label = f"{label}.attributes[{j}]"
            if not isinstance(attr, dict):
                report.error(attr_label, "must be an object")
                continue
            _reject_unknown_fields(attr, {"id", "role", "data_type", "description", "synonyms", "reference", "value_map", "required", "format", "granularity", "unit"}, attr_label, report)
            attr_id = _required_identifier(attr, "id", attr_label, report)
            if attr_id:
                _unique(attribute_ids, attr_id, f"{attr_label}.id", "attribute", report)
                if entity_id and not attr_id.startswith(entity_id + "."):
                    report.error(f"{attr_label}.id", f"must start with '{entity_id}.'")
                owned.add(attr_id)
                attributes[attr_id] = attr
            if attr.get("role") not in ROLES:
                report.error(f"{attr_label}.role", f"must be one of {', '.join(sorted(ROLES))}")
            if attr.get("data_type") not in TYPES:
                report.error(f"{attr_label}.data_type", f"must be one of {', '.join(sorted(TYPES))}")
            if "unit" in attr and (attr.get("role") != "measure" or attr["unit"] not in UNITS):
                report.error(f"{attr_label}.unit", "is allowed only on a measure and must be a supported unit")
            if "granularity" in attr and (attr.get("role") != "time" or attr["granularity"] not in GRANULARITIES):
                report.error(f"{attr_label}.granularity", "is allowed only on a time attribute and must be supported")
            if attr.get("role") == "time" and attr.get("data_type") == "integer" and "granularity" not in attr:
                report.error(f"{attr_label}.granularity", "is required for an integer time attribute")
        identity = entity.get("identity_attributes")
        if not isinstance(identity, list) or not identity:
            report.error(f"{label}.identity_attributes", "is required and must be a non-empty list")
        else:
            for attr_id in identity:
                if attr_id not in owned:
                    report.error(f"{label}.identity_attributes", f"'{attr_id}' is not an attribute of this entity")
        if "time_attributes" in entity:
            times = entity["time_attributes"]
            if not isinstance(times, list) or not times:
                report.error(f"{label}.time_attributes", "must be a non-empty list when provided")
            else:
                for attr_id in times:
                    if attr_id not in owned or attributes.get(attr_id, {}).get("role") != "time":
                        report.error(f"{label}.time_attributes", f"'{attr_id}' must be an owned time attribute")

    # Resolve references after every attribute has been indexed.
    for attr_id, attr in attributes.items():
        if "reference" in attr:
            target = attributes.get(attr["reference"])
            if attr.get("role") != "dimension" or not target or target.get("role") != "dimension":
                report.error(f"attribute '{attr_id}'.reference", "must resolve to an existing dimension attribute")

    for i, kpi in enumerate(kpis):
        label = f"kpis[{i}]"
        if not isinstance(kpi, dict):
            report.error(label, "must be an object")
            continue
        _reject_unknown_fields(kpi, {"id", "unit", "description", "synonyms", "influenced_by", "parameters", "expr_ast"}, label, report)
        kpi_id = _required_identifier(kpi, "id", label, report, simple=True)
        if kpi_id:
            _unique(kpi_ids, kpi_id, f"{label}.id", "KPI", report)
        if kpi.get("unit") not in UNITS | {"varies"}:
            report.error(f"{label}.unit", "is required and must be a supported unit")
        if not isinstance(kpi.get("expr_ast"), dict) or not kpi["expr_ast"].get("type"):
            report.error(f"{label}.expr_ast", "is required and must be a Formula AST object with a type")

    for i, value_map in enumerate(value_maps):
        label = f"value_maps[{i}]"
        if not isinstance(value_map, dict):
            report.error(label, "must be an object")
            continue
        _reject_unknown_fields(value_map, {"id", "reference", "description", "values"}, label, report)
        map_id = _required_identifier(value_map, "id", label, report)
        if map_id:
            _unique(value_map_ids, map_id, f"{label}.id", "value map", report)
        target = attributes.get(value_map.get("reference"))
        if not target or target.get("role") != "dimension":
            report.error(f"{label}.reference", "must resolve to an existing dimension attribute")
        if not isinstance(value_map.get("values"), list):
            report.error(f"{label}.values", "is required and must be a list")
        else:
            for j, value in enumerate(value_map["values"]):
                if not isinstance(value, (str, dict)):
                    report.error(f"{label}.values[{j}]", "must be a string or value object")
                if isinstance(value, dict):
                    _reject_unknown_fields(value, {"value", "synonyms", "description"}, f"{label}.values[{j}]", report)
                    if not isinstance(value.get("value"), str):
                        report.error(f"{label}.values[{j}].value", "is required and must be a string")

    for attr_id, attr in attributes.items():
        if "value_map" in attr and attr["value_map"] not in value_map_ids:
            report.error(f"attribute '{attr_id}'.value_map", "must resolve to an existing value map")

    for i, relationship in enumerate(relationships):
        label = f"relationships[{i}]"
        if not isinstance(relationship, dict):
            report.error(label, "must be an object")
            continue
        for key in ("from", "relationship", "to", "cardinality"):
            if key not in relationship:
                report.error(f"{label}.{key}", "is required")
        _reject_unknown_fields(relationship, {"from", "relationship", "to", "cardinality"}, label, report)
        _check_identifier(relationship.get("relationship"), f"{label}.relationship", report, simple=True)
        if relationship.get("from") not in entity_ids or relationship.get("to") not in entity_ids:
            report.error(label, "from and to must name existing entities")
        if relationship.get("cardinality") not in CARDINALITIES:
            report.error(f"{label}.cardinality", "must be 1:1, 1:n, n:1, or n:n")

    for i, kpi in enumerate(kpis):
        if isinstance(kpi, dict) and isinstance(kpi.get("expr_ast"), dict):
            _validate_ast(kpi["expr_ast"], f"kpis[{i}].expr_ast", attributes, kpi_ids, entity_ids, report)
    return report, data


def _required_identifier(obj, key, label, report, simple=False):
    if key not in obj:
        report.error(f"{label}.{key}", "is required")
        return None
    value = obj[key]
    _check_identifier(value, f"{label}.{key}", report, simple)
    return value


def _check_identifier(value, path, report, simple=False):
    pattern = r"[a-z][a-z0-9_]*" if simple else r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*"
    import re
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        suffix = "" if simple else " in entity.attribute form"
        report.error(path, f"must be a lowercase identifier{suffix}")


def _reject_unknown_fields(obj, allowed, label, report):
    for key in obj.keys() - allowed:
        report.error(f"{label}.{key}", "is not defined by schema 0.1")


def _validate_ast(node, path, attributes, kpi_ids, entity_ids, report):
    """Check node names and canonical references; detailed type checks stay runtime-specific."""
    if isinstance(node, list):
        for index, item in enumerate(node):
            _validate_ast(item, f"{path}[{index}]", attributes, kpi_ids, entity_ids, report)
        return
    if not isinstance(node, dict):
        return
    node_type = node.get("type")
    if node_type and node_type not in AST_NODE_TYPES:
        report.error(f"{path}.type", f"unknown Formula AST node type '{node_type}'")
    if node_type == "ref":
        target = attributes if node.get("kind") == "attribute" else kpi_ids if node.get("kind") == "kpi" else None
        if target is None:
            report.error(f"{path}.kind", "must be attribute or kpi")
        elif node.get("id") not in target:
            report.error(f"{path}.id", f"does not resolve to an existing {node.get('kind')}")
    if node_type == "agg" and node.get("scope_entity") not in entity_ids:
        report.error(f"{path}.scope_entity", "must resolve to an existing entity")
    for key, value in node.items():
        if key != "type":
            _validate_ast(value, f"{path}.{key}", attributes, kpi_ids, entity_ids, report)


def _unique(seen, value, label, thing, report):
    if value in seen:
        report.error(label, f"duplicate {thing} id '{value}'")
    seen.add(value)


def main():
    parser = argparse.ArgumentParser(description="Validate an Ontology Language YAML file")
    parser.add_argument("file", type=Path)
    parser.add_argument("--fix", action="store_true", help="add missing empty lists and save a .bak copy")
    args = parser.parse_args()
    report, data = validate(args.file, args.fix)
    if args.fix and data is not None and report.fixes:
        backup = args.file.with_suffix(args.file.suffix + ".bak")
        shutil.copy2(args.file, backup)
        args.file.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        print(f"Fixed {len(report.fixes)} item(s); backup saved to {backup}")
        for item in report.fixes:
            print(f"  FIXED  {item}")
    if report.errors:
        print(f"INVALID: {args.file} ({len(report.errors)} problem(s))")
        for item in report.errors:
            print(f"  ERROR  {item}")
        return 1
    print(f"VALID: {args.file}" + (f" ({len(report.fixes)} safe fix(es) applied)" if report.fixes else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
