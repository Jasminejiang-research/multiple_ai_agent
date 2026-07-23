# TAM / SAM / SOM Framework

## Purpose

TAM, SAM, and SOM create progressively narrower views of market opportunity.
The framework is useful only when definitions, units, time period,
geography, calculations, and assumptions are transparent.

## Definitions

- **TAM — Total Addressable Market:** annual demand if the defined solution
  served every relevant customer without product, geographic, or capacity
  constraints.
- **SAM — Serviceable Available Market:** the part of TAM addressable by the
  current product category, target segment, geography, channels, and
  regulatory scope.
- **SOM — Serviceable Obtainable Market:** the realistic share of SAM that the
  organization could capture in a stated period given competition, capacity,
  conversion, retention, and capital.

## Required Scope

Specify the offer, buyer, end user, unit of demand, currency, annualization,
geography, base year, and forecast horizon before calculating.

## Bottom-Up Method

Preferred when customer and pricing drivers are observable.

```text
TAM = all relevant customers × annual spend per customer
SAM = serviceable customers × annual spend per customer
SOM = reachable customers × expected penetration × annual spend per customer
```

Use segment-specific pricing and consumption when averages would hide material
differences.

## Top-Down Method

Start with a credible published market estimate and apply explicit filters for
segment, geography, use case, and product fit. Do not multiply arbitrary
percentages merely to reach a desired value.

```text
SAM = published market × supported serviceable share
SOM = SAM × evidence-based obtainable share
```

Top-down estimates should corroborate, not replace, bottom-up reasoning.

## Value-Theory Method

When no stable category exists, estimate willingness to pay from the
measurable economic value created. Validate the assumed value capture with
customer research or experiments.

## Calculation Table

| Layer | Customer definition | Formula | Value | Source IDs | Key assumptions |
|---|---|---|---:|---|---|
| TAM | `[Definition]` | `[Formula]` | `[Amount]` | `[source_ids]` | `[Assumptions]` |
| SAM | `[Definition]` | `[Formula]` | `[Amount]` | `[source_ids]` | `[Constraints]` |
| SOM | `[Definition]` | `[Formula]` | `[Amount]` | `[source_ids]` | `[Capture logic]` |

## SOM Reality Check

Reconcile the SOM with:

- leads or accounts reachable by the planned channels;
- sales capacity and sales-cycle length;
- conversion and retention assumptions;
- production or service-delivery capacity;
- competitor response and switching friction;
- required funding and time horizon.

## Scenario and Sensitivity Analysis

Show downside, base, and upside cases for the few drivers that matter most.
Never present an estimate as a forecast without explaining these drivers.

| Driver | Downside | Base | Upside | Evidence / rationale |
|---|---:|---:|---:|---|
| `[Customer count, price, penetration, etc.]` | `[Value]` | `[Value]` | `[Value]` | `[source_id or assumption]` |

## Quality Checks

- TAM, SAM, and SOM use the same units and time basis.
- SAM is a true subset of TAM, and SOM is a true subset of SAM.
- The model avoids double-counting buyers, users, or revenue.
- Sources include publisher, date, geography, and category definition.
- Assumptions are distinguishable from verified inputs.
- The SOM follows from execution capacity rather than a generic market-share
  percentage.
