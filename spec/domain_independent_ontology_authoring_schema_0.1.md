# Domain-independent ontology authoring schema 0.1

This document defines the semantic authoring format for a domain ontology.
It is domain-independent: it describes business concepts, not database tables,
columns, SQL dialects, or physical join conditions.

## Status and scope

This is the canonical authoring contract. It uses three attribute roles and a
small portable data-type set.

## 1. Complete document shape

```yaml
ontology_id: <lowercase ontology id>
ontology_version: "<immutable baseline version>"
formula_schema_version: "1"

entities: []
kpis: []
relationships: []
value_maps: []
```

All six top-level fields are required. `entities`, `kpis`, `relationships`,
and `value_maps` must be lists, including when empty.

| Field | Type | Meaning |
| --- | --- | --- |
| `ontology_id` | lowercase string | Stable semantic identifier, such as `retail` or `healthcare`. |
| `ontology_version` | string | Immutable version of this domain baseline, such as `"0.1"`. |
| `formula_schema_version` | string | Version of the Formula AST contract. Schema 0.1 uses `"1"`. |
| `entities` | list | Business objects, events, and targets. |
| `kpis` | list | Canonical measurable concepts and formulas. |
| `relationships` | list | Conceptual links between entities. |
| `value_maps` | list | Controlled vocabularies for dimensions. |

Identifiers must be lowercase, stable semantic names. Do not use physical
source names such as `dw.fact_order_v2` or `ga_session_id` as ontology IDs.

## 2. Entities

An entity is a business concept that owns attributes. Attributes are nested
inside their entity and are not declared in a top-level attribute list.

```yaml
entities:
  - id: order
    entity_type: event
    description: A confirmed customer purchase.
    synonyms: [purchase, sale]
    identity_attributes: [order.order_id]
    time_attributes: [order.ordered_at]
    attributes: []
```

| Entity field | Required | Type | Rules |
| --- | --- | --- | --- |
| `id` | Yes | lowercase string | Unique entity identifier. |
| `entity_type` | Yes | enum | `definition`, `event`, or `target`. |
| `identity_attributes` | Yes | non-empty list of attribute IDs | Every item must identify an attribute owned by this entity. Their ordered combination is the entity's semantic identity. |
| `attributes` | Yes | list | Attributes owned by the entity. |
| `time_attributes` | No | non-empty list of attribute IDs | Temporal attributes owned by this entity. The ordered combination may represent a composite temporal key. |
| `description` | No | string | Business meaning. |
| `synonyms` | No | list of strings | Alternate user-facing names. |

### Entity types

| Type | Use for | Examples |
| --- | --- | --- |
| `definition` | Stable things, lookup concepts, and master data. | `customer`, `product`, `facility` |
| `event` | Things that happen at a time or interval. | `order`, `visit`, `measurement` |
| `target` | Plans, budgets, quotas, thresholds, or expected values. | `monthly_target`, `service_goal` |

## 3. Attributes: three roles only

Every attribute has exactly one role. Schema 0.1 supports only:

```yaml
dimension | time | measure
```

Identity, conceptual relationships, and time granularity are independent
properties because they describe different concerns.

| Role | Meaning | Typical examples |
| --- | --- | --- |
| `dimension` | A categorical, identifying, relational, or descriptive value used to group or filter. | `order.order_id`, `order.customer_id`, `product.category` |
| `time` | A date or timestamp that scopes, orders, or groups a result in time. | `order.ordered_at`, `target.period_start` |
| `measure` | A numeric quantity that can be aggregated or used in a formula. | `order.net_amount`, `inventory.on_hand_quantity` |

### Attribute fields

```yaml
attributes:
  - id: order.order_id
    role: dimension
    data_type: string

  - id: order.customer_id
    role: dimension
    data_type: string
    reference: customer.customer_id

  - id: order.ordered_at
    role: time
    data_type: datetime

  - id: order.net_amount
    role: measure
    data_type: decimal
    unit: currency
```

