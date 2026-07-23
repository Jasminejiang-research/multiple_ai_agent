# Unit Economics Framework

## Purpose

Unit economics tests whether revenue from one defined economic unit can cover
the variable and acquisition costs required to create and serve it. The unit
may be a customer, account, order, subscription, location, or transaction, but
it must be defined consistently.

## Scope and Inputs

Record the unit, customer segment, channel, geography, currency, accounting
period, cohort window, and whether figures are historical, forecast, or
assumed. Avoid mixing monthly and annual values or bookings and recognized
revenue.

## Core Revenue and Margin Metrics

```text
ARPU = recognized revenue / average active units
Gross profit per unit = revenue per unit - variable cost per unit
Gross margin % = gross profit / revenue
Contribution margin = revenue - all costs that vary with serving the unit
```

List which costs are classified as variable or allocated. Typical items can
include payment fees, hosting or inference, fulfillment, support, commissions,
returns, and usage-based third-party services.

## Customer Acquisition Cost

```text
CAC = acquisition sales and marketing cost / new customers acquired
```

Calculate CAC by segment and channel where possible. State whether salaries,
tools, commissions, brand spend, and partner fees are included. Do not compare
blended CAC with revenue from a selectively high-performing cohort.

## Retention and Churn

```text
Logo churn = customers lost / customers at start of period
Revenue churn = recurring revenue lost / recurring revenue at start
Net revenue retention = (starting revenue - churn - contraction + expansion)
                        / starting revenue
```

Use observed cohort retention when available. A simple churn average can hide
large differences by customer age or segment.

## Lifetime Value

A simplified steady-state subscription model is:

```text
LTV = ARPU × gross margin % / periodic customer churn rate
```

Use this formula only when churn is stable and the period is consistent.
Prefer a cohort-based discounted contribution-margin model when data allows.
Do not assume an infinite lifetime or include unearned future revenue without
discounting and sensitivity analysis.

## Payback and Efficiency

```text
CAC payback periods = CAC / contribution margin per unit per period
LTV:CAC = lifetime contribution value / CAC
```

For transactional businesses, also calculate contribution per order and the
number or time of repeat purchases required to recover acquisition cost.

## Assumption Table

| Metric / driver | Value | Unit and period | Segment / channel | Source ID or formula | Status |
|---|---:|---|---|---|---|
| Revenue per unit | `[Value]` | `[Currency/month]` | `[Segment]` | `[source_id]` | `[Observed/assumed]` |
| Variable cost per unit | `[Value]` | `[Currency/month]` | `[Segment]` | `[source_id]` | `[Observed/assumed]` |
| CAC | `[Value]` | `[Currency/customer]` | `[Channel]` | `[Formula]` | `[Observed/assumed]` |
| Churn | `[Value]` | `[%/month]` | `[Cohort]` | `[source_id]` | `[Observed/assumed]` |

## Scenario Analysis

Model downside, base, and upside cases for price, gross margin, CAC, conversion,
retention, and expansion. Show which driver changes the conclusion most.

| Output | Downside | Base | Upside | Decision threshold |
|---|---:|---:|---:|---:|
| Contribution margin | `[Value]` | `[Value]` | `[Value]` | `[Minimum]` |
| CAC payback | `[Periods]` | `[Periods]` | `[Periods]` | `[Maximum]` |
| LTV:CAC | `[Ratio]` | `[Ratio]` | `[Ratio]` | `[Minimum]` |

## Quality Checks

- The economic unit and measurement period are explicit.
- Revenue, margin, CAC, churn, and LTV use compatible segments and cohorts.
- Variable costs include costs that truly scale with usage or fulfillment.
- CAC includes the stated sales and marketing components.
- LTV is based on contribution or gross profit, not revenue alone.
- Forecasts are labeled, formulas are reproducible, and uncertainty is shown.
- Attractive ratios are not treated as proof of adequate cash runway or total
  company profitability.
