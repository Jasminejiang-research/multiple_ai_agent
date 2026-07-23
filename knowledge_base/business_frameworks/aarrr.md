# AARRR Framework

## Purpose

AARRR maps the customer lifecycle through Acquisition, Activation, Retention,
Referral, and Revenue. Use it to diagnose a growth system and assign
stage-specific metrics, experiments, and owners—not as a vanity-metric
dashboard.

## Define the Basics

Before measuring, specify:

- target segment and analysis period;
- user and account identity rules;
- the product's core value event;
- cohort definition and attribution window;
- data source, exclusions, and metric owner;
- a `source_id` for each external benchmark or material input.

## 1. Acquisition

**Question:** How do qualified prospects first arrive?

Candidate measures include qualified visitors, sign-ups, customer acquisition
cost by channel, and visit-to-sign-up conversion. Separate paid, organic,
partner, and sales-led channels.

## 2. Activation

**Question:** Do new users experience the product's value?

Define one observable activation event based on behavior that predicts later
value—for example, completing a key workflow—not a superficial event such as
opening an email.

```text
Activation rate = activated new users / eligible new users
```

## 3. Retention

**Question:** Do users repeatedly receive value?

Use cohorts and a product-appropriate return interval. Measure logo retention,
user retention, revenue retention, or repeat purchase separately.

```text
Period-N retention = cohort members active in period N / original cohort size
```

## 4. Referral

**Question:** Do satisfied users create qualified new demand?

Track invitations, shares, referred sign-ups, referral conversion, or a viral
coefficient only when the referral mechanism is observable.

```text
Viral coefficient = invitations per active user × invite conversion rate
```

## 5. Revenue

**Question:** Does delivered value convert into sustainable revenue?

Track paid conversion, average revenue per account, expansion, churn, gross
margin, payback, and lifetime value using explicit definitions.

## Funnel Specification

| Stage | Event definition | Primary metric | Data source | Window | Owner |
|---|---|---|---|---|---|
| Acquisition | `[Qualified arrival]` | `[Metric]` | `[System]` | `[Window]` | `[Role]` |
| Activation | `[Core value event]` | `[Metric]` | `[System]` | `[Window]` | `[Role]` |
| Retention | `[Repeat value event]` | `[Metric]` | `[System]` | `[Window]` | `[Role]` |
| Referral | `[Qualified referral]` | `[Metric]` | `[System]` | `[Window]` | `[Role]` |
| Revenue | `[Monetization event]` | `[Metric]` | `[System]` | `[Window]` | `[Role]` |

## Experiment Loop

1. Find the largest evidence-backed constraint in the lifecycle.
2. Form a causal hypothesis for one segment and stage.
3. Define the intervention, primary metric, guardrail, and stopping rule.
4. Run the experiment for an adequate window.
5. Record the result, uncertainty, and next decision.

| Hypothesis | Stage | Experiment | Primary metric | Guardrail | Decision rule |
|---|---|---|---|---|---|
| `[If..., then..., because...]` | `[Stage]` | `[Test]` | `[Metric]` | `[Metric]` | `[Rule]` |

## Quality Checks

- Events represent customer value rather than easy-to-count activity.
- Metrics use stable identities, denominators, and time windows.
- Retention is cohort-based and appropriate to product cadence.
- Channel and customer segments are not blended when economics differ.
- Revenue metrics connect to margin and retention, not only bookings.
- Experiments include guardrails and do not optimize one stage at the expense
  of the whole lifecycle.