| Attribute field | Required | Type | Rules |
| --- | --- | --- | --- |
| `id` | Yes | lowercase `entity.attribute` string | Unique and prefixed by its owning entity ID. |
| `role` | Yes | enum | Exactly one of `dimension`, `time`, `measure`. |
| `data_type` | Yes | enum | One of the basic types defined below. |
| `description` | No | string | Business meaning or constraints. |
| `synonyms` | No | list of strings | Alternate user-facing terms. |
| `reference` | No | attribute ID | Canonical target attribute for a relational dimension. |
| `value_map` | No | value-map ID | Controlled vocabulary for a dimension. |
| `required` | No | boolean | Whether a value is semantically required. Defaults to `true`. |
| `format` | No | string | Display or interpretation hint, e.g. `uri`. |
| `granularity` | No | enum | Time resolution; valid only for `time`: `minute`, `hour`, `day`, `week`, `month`, `quarter`, `year`. |
| `unit` | No | enum | Unit of a `measure`; one of the bounded unit list below. |

### Identity and relationships

An identity is declared by the containing entity's `identity_attributes`, not
by an attribute role:

```yaml
- id: customer
  entity_type: definition
  identity_attributes: [customer.customer_id]
  attributes:
    - id: customer.customer_id
      role: dimension
      data_type: string
```

A conceptual reference is declared by singular `reference`. The value is the
target ontology attribute, not a physical source column:

```yaml
- id: order.customer_id
  role: dimension
  data_type: string
  reference: customer.customer_id
```

An attribute may be both an entity's identity and a dimension. A relational
attribute may also be grouped or filtered like any other dimension.

For a composite identity, list each component in deterministic order:

```yaml
- id: order_line
  entity_type: event
  identity_attributes: [order_line.order_id, order_line.line_number]
  attributes:
    - {id: order_line.order_id, role: dimension, data_type: string, reference: order.order_id}
    - {id: order_line.line_number, role: dimension, data_type: integer}
```

The identity is the ordered tuple `(order_id, line_number)`, not either
attribute alone.

### Time periods and granularity

Represent a monthly or quarterly target with one or more `time` attributes and
an explicit granularity:

```yaml
- id: monthly_target.period_start
  role: time
  data_type: date
  granularity: month
```

When a source represents time as separate calendar components, use multiple
`time_attributes` in deterministic order. `integer` is allowed for a `time`
attribute only when it is a calendar component with declared granularity:

```yaml
- id: monthly_target
  entity_type: target
  identity_attributes: [monthly_target.target_id]
  time_attributes: [monthly_target.year, monthly_target.month]
  attributes:
    - {id: monthly_target.target_id, role: dimension, data_type: string}
    - {id: monthly_target.year, role: time, data_type: integer, granularity: year}
    - {id: monthly_target.month, role: time, data_type: integer, granularity: month}
```

The ordered tuple `(year, month)` identifies the monthly temporal coordinate;
neither component alone should be interpreted as a complete month.

## 4. Basic data types only

Schema 0.1 supports this complete data-type whitelist:

```yaml
string | integer | decimal | boolean | date | datetime
```

| Data type | Use for | Examples |
| --- | --- | --- |
| `string` | Text, identifiers, codes, categories, and values from a value map. | `customer_id`, `country`, `status` |
| `integer` | Whole-number counts and quantities. | `quantity`, `units_in_stock` |
| `decimal` | Exact fractional numeric values. Use for money, rates, and measurements. | `net_amount`, `weight`, `conversion_rate` |
| `boolean` | True/false flags. | `is_subscription`, `is_returned` |
| `date` | Calendar date without a time of day. | `period_start`, `order_date` |
| `datetime` | Timestamp or local date-time. Timezone policy belongs to execution context. | `ordered_at`, `captured_at` |

Rules:

- `measure` normally uses `integer` or `decimal`.
- `time` normally uses `date` or `datetime`. It may use `integer` only for a
  calendar component such as `year` or `month`, with `granularity` declared.
- `dimension` may use any basic type, but `string` is preferred for business
  identifiers and controlled categories.
- Store a rate as a `decimal` and declare its KPI unit as `ratio` or `percent`.
  Do not create a separate `percentage` data type.
- Use `date` plus `granularity: month` for a monthly temporal value.

## 5. Units: a bounded generic list

Units apply to `measure` attributes and KPI outputs. Schema 0.1 allows only:

```yaml
count | currency | ratio | percent | seconds | bytes | unitless
```

| Unit | Meaning | Typical value type |
| --- | --- | --- |
| `count` | Discrete count of things, events, or records. | `integer` |
| `currency` | Monetary amount in the execution context's configured currency. | `decimal` |
| `ratio` | Unitless proportion on a 0-1 scale. | `decimal` |
| `percent` | Proportion on a 0-100 scale. | `decimal` |
| `seconds` | Elapsed duration in canonical seconds. Convert display units at presentation time. | `integer` or `decimal` |
| `bytes` | Digital information size in canonical bytes. | `integer` |
| `unitless` | A score, index, or normalized value with no physical unit. | `integer` or `decimal` |

