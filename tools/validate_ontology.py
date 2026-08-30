#!/usr/bin/env python3
"""Validate an Ontology Language YAML file.

Usage:
    python tools/validate_ontology.py examples/retail.yaml
    python tools/validate_ontology.py examples/retail.yaml --fix
"""

import argparse
import datetime as dt
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
    "least", "greatest",
    "date_trunc", "date_add", "date_diff", "extract", "current_date",
    "current_timestamp", "variance", "stddev", "covariance", "correlation",
    "percentile", "median", "mode", "z_score", "window", "moving_average",
    "run_rate_projection", "target_progress",
}
AGGREGATE_FUNCTIONS = {"sum", "avg", "min", "max", "count", "count_distinct", "bool_and", "bool_or"}
WINDOW_FUNCTIONS = AGGREGATE_FUNCTIONS | {
    "row_number", "rank", "dense_rank", "lag", "lead", "variance", "stddev",
    "median", "percentile", "covariance", "correlation",
}
ZERO_BEHAVIORS = {None, "zero", "error"}
STATISTICAL_POPULATIONS = {"sample", "population"}
PERCENTILE_METHODS = {"continuous", "discrete"}
MODE_TIE_BREAKS = {"min", "max", None}
TIME_PARTS = {"year", "quarter", "month", "week", "day", "day_of_week", "hour"}
PERIOD_DEFAULTS = {"daily", "weekly", "monthly", "quarterly", "annual"}
WINDOW_DIRECTIONS = {"asc", "desc"}
WINDOW_NULLS = {"first", "last"}


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
    kpi_parameters, value_map_values = {}, {}
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
        kpi_parameters[kpi_id] = _validate_parameters(kpi.get("parameters"), label, report)
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
            value_map_values[map_id] = set()
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
                canonical_value = value if isinstance(value, str) else value.get("value") if isinstance(value, dict) else None
                if map_id and isinstance(canonical_value, str):
                    if canonical_value in value_map_values[map_id]:
                        report.error(f"{label}.values[{j}]", f"duplicate canonical value '{canonical_value}'")
                    value_map_values[map_id].add(canonical_value)

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
            _validate_ast(
                kpi["expr_ast"],
                f"kpis[{i}].expr_ast",
                attributes,
                kpi_ids,
                entity_ids,
                value_map_values,
                kpi_parameters.get(kpi.get("id"), set()),
                report,
            )
    _validate_kpi_dependency_cycles(kpis, report)
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


def _validate_parameters(parameters, label, report):
    """Validate KPI parameter declarations and return their resolvable names."""
    if parameters is None:
        return set()
    if not isinstance(parameters, list):
        report.error(f"{label}.parameters", "must be a list when provided")
        return set()
    names = set()
    for index, parameter in enumerate(parameters):
        path = f"{label}.parameters[{index}]"
        if not isinstance(parameter, dict):
            report.error(path, "must be an object")
            continue
        _reject_unknown_fields(parameter, {"name", "data_type", "description", "default", "required"}, path, report)
        name = _required_identifier(parameter, "name", path, report, simple=True)
        if name:
            _unique(names, name, f"{path}.name", "parameter", report)
        if parameter.get("data_type") not in TYPES:
            report.error(f"{path}.data_type", f"is required and must be one of {', '.join(sorted(TYPES))}")
        if "required" in parameter and not isinstance(parameter["required"], bool):
            report.error(f"{path}.required", "must be a boolean")
        if "default" in parameter and not _is_scalar(parameter["default"]):
            report.error(f"{path}.default", "must be a scalar or null")
    return names


def _is_scalar(value):
    return value is None or isinstance(value, (str, int, float, bool, dt.date, dt.datetime, dt.time))


