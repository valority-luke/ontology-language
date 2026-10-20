# Agent Ontology DSL 0.1

The Agent Ontology DSL is a deterministic, read-only projection of a valid
Ontology Language YAML document. It reduces repeated schema information before
an AI agent receives ontology context. It is deliberately TypeScript-shaped for
readability, but is **not executable TypeScript**, JavaScript, or a user
authoring format.

The canonical source of truth is the YAML authoring schema 0.1. The compiler
must validate YAML with the canonical validator before generating DSL. A
validation error produces no DSL output.

## 1. Contract and safety

The DSL is generated context only. Consumers must parse it as data or consume
the compiler's in-memory representation; they must never evaluate it with a
JavaScript/TypeScript runtime. The generated outer `ontology(..., () => {...})`
wrapper is fixed notation, not a callback that consumers should invoke. The
DSL has no imports, bindings, user-authored callbacks, loops, computed
properties, or user-defined functions.

The projection preserves source ordering and all schema 0.1 semantic fields.
It can omit only information made unambiguous by these conventions:

- An attribute name is local to the surrounding `entity`; `amount` in `invoice`
  denotes canonical ID `invoice.amount`.
- `dim()` denotes `role: dimension` and `data_type: string`.
- `dim("integer")`, `time("datetime")`, and `measure("decimal", "currency")`
  explicitly state non-default role/type/unit information.
- `key` and `time` contain local attribute names in the source's declared order.
- Full canonical IDs remain mandatory for references, KPI references, value-map
  targets, and relationships.

## 2. Document shape

```ts
ontology("retail", { version: "0.1", formulaVersion: "1" }, () => {
  entity("order", {
    kind: "event",
    key: ["order_id"],
    time: ["ordered_at"],
    attrs: {
      order_id: dim(),
      ordered_at: time("datetime"),
      customer_id: dim({ ref: "customer.customer_id" }),
      net_amount: measure("decimal", { unit: "currency" }),
    },
  });
});
```

The compiler always emits an `ontology` declaration with canonical ontology
ID, ontology version, and Formula AST version. Its body has zero or more
`entity`, `kpi`, `relates`, and `valueMap` declarations, in canonical YAML
section order.

## 3. Entity and attribute declarations

```ts
entity("<entity-id>", {
  kind: "definition" | "event" | "target",
  desc?: "<description>",
  aka?: ["<synonym>", ...],
  key: ["<local-attribute>", ...],
  time?: ["<local-time-attribute>", ...],
  attrs: { "<local-attribute>": <attribute-declaration>, ... },
});
```

An attribute declaration is one of:

```ts
dim()                                      // dimension:string
dim("<data-type>", { ...options })
time("<data-type>", { ...options })
measure("<data-type>", "<unit>")
measure("<data-type>", { unit: "<unit>", ...options })
```

`dim` may receive options as its only argument when its data type is the
default string: `dim({ ref: "customer.customer_id" })`.

Attribute options map directly to YAML fields:

| DSL option | YAML field |
| --- | --- |
| `desc` | `description` |
| `aka` | `synonyms` |
| `ref` | `reference` |
| `values` | `value_map` |
| `required` | `required` |
| `format` | `format` |
| `grain` | `granularity` |
| `unit` | `unit` |

## 4. Value maps and relationships

```ts
valueMap("value_map.order_status", {
  for: "order.status",
  desc: "Optional map description",
  values: ["confirmed", { value: "retail_store", synonyms: ["store"] }],
});

relates("order", "placed_by", "customer", "n:1");
```

`valueMap` values retain the original scalar/object data. Within those value
objects the canonical YAML field name `synonyms` is retained to avoid an
unnecessary transformation of arbitrary JSON-shaped data.

## 5. KPIs and formulas

```ts
kpi("net_revenue", {
  unit: "currency",
  desc: "Sum of net order amounts.",
  aka: ["revenue"],
  influencedBy: ["..."],
  parameters: [{ /* canonical parameter data */ }],
  expr: agg("sum", "order", attr("order.net_amount")),
});
```

Every Formula AST v1 node has a canonical, non-executable Agent DSL rendering.
The compiler never falls back to an opaque AST blob for a valid v1 formula.
Nested expression fields are recursively rendered; ordinary metadata remains a
plain object or array.