`duration` is not a data type. Model elapsed time as an `integer` or `decimal`
measure with `unit: seconds`:

```yaml
- id: fulfillment.elapsed_time
  role: measure
  data_type: integer
  unit: seconds
```

Do not author arbitrary unit strings. If a domain needs a unit outside this
list, the schema must be versioned to add it rather than allowing a free-form
value.

## 6. Value maps

A value map is a controlled vocabulary for one dimensional attribute. It maps
accepted terms to a stable canonical value.

```yaml
value_maps:
  - id: value_map.sales_channel
    reference: order.channel
    description: Channel through which an order was placed.
    values:
      - web
      - value: retail_store
        synonyms: [store, physical store]
      - value: marketplace
        synonyms: [third party marketplace]
```

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | Yes | Unique lowercase identifier, conventionally `value_map.<concept>`. |
| `reference` | Yes | Existing dimension attribute that uses this vocabulary. |
| `values` | Yes | List of canonical value strings or value objects. |
| `description` | No | Meaning and authoring guidance. |

A value object requires `value` and may contain `synonyms` and `description`.

## 7. Relationships

Relationships state conceptual meaning only. Do not include physical join
keys, tables, columns, or SQL in this section.

```yaml
relationships:
  - from: order
    relationship: placed_by
    to: customer
    cardinality: "n:1"
```

| Field | Required | Rules |
| --- | --- | --- |
| `from` | Yes | Existing source entity ID. |
| `relationship` | Yes | Lowercase conceptual predicate. |
| `to` | Yes | Existing target entity ID. |
| `cardinality` | Yes | One of `"1:1"`, `"1:n"`, `"n:1"`, or `"n:n"`. |

## 8. KPIs

A KPI defines a named measurable concept. Its formula uses the versioned
Formula AST, not SQL or physical identifiers.

```yaml
kpis:
  - id: net_revenue
    unit: currency
    description: Sum of net order amount.
    synonyms: [revenue]
    expr_ast:
      type: agg
      function: sum
      scope_entity: order
      arg: {type: ref, kind: attribute, id: order.net_amount}
```

| KPI field | Required | Meaning |
| --- | --- | --- |
| `id` | Yes | Unique lowercase KPI identifier. |
| `unit` | Yes | One of the bounded unit list, or `varies` when a parameterized KPI inherits its unit from its selected base KPI. |
| `expr_ast` | Yes | Formula AST v1 expression. |
| `description` | No | Business definition and interpretation. |
| `synonyms` | No | Alternate metric names. |
| `influenced_by` | No | KPI lineage/driver metadata. |
| `parameters` | No | Typed inputs for specialized formula contracts. |

Formula AST expressions must use canonical attribute/KPI references. Physical
source binding occurs after semantic validation.

## 9. Formula AST v1 specification

`expr_ast` is a versioned semantic expression tree. It is not SQL and must
never contain tables, columns, quoted identifiers, raw SQL, subqueries,
DDL/DML, or arbitrary database function names. A renderer binds canonical
ontology attributes to physical sources and may build a transient SQLGlot AST
only after this formula has been validated.

Every node is an object with a required `type`. Unknown node types and unknown
fields must be rejected.

### 9.1 Supported node families