def _validate_kpi_dependency_cycles(kpis, report):
    """Reject direct and indirect KPI formula cycles before a runtime evaluates them."""
    graph = {}
    for kpi in kpis:
        if isinstance(kpi, dict) and isinstance(kpi.get("id"), str):
            graph[kpi["id"]] = _kpi_dependencies(kpi.get("expr_ast"))

    visited, active, stack = set(), set(), []

    def visit(kpi_id):
        if kpi_id in active:
            start = stack.index(kpi_id)
            cycle = stack[start:] + [kpi_id]
            report.error(f"kpi '{kpi_id}'.expr_ast", f"KPI reference cycle: {' -> '.join(cycle)}")
            return
        if kpi_id in visited:
            return
        visited.add(kpi_id)
        active.add(kpi_id)
        stack.append(kpi_id)
        for target in graph.get(kpi_id, set()):
            if target in graph:
                visit(target)
        stack.pop()
        active.remove(kpi_id)

    for kpi_id in graph:
        visit(kpi_id)


def _kpi_dependencies(node):
    if isinstance(node, list):
        return set().union(*(_kpi_dependencies(item) for item in node)) if node else set()
    if not isinstance(node, dict):
        return set()
    dependencies = set()
    if node.get("type") == "ref" and node.get("kind") == "kpi" and isinstance(node.get("id"), str):
        dependencies.add(node["id"])
    if node.get("type") == "base_metric_ref" and isinstance(node.get("default"), str):
        dependencies.add(node["default"])
    for value in node.values():
        dependencies.update(_kpi_dependencies(value))
    return dependencies