### 5.1 References and literals

```ts
attr("order.net_amount")                         // ref(kind: attribute)
kpiRef("net_revenue")                            // ref(kind: kpi)
valueRef("value_map.order_status", "confirmed") // value_ref
value(<scalar>, "<optional-data-type>")          // typed const; plain literals when untyped
param("minimum_order_value")
baseMetric("net_revenue")
period("monthly")
```

### 5.2 Arithmetic, aggregation, and filters

```ts
add(left, right)          sub(left, right)          mul(left, right)
mod(left, right)          power(base, exponent)
neg(input)                abs(input)                round(input, precision)
floor(input)              ceil(input)
safeDiv(numerator, denominator, { onZero?: null | "zero" | "error" })
least(...args)            greatest(...args)

agg("sum" | "avg" | "min" | "max" | "count" | "count_distinct" | "bool_and" | "bool_or",
    "<scope-entity>", input, { distinct?: boolean })
filter(input, predicate)
```

### 5.3 Predicates, conditions, and null handling

```ts
and(...predicates)        or(...predicates)         not(predicate)
eq(left, right)           ne(left, right)
gt(left, right)           gte(left, right)          lt(left, right)          lte(left, right)
inSet(input, ...values)   notIn(input, ...values)
isNull(input)             isNotNull(input)
between(input, low, high)
like(input, pattern, { caseSensitive?: boolean })
caseWhen([{ when: predicate, then: expression }, ...], elseExpression)
coalesce(...args)         nullIf(left, right)
```

### 5.4 Text, conversion, and time

```ts
concat(...args, { separator?: expression })
lower(input)              upper(input)              trim(input)              length(input)
substring(input, start, length?)
cast(input, "string" | "integer" | "decimal" | "boolean" | "date" | "datetime")

dateTrunc("minute" | "hour" | "day" | "week" | "month" | "quarter" | "year", input)
dateAdd(unit, amount, input)
dateDiff("day" | "week" | "month" | "quarter" | "year", start, end)
extract("year" | "quarter" | "month" | "week" | "day" | "day_of_week" | "hour", input)
currentDate()              currentTimestamp()
```

### 5.5 Statistics, windows, and specialized analytics

```ts
variance("sample" | "population", input)
stddev("sample" | "population", input)
covariance("sample" | "population", x, y)
correlation(x, y)
percentile(input, <0..1>, "continuous" | "discrete")
median(input)              mode(input, "min" | "max" | null)
zScore(input, mean, stddev, { onZeroStddev: null | "zero" | "error" })

window("sum" | "avg" | "min" | "max" | "count" | "count_distinct" | "bool_and" | "bool_or" |
       "row_number" | "rank" | "dense_rank" | "lag" | "lead" | "variance" | "stddev" |
       "median" | "percentile" | "covariance" | "correlation", {
  input?: expression,
  partitionBy?: [attr("...")],
  orderBy?: [{ input: expression, direction: "asc" | "desc", nulls: "first" | "last" }],
  frame?: { kind: "rows" | "range", start: "unbounded_preceding" | "current_row" | number,
            end: "current_row" | "unbounded_following" | number },
  offset?: number,
  default?: expression,
})

movingAverage(baseMetric, windowDays)
runRateProjection("period_to_date", period, baseMetric)
targetProgress(actualMetric, {
  period: "daily" | "weekly" | "monthly" | "quarterly" | "annual" | period("..."),
  targetEntity: "<entity id>",
  targetMeasure: attr("..."),
  scopeKeys: [attr("...")],
})
```

The DSL helper names are serialization notation, not functions supplied by a
runtime. The YAML Formula AST specification remains normative for semantics,
typing, unit compatibility, and capability requirements.

## 6. Compiler behavior

`tools/compile_ontology_dsl.py` imports and calls `validate()` from
`tools/validate_ontology.py`; it does not duplicate validation rules.

```powershell
python tools/compile_ontology_dsl.py examples/saas.yaml
python tools/compile_ontology_dsl.py examples/saas.yaml --output saas.ontology.ts
```

On invalid YAML it exits with status `1`, reports the canonical validator's
errors to standard error, and does not create/write an output file. On valid
YAML it exits with status `0` and writes deterministic UTF-8 output.