| Family | Node types |
| --- | --- |
| References and literals | `ref`, `value_ref`, `const`, `param`, `base_metric_ref`, `period_ref` |
| Arithmetic | `add`, `sub`, `mul`, `safe_div`, `mod`, `neg`, `abs`, `round`, `floor`, `ceil`, `power` |
| Aggregation | `agg`, `filter` |
| Predicates | `and`, `or`, `not`, `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `is_null`, `is_not_null`, `between`, `like` |
| Conditional and null | `case`, `coalesce`, `nullif` |
| Text and conversion | `concat`, `lower`, `upper`, `trim`, `substring`, `length`, `cast` |
| Date and time | `date_trunc`, `date_add`, `date_diff`, `extract`, `current_date`, `current_timestamp` |
| Statistics | `variance`, `stddev`, `covariance`, `correlation`, `percentile`, `median`, `mode`, `z_score` |
| Windows | `window` |
| Specialized analytics | `moving_average`, `run_rate_projection`, `target_progress` |

### 9.2 References and literals

```yaml
{type: ref, kind: attribute | kpi, id: <canonical id>}
{type: value_ref, value_map: <value_map id>, id: <canonical value id>}
{type: const, value: <scalar | null>, data_type: <optional basic data type>}
{type: param, name: <parameter name>}
{type: base_metric_ref, default: <kpi id>}
{type: period_ref, default: daily | weekly | monthly | quarterly | annual}
```

`ref` IDs, `value_ref` IDs, and `param` names must resolve in the ontology.
`const` cannot contain a physical identifier or SQL fragment.

### 9.3 Arithmetic and aggregation

```yaml
{type: add | sub | mul | mod, left: <expression>, right: <expression>}
{type: power, base: <expression>, exponent: <expression>}
{type: neg | abs | floor | ceil, arg: <expression>}
{type: round, arg: <expression>, precision: <integer expression>}
{type: safe_div, numerator: <expression>, denominator: <expression>, on_zero: null | zero | error}

{type: agg,
 function: sum | avg | min | max | count | count_distinct | bool_and | bool_or,
 scope_entity: <entity id>,
 arg: <expression>,
 distinct: <optional boolean>}

{type: filter, input: <expression>, where: <predicate expression>}
```

`safe_div` is required instead of ordinary division. `on_zero: null` is the
default and means no result rather than a fabricated zero. `filter` scopes only
its input; it does not alter the caller's overall query filters.

### 9.4 Predicates and `if / else`

```yaml
{type: and | or, args: [<predicate>, <predicate>, ...]}
{type: not, arg: <predicate>}
{type: eq | ne | gt | gte | lt | lte, left: <expression>, right: <expression>}
{type: in | not_in, input: <expression>, values: [<expression>, ...]}
{type: is_null | is_not_null, arg: <expression>}
{type: between, input: <expression>, low: <expression>, high: <expression>}
{type: like, input: <expression>, pattern: <expression>, case_sensitive: <optional boolean>}
```

Formula AST v1 represents `if / else` using one canonical `case` node; it does
not define a second equivalent `if` node:

```yaml
type: case
branches:
  - when:
      type: gte
      left: {type: ref, kind: attribute, id: order.net_amount}
      right: {type: const, value: 1000, data_type: decimal}
    then: {type: const, value: enterprise, data_type: string}
  - when:
      type: gte
      left: {type: ref, kind: attribute, id: order.net_amount}
      right: {type: const, value: 100, data_type: decimal}
    then: {type: const, value: standard, data_type: string}
else: {type: const, value: small, data_type: string}
```

Branches are evaluated in order; the first `when` that is true wins. `else` is
required. A null predicate is not true and continues to the next branch.
Every `then` and `else` expression must have compatible types and units.

### 9.5 Null, text, type, and time functions

```yaml
{type: coalesce, args: [<expression>, <expression>, ...]}
{type: nullif, left: <expression>, right: <expression>}
{type: concat, args: [<expression>, ...], separator: <optional expression>}
{type: lower | upper | trim | length, arg: <expression>}
{type: substring, input: <expression>, start: <integer expression>, length: <optional integer expression>}
{type: cast, input: <expression>, to: string | integer | decimal | boolean | date | datetime}