def _validate_ast(node, path, attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report):
    """Validate the complete Formula AST v1 structural contract."""
    if not isinstance(node, dict):
        report.error(path, "must be a Formula AST object")
        return
    node_type = node.get("type")
    if node_type not in AST_NODE_TYPES:
        report.error(f"{path}.type", f"unknown Formula AST node type '{node_type}'")
        return

    def fields(required, optional=()):
        _ast_fields(node, path, required, optional, report)

    def expr(key, required=True):
        _ast_expression(node, key, path, required, attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)

    def expressions(key, minimum=1):
        _ast_expressions(node, key, path, minimum, attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)

    if node_type == "ref":
        fields({"type", "kind", "id"})
        target = attributes if node.get("kind") == "attribute" else kpi_ids if node.get("kind") == "kpi" else None
        if target is None:
            report.error(f"{path}.kind", "must be attribute or kpi")
        elif node.get("id") not in target:
            report.error(f"{path}.id", f"does not resolve to an existing {node.get('kind')}")
        return
    if node_type == "value_ref":
        fields({"type", "value_map", "id"})
        values = value_map_values.get(node.get("value_map"))
        if values is None:
            report.error(f"{path}.value_map", "must resolve to an existing value map")
        elif node.get("id") not in values:
            report.error(f"{path}.id", "must resolve to a canonical value in the value map")
        return
    if node_type == "const":
        fields({"type", "value"}, {"data_type"})
        if not _is_scalar(node.get("value")):
            report.error(f"{path}.value", "must be a scalar or null")
        if "data_type" in node and node["data_type"] not in TYPES:
            report.error(f"{path}.data_type", f"must be one of {', '.join(sorted(TYPES))}")
        return
    if node_type == "param":
        fields({"type", "name"})
        if node.get("name") not in parameter_names:
            report.error(f"{path}.name", "must resolve to a parameter declared by this KPI")
        return
    if node_type == "base_metric_ref":
        fields({"type", "default"})
        if node.get("default") not in kpi_ids:
            report.error(f"{path}.default", "must resolve to an existing KPI")
        return
    if node_type == "period_ref":
        fields({"type", "default"})
        if node.get("default") not in PERIOD_DEFAULTS:
            report.error(f"{path}.default", f"must be one of {', '.join(sorted(PERIOD_DEFAULTS))}")
        return

    if node_type in {"add", "sub", "mul", "mod"}:
        fields({"type", "left", "right"})
        expr("left"); expr("right")
        return
    if node_type == "power":
        fields({"type", "base", "exponent"})
        expr("base"); expr("exponent")
        return
    if node_type in {"neg", "abs", "floor", "ceil"}:
        fields({"type", "arg"})
        expr("arg")
        return
    if node_type == "round":
        fields({"type", "arg", "precision"})
        expr("arg"); expr("precision")
        return
    if node_type == "safe_div":
        fields({"type", "numerator", "denominator"}, {"on_zero"})
        expr("numerator"); expr("denominator")
        if "on_zero" in node and node["on_zero"] not in ZERO_BEHAVIORS:
            report.error(f"{path}.on_zero", "must be null, zero, or error")
        return
    if node_type in {"least", "greatest"}:
        fields({"type", "args"})
        expressions("args", minimum=1)
        return
    if node_type == "agg":
        fields({"type", "function", "scope_entity", "arg"}, {"distinct"})
        if node.get("function") not in AGGREGATE_FUNCTIONS:
            report.error(f"{path}.function", f"must be one of {', '.join(sorted(AGGREGATE_FUNCTIONS))}")
        if node.get("scope_entity") not in entity_ids:
            report.error(f"{path}.scope_entity", "must resolve to an existing entity")
        if "distinct" in node and not isinstance(node["distinct"], bool):
            report.error(f"{path}.distinct", "must be a boolean")
        expr("arg")
        return
    if node_type == "filter":
        fields({"type", "input", "where"})
        expr("input"); expr("where")
        return

    if node_type in {"and", "or"}:
        fields({"type", "args"})
        expressions("args", minimum=1)
        return
    if node_type == "not":
        fields({"type", "arg"})
        expr("arg")
        return
    if node_type in {"eq", "ne", "gt", "gte", "lt", "lte"}:
        fields({"type", "left", "right"})
        expr("left"); expr("right")
        return
    if node_type in {"in", "not_in"}:
        fields({"type", "input", "values"})
        expr("input"); expressions("values", minimum=1)
        return
    if node_type in {"is_null", "is_not_null"}:
        fields({"type", "arg"})
        expr("arg")
        return
    if node_type == "between":
        fields({"type", "input", "low", "high"})
        expr("input"); expr("low"); expr("high")
        return
    if node_type == "like":
        fields({"type", "input", "pattern"}, {"case_sensitive"})
        expr("input"); expr("pattern")
        if "case_sensitive" in node and not isinstance(node["case_sensitive"], bool):
            report.error(f"{path}.case_sensitive", "must be a boolean")
        return
    if node_type == "case":
        fields({"type", "branches", "else"})
        branches = node.get("branches")
        if not isinstance(branches, list) or not branches:
            report.error(f"{path}.branches", "must be a non-empty list")
        else:
            for index, branch in enumerate(branches):
                branch_path = f"{path}.branches[{index}]"
                if not isinstance(branch, dict):
                    report.error(branch_path, "must be an object")
                    continue
                _ast_fields(branch, branch_path, {"when", "then"}, (), report)
                _validate_ast(branch.get("when"), f"{branch_path}.when", attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)
                _validate_ast(branch.get("then"), f"{branch_path}.then", attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)
        expr("else")
        return
    if node_type == "coalesce":
        fields({"type", "args"})
        expressions("args", minimum=1)
        return
    if node_type == "nullif":
        fields({"type", "left", "right"})
        expr("left"); expr("right")
        return

    if node_type == "concat":
        fields({"type", "args"}, {"separator"})
        expressions("args", minimum=1); expr("separator", required=False)
        return
    if node_type in {"lower", "upper", "trim", "length"}:
        fields({"type", "arg"})
        expr("arg")
        return
    if node_type == "substring":
        fields({"type", "input", "start"}, {"length"})
        expr("input"); expr("start"); expr("length", required=False)
        return
    if node_type == "cast":
        fields({"type", "input", "to"})
        expr("input")
        if node.get("to") not in TYPES:
            report.error(f"{path}.to", f"must be one of {', '.join(sorted(TYPES))}")
        return

    if node_type == "date_trunc":
        fields({"type", "unit", "input"})
        _validate_granularity(node.get("unit"), f"{path}.unit", report); expr("input")
        return
    if node_type == "date_add":
        fields({"type", "unit", "amount", "input"})
        _validate_granularity(node.get("unit"), f"{path}.unit", report); expr("amount"); expr("input")
        return
    if node_type == "date_diff":
        fields({"type", "unit", "start", "end"})
        _validate_date_diff_unit(node.get("unit"), f"{path}.unit", report); expr("start"); expr("end")
        return
    if node_type == "extract":
        fields({"type", "part", "input"})
        if node.get("part") not in TIME_PARTS:
            report.error(f"{path}.part", f"must be one of {', '.join(sorted(TIME_PARTS))}")
        expr("input")
        return
    if node_type in {"current_date", "current_timestamp"}:
        fields({"type"})
        return

    if node_type in {"variance", "stddev"}:
        fields({"type", "population", "input"})
        _validate_population(node.get("population"), f"{path}.population", report); expr("input")
        return
    if node_type == "covariance":
        fields({"type", "population", "x", "y"})
        _validate_population(node.get("population"), f"{path}.population", report); expr("x"); expr("y")
        return
    if node_type == "correlation":
        fields({"type", "x", "y"})
        expr("x"); expr("y")
        return
    if node_type == "percentile":
        fields({"type", "input", "percentile", "method"})
        expr("input")
        percentile = node.get("percentile")
        if isinstance(percentile, bool) or not isinstance(percentile, (int, float)) or not 0 <= percentile <= 1:
            report.error(f"{path}.percentile", "must be a number from 0 to 1")
        if node.get("method") not in PERCENTILE_METHODS:
            report.error(f"{path}.method", "must be continuous or discrete")
        return
    if node_type == "median":
        fields({"type", "input"})
        expr("input")
        return
    if node_type == "mode":
        fields({"type", "input", "tie_break"})
        expr("input")
        if node.get("tie_break") not in MODE_TIE_BREAKS:
            report.error(f"{path}.tie_break", "must be min, max, or null")
        return
    if node_type == "z_score":
        fields({"type", "input", "mean", "stddev", "on_zero_stddev"})
        expr("input"); expr("mean"); expr("stddev")
        if node.get("on_zero_stddev") not in ZERO_BEHAVIORS:
            report.error(f"{path}.on_zero_stddev", "must be null, zero, or error")
        return
    if node_type == "window":
        _validate_window(node, path, attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)
        return
    if node_type == "moving_average":
        _validate_moving_average(node, path, attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)
        return
    if node_type == "run_rate_projection":
        fields({"type", "observed", "elapsed", "total"}, {"on_zero"})
        expr("observed"); expr("elapsed"); expr("total")
        if "on_zero" in node and node["on_zero"] not in ZERO_BEHAVIORS:
            report.error(f"{path}.on_zero", "must be null, zero, or error")
        return
    if node_type == "target_progress":
        fields({"type", "actual", "target"}, {"on_zero"})
        expr("actual"); expr("target")
        if "on_zero" in node and node["on_zero"] not in ZERO_BEHAVIORS:
            report.error(f"{path}.on_zero", "must be null, zero, or error")


