<a href="https://valority.ai/"><img src="https://media.base44.com/images/public/69553b6983f22802d06a0577/9fff0d47f_Vicon-transparent.png" alt="Valority" width="180"></a>

# Valority Ontology Language

A lightweight, domain-independent language for describing business meaning in a form that people, AI agents, analytics systems, and applications can share.

Most AI systems can connect to data. That does not mean they understand what the data means.

Ask two teams what "revenue," "active customer," or "conversion" means and you may get different answers. Connect an AI agent to the same systems and it has the same problem. It can read tables and write SQL, but it still has to infer the business definitions behind the data.

The Valority Ontology Language provides a structured way to make those definitions explicit.

It describes the business concepts, metrics, relationships, and controlled vocabularies that make up a domain, without tying them to a specific database, warehouse, SaaS application, or AI platform.

## Why this exists

Business meaning is often scattered across dashboards, SQL queries, documentation, prompts, and people's heads.

That works until different systems or teams interpret the same term differently.

For example, "revenue" could mean:

- gross order value;
- revenue after refunds;
- recognized accounting revenue;
- attributed campaign revenue.

An AI agent should not have to guess which one you mean.

An ontology gives these concepts canonical names and definitions that can be reused across systems.

The goal is simple:

> Define business meaning once, then map it to whatever data sources and applications need to use it.