{type: date_trunc, unit: minute | hour | day | week | month | quarter | year, input: <expression>}
{type: date_add, unit: minute | hour | day | week | month | quarter | year, amount: <integer expression>, input: <expression>}
{type: date_diff, unit: day | week | month | quarter | year, start: <expression>, end: <expression>}
{type: extract, part: year | quarter | month | week | day | day_of_week | hour, input: <expression>}
{type: current_date}
{type: current_timestamp}
```

Timezone, week-start, and calendar policy come from the execution context, not
the database default.

### 9.6 Statistical functions

Statistical functions must state their method and population semantics. Null
inputs are ignored; an empty or insufficient sample returns null, never zero.

```yaml
{type: variance | stddev, population: sample | population, input: <numeric expression>}
{type: covariance, population: sample | population, x: <numeric expression>, y: <numeric expression>}
{type: correlation, x: <numeric expression>, y: <numeric expression>}
{type: percentile, input: <orderable expression>, percentile: <0 to 1>, method: continuous | discrete}
{type: median, input: <orderable expression>}
{type: mode, input: <orderable expression>, tie_break: min | max | null}
{type: z_score, input: <numeric expression>, mean: <expression>, stddev: <expression>, on_zero_stddev: null | zero | error}
```

| Function | Defined behavior |
| --- | --- |
| `variance`, `stddev`, `covariance` | `sample` divides by `n - 1`; `population` divides by `n`. |
| `correlation` | Pearson correlation; returns null with fewer than two valid pairs or zero variance. |
| `percentile` | Percentile is in `[0, 1]`; `continuous` interpolates and `discrete` chooses an observed value. |
| `median` | Exact continuous percentile at `0.5`. |
| `mode` | Most frequent non-null value; `tie_break` is mandatory. |
| `z_score` | `(input - mean) / stddev`, using the declared zero-standard-deviation behavior. |

Exact percentile, median, and mode must never be silently replaced by an
approximation. A future approximate function must have a distinct node name
and explicit error/algorithm contract.

### 9.7 Window functions

```yaml
type: window
function: sum | avg | min | max | count | count_distinct | row_number | rank | dense_rank | lag | lead | variance | stddev | median | percentile | covariance | correlation
input: <expression>                    # not required for row_number/rank/dense_rank
partition_by: [<attribute ref>, ...]
order_by:
  - {input: <expression>, direction: asc | desc, nulls: first | last}
frame:
  kind: rows | range
  start: unbounded_preceding | current_row | <integer>
  end: current_row | unbounded_following | <integer>
offset: <optional non-negative integer> # lag/lead
default: <optional expression>          # lag/lead
```

### 9.8 Evaluation stages and specialized analytics

| Stage | Examples | Rule |
| --- | --- | --- |
| `row` | refs, literals, predicates, `case`, scalar text/date functions | May use only row-stage inputs. |
| `aggregate` | `agg`, aggregate statistics, arithmetic over aggregate/KPI results | May consume row-stage inputs, not a window result at the same query level. |
| `window` | `window`, windowed `z_score` | May consume row/aggregate results but cannot be nested in another aggregate/window at the same level. |

`moving_average`, `run_rate_projection`, and `target_progress` are named,
typed contracts for analytics that cannot safely be inferred from generic SQL
syntax. They may be used only when the active runtime explicitly supports them.

### 9.9 Runtime capability gate

Formula AST v1 defines valid semantic syntax; runtime renderers declare the
smaller set they can execute for a given dialect. A baseline must be rejected
at validation/publish time if its AST uses an unsupported node, aggregate,
statistical method, window behavior, or dialect feature.

```yaml
formula_capabilities:
  formula_schema_version: "1"
  supported_node_types: [ref, const, agg, mul, safe_div]
  supported_aggregate_functions: [sum, count_distinct]
  supported_dialects: [postgres]
```

## 10. Validation rules

Before publishing, validate all of the following:

1. The six required top-level fields are present.
2. Entity, attribute, KPI, value-map, and relationship identifiers are unique
   in their namespaces and lowercase.
3. Every entity has a non-empty, owned `identity_attributes` list; every item
   in `time_attributes`, when present, is an owned `time` attribute.
4. Every attribute uses exactly one of the three allowed roles and one of the
   six allowed data types.
5. `reference` targets an existing `dimension` attribute and is used only on a
   `dimension`; its target entity is derived from the target attribute ID.
6. `value_map` targets an existing value map; each value map references an
   existing `dimension`.
7. `granularity` is used only on a `time` attribute; `unit` only on a
   `measure` attribute and must use the bounded unit list. An integer time
   attribute must declare granularity.
8. Every relationship endpoint names an existing entity and uses a valid
   cardinality.
9. Each KPI has an executable Formula AST with only supported runtime
   capabilities.
10. The document contains no physical source/table/column/join definitions.

## 11. Minimal valid example

```yaml
ontology_id: retail
ontology_version: "0.1"
formula_schema_version: "1"

entities:
  - id: order
    entity_type: event
    identity_attributes: [order.order_id]
    time_attributes: [order.ordered_at]
    attributes:
      - {id: order.order_id, role: dimension, data_type: string}
      - {id: order.ordered_at, role: time, data_type: datetime}
      - {id: order.net_amount, role: measure, data_type: decimal, unit: currency}

kpis:
  - id: net_revenue
    unit: currency
    expr_ast:
      type: agg
      function: sum
      scope_entity: order
      arg: {type: ref, kind: attribute, id: order.net_amount}

relationships: []
value_maps: []
```