def _ast_fields(node, path, required, optional, report):
    allowed = set(required) | set(optional)
    for field in required:
        if field not in node:
            report.error(f"{path}.{field}", "is required")
    _reject_unknown_fields(node, allowed, path, report)


def _ast_expression(node, key, path, required, attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report):
    if key not in node:
        if required:
            report.error(f"{path}.{key}", "is required")
        return
    _validate_ast(node[key], f"{path}.{key}", attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)


def _ast_expressions(node, key, path, minimum, attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report):
    values = node.get(key)
    if not isinstance(values, list) or len(values) < minimum:
        report.error(f"{path}.{key}", f"must be a list with at least {minimum} expression(s)")
        return
    for index, value in enumerate(values):
        _validate_ast(value, f"{path}.{key}[{index}]", attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)


def _validate_population(value, path, report):
    if value not in STATISTICAL_POPULATIONS:
        report.error(path, "must be sample or population")


def _validate_granularity(value, path, report):
    if value not in GRANULARITIES:
        report.error(path, f"must be one of {', '.join(sorted(GRANULARITIES))}")


def _validate_date_diff_unit(value, path, report):
    allowed = GRANULARITIES - {"minute", "hour"}
    if value not in allowed:
        report.error(path, f"must be one of {', '.join(sorted(allowed))}")