For a practical introduction to this idea, see [Teach AI Your Business](https://valority.ai/blog/teach-ai-your-business).

## What the language describes

An ontology contains four main kinds of business knowledge.

### Entities

The things and events that exist in a domain.

Examples:

```text
customer
order
product
campaign
subscription
```

Entities own `dimension`, `time`, and `measure` attributes. An entity's
semantic identity is declared separately with its non-empty
`identity_attributes` list.

### KPIs

Named measurable concepts with explicit definitions.

Examples:

```text
net_revenue
orders
conversion_rate
average_order_value
```

KPI formulas use a structured expression language called Formula AST rather than raw SQL.

### Relationships

Business relationships between entities.

For example:

```text
order placed_by customer
order contains product
```

These describe semantic relationships, not database joins.

### Value maps

Canonical vocabularies for values that may appear under different names.

For example:

```text
retail_store
```

could recognize:

```text
store
shop
physical store
```

This lets different systems and users speak slightly different languages while resolving to the same business concept.

## A small example

```yaml
ontology_id: retail
ontology_version: "0.1"
formula_schema_version: "1"

entities:
  - id: customer
    entity_type: definition
    identity_attributes: [customer.customer_id]
    attributes:
      - id: customer.customer_id
        role: dimension
        data_type: string

  - id: order
    entity_type: event
    identity_attributes: [order.order_id]
    time_attributes: [order.ordered_at]
    attributes:
      - id: order.order_id
        role: dimension
        data_type: string

      - id: order.ordered_at
        role: time
        data_type: datetime

      - id: order.customer_id
        role: dimension
        reference: customer.customer_id
        data_type: string

      - id: order.channel
        role: dimension
        data_type: string
        value_map: value_map.order_channel

      - id: order.net_amount
        role: measure
        data_type: decimal
        unit: currency

kpis:
  - id: net_revenue
    unit: currency
    description: Revenue from confirmed orders after applicable adjustments.
    synonyms: [revenue, sales]

    expr_ast:
      type: agg
      function: sum
      scope_entity: order
      arg:
        type: ref
        kind: attribute
        id: order.net_amount

relationships:
  - from: order
    relationship: placed_by
    to: customer
    cardinality: "n:1"

value_maps:
  - id: value_map.order_channel
    reference: order.channel
    values:
      - web
      - value: retail_store
        synonyms: [store, physical store]
```

The important part is not YAML itself. The important part is that `net_revenue`, `order`, `customer`, and `retail_store` now have explicit meanings that software can reason about.

## Business meaning is separate from physical data

The ontology is deliberately independent of physical data sources.

You will not find things like this in the ontology:

```text
warehouse table names
database column names
SQL joins
Shopify fields
Salesforce objects
Snowflake schemas
BigQuery datasets
```

Those belong in a separate source-mapping layer.

For example, the ontology may define:

```text
order.net_amount
```

One company might map that concept to Shopify. Another might map it to a Snowflake table. A third might derive it from several systems.

The business definition stays the same even when the underlying implementation changes.

This separation is one of the main design principles of the language.

## Formula AST

KPIs need more than names and descriptions. Some of them also need executable definitions.

Instead of embedding SQL in the ontology, formulas are represented as a structured Abstract Syntax Tree.

For example:

```yaml
- id: average_order_value
  unit: currency
  expr_ast:
    type: safe_div
    numerator:
      type: ref
      kind: kpi
      id: net_revenue
    denominator:
      type: ref
      kind: kpi
      id: orders
```

Formula AST provides a constrained, portable expression language for calculations,
aggregation, bounded scalar expressions (`least` and `greatest`), filtering,
conditions, date operations, statistics, and analytical functions.

It intentionally excludes raw SQL and physical table or column references.

A runtime can translate supported Formula AST expressions into SQL or another execution format after the ontology has been mapped to physical data.

`formula_schema_version` selects the semantic Formula AST contract:

```yaml
formula_schema_version: "1"
```

Each runtime must separately declare the Formula AST node types, aggregate
functions, statistical methods, window behavior, and dialect features it can
execute. An ontology must be rejected at publish time when it uses a feature
outside the active runtime capability set.

See the specification for the complete Formula AST v1 contract.

## Domain-independent by design

The language does not define what a customer, order, campaign, patient, machine, or transaction should look like.

Those belong to individual domain ontologies.

The same authoring format can therefore be used for domains such as:

```text
e-commerce
SaaS
marketing
financial services
manufacturing
healthcare
advertising
```

Each domain defines its own vocabulary while following the same language rules.

## What this is not

This project is not a database schema.

It is not a replacement for your warehouse.

It is not a SQL modeling framework.

It does not define how physical sources should be joined.

It is also not intended to model every piece of knowledge inside an organization.

The aim is narrower: provide a stable semantic contract for the business concepts that systems need to understand and reason about consistently.

## Why this matters for AI

A skill or prompt can tell an AI agent what process to follow.

It cannot reliably resolve ambiguous business terminology unless those definitions exist somewhere.

A skill might tell an agent:

> Investigate the decline in revenue and break it down by channel.

The ontology tells the agent what `revenue` and `channel` actually mean, which values belong to each channel, which entities are related, and which KPIs may influence the result.

That distinction becomes increasingly important as AI systems move from answering questions to running analyses and making decisions.

## Using the language

### Validate an ontology

The repository includes a small validator for schema 0.1. It gives one clear
error per invalid field and exits with `0` for a valid file or `1` otherwise.
It requires Python 3.9+ and [PyYAML](https://pyyaml.org/):

```powershell
python -m pip install -r requirements.txt
```

Validate an ontology locally:

```powershell
python tools/validate_ontology.py examples/retail.yaml
```

The validator checks the document shape, allowed fields, identifiers, entity
ownership, relationship and value-map references, KPI dependency cycles, and
the complete structural contract of every Formula AST node. Formula AST type
and unit inference, plus runtime capability checks, remain the responsibility
of a runtime because its supported features are implementation-specific.

Use `--fix` to add only missing empty top-level lists. It saves the original
file as `<file>.bak` and re-formats the YAML. It never guesses IDs, references,
roles, data types, or Formula AST meanings.

```powershell
python tools/validate_ontology.py examples/retail.yaml --fix
```

In CI, validate the committed examples (and any ontology directory added by an
application):

```powershell
python tools/validate_ontology.py examples/retail.yaml
python tools/validate_ontology.py examples/saas.yaml
```

Run the validator's regression tests before opening a pull request:

```powershell
python -m unittest discover -s tests -v
```

### Compile agent context

The YAML authoring file is the only source of truth. Before an AI agent reads
an ontology, compile its validated YAML into the compact, read-only Agent
Ontology DSL:

```text
YAML authoring source → canonical validation → generated agent context
```

The compiler does not modify the YAML, execute TypeScript, or create a second
editable ontology format. Treat its output as generated context: regenerate it
after every YAML change and do not hand-edit it.

```powershell
# Print DSL to standard output
python tools/compile_ontology_dsl.py examples/saas.yaml

# Write DSL to a generated file for an agent integration
python tools/compile_ontology_dsl.py examples/saas.yaml --output saas.ontology.ts
```

The compiler imports and uses the same YAML validator, so it emits no DSL for
an invalid ontology. It exits with `1` and leaves the requested output path
untouched when validation fails. The DSL is TypeScript-shaped context, not
executable code; agents and runtimes must parse or consume it as data rather
than executing it. Its complete contract is in
[`spec/agent_ontology_dsl_0.1.md`](spec/agent_ontology_dsl_0.1.md).

A typical implementation has three separate layers:

```text
Business ontology
        |
        v
Physical source mapping
        |
        v
Execution / AI / analytics
```

The ontology defines meaning.

The mapping layer connects that meaning to actual data.

The runtime uses both to query, analyze, validate, or reason over the data.

These layers can evolve independently.

## Specification status

The current version is:

```text
Ontology authoring schema: 0.1
Formula AST: 1
Agent Ontology DSL: 0.1 (generated projection)
Status: early specification
```

Version `0.1` is intended for experimentation and implementation feedback. The language may change before a stable `1.0` release.

Semantic changes should result in a new ontology version. Formula-language compatibility is governed separately through `formula_schema_version`.

## Repository structure

A typical repository layout is:

```text
.
├── README.md
├── LICENSE
├── requirements.txt                 # validator dependency
├── .github/
│   └── workflows/
│       └── validate.yml              # pull-request validation
├── spec/
│   ├── agent_ontology_dsl_0.1.md      # generated agent-context DSL
│   └── domain_independent_ontology_authoring_schema_0.1.md
├── examples/
│   ├── retail.yaml
│   └── saas.yaml
├── tools/
│   ├── compile_ontology_dsl.py        # validates YAML, then emits Agent DSL
│   └── validate_ontology.py          # schema 0.1 validator
└── tests/
    ├── fixtures/                     # intentionally invalid test inputs
    └── test_validate_ontology.py
```

## Luke and Valority

The ontology language is developed by Valority and is designed to be usable independently.

Luke uses the language as part of its semantic foundation for AI-driven analysis and decision-making, but using this specification does not require Luke.

The goal is for the language to be useful anywhere a system needs a consistent understanding of business concepts.

## Contributing

The specification is still early, and feedback from people building semantic layers, analytics systems, AI agents, and data platforms is welcome.

Good areas for discussion include:

- missing semantic concepts;
- ambiguous definitions;
- Formula AST portability;
- validation rules;
- domain modeling examples;
- interoperability with existing semantic and data platforms.

Please open an issue before proposing substantial changes to the language so the design and compatibility implications can be discussed first.

For collaboration, implementation support, or general questions, [contact Valority](https://valority.ai/Contact).

## License

This project is licensed under the Apache License 2.0.

See [LICENSE](LICENSE) for details.

Valority, Luke, and associated names and logos are not granted under the Apache License 2.0 and may be subject to separate trademark rights.

## Documentation

The complete authoring schema and Formula AST specification is in
[`spec/domain_independent_ontology_authoring_schema_0.1.md`](spec/domain_independent_ontology_authoring_schema_0.1.md).