def _validate_window(node, path, attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report):
    _ast_fields(node, path, {"type", "function"}, {"input", "partition_by", "order_by", "frame", "offset", "default"}, report)
    function = node.get("function")
    if function not in WINDOW_FUNCTIONS:
        report.error(f"{path}.function", f"must be one of {', '.join(sorted(WINDOW_FUNCTIONS))}")
    if "input" not in node and function not in {"row_number", "rank", "dense_rank"}:
        report.error(f"{path}.input", f"is required for window function '{function}'")
    if "input" in node:
        _validate_ast(node["input"], f"{path}.input", attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)
    _validate_partition_by(node.get("partition_by"), f"{path}.partition_by", attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)
    _validate_order_by(node.get("order_by"), f"{path}.order_by", attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)
    _validate_frame(node.get("frame"), f"{path}.frame", report)
    if "offset" in node and (isinstance(node["offset"], bool) or not isinstance(node["offset"], int) or node["offset"] < 0):
        report.error(f"{path}.offset", "must be a non-negative integer")
    if ("offset" in node or "default" in node) and function not in {"lag", "lead"}:
        report.error(path, "offset and default are allowed only for lag or lead")
    if "default" in node:
        _validate_ast(node["default"], f"{path}.default", attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)


def _validate_moving_average(node, path, attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report):
    _ast_fields(node, path, {"type", "input", "periods", "order_by"}, {"partition_by"}, report)
    _validate_ast(node.get("input"), f"{path}.input", attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)
    if isinstance(node.get("periods"), bool) or not isinstance(node.get("periods"), int) or node["periods"] < 1:
        report.error(f"{path}.periods", "must be a positive integer")
    order_by = node.get("order_by")
    if not isinstance(order_by, dict):
        report.error(f"{path}.order_by", "must be an order-by object")
    else:
        _validate_order_by([order_by], f"{path}.order_by", attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)
    _validate_partition_by(node.get("partition_by"), f"{path}.partition_by", attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)


def _validate_partition_by(value, path, attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report):
    if value is None:
        return
    if not isinstance(value, list):
        report.error(path, "must be a list of attribute references")
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict) or item.get("type") != "ref" or item.get("kind") != "attribute":
            report.error(item_path, "must be an attribute ref Formula AST node")
        else:
            _validate_ast(item, item_path, attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)


def _validate_order_by(value, path, attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report):
    if value is None:
        return
    if not isinstance(value, list) or not value:
        report.error(path, "must be a non-empty list")
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            report.error(item_path, "must be an object")
            continue
        _ast_fields(item, item_path, {"input", "direction", "nulls"}, (), report)
        _validate_ast(item.get("input"), f"{item_path}.input", attributes, kpi_ids, entity_ids, value_map_values, parameter_names, report)
        if item.get("direction") not in WINDOW_DIRECTIONS:
            report.error(f"{item_path}.direction", "must be asc or desc")
        if item.get("nulls") not in WINDOW_NULLS:
            report.error(f"{item_path}.nulls", "must be first or last")


def _validate_frame(value, path, report):
    if value is None:
        return
    if not isinstance(value, dict):
        report.error(path, "must be an object")
        return
    _ast_fields(value, path, {"kind", "start", "end"}, (), report)
    if value.get("kind") not in {"rows", "range"}:
        report.error(f"{path}.kind", "must be rows or range")
    start, end = value.get("start"), value.get("end")
    if start not in {"unbounded_preceding", "current_row"} and not _non_negative_integer(start):
        report.error(f"{path}.start", "must be unbounded_preceding, current_row, or a non-negative integer")
    if end not in {"current_row", "unbounded_following"} and not _non_negative_integer(end):
        report.error(f"{path}.end", "must be current_row, unbounded_following, or a non-negative integer")


def _non_negative_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


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
