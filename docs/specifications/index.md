# Specifications

What this service must do, as numbered requirements that a test can name.

## Where these came from

They were **extracted from the test suite**, not written ahead of it. Every requirement
below describes behaviour that some test already asserts, and the test was read to write
the requirement rather than the other way round.

That order is deliberate and it is also the limit of what this document claims. These are
the guarantees this service **actually makes today**, as evidenced by something that runs.
They are not a product specification, they are not exhaustive, and a behaviour absent here
is not thereby forbidden — it is unverified, which is a different statement.

Where a requirement is worth stating but the code does not meet it, the test is written to
the requirement and marked `xfail(strict=True)` with its reason — recorded, verified to
still be broken, and loud the day someone fixes it. **There are currently none**; the two
that existed were resolved on 2026-08-15, one by fixing the code and one by deciding the
behaviour was correct and writing the requirement to it.

## The identifier scheme

`REQ-` followed by four digits, allocated by area:

| Range | Area | Document |
|---|---|---|
| `REQ-01xx` | the pipeline and energy matching | [computation.md](computation.md) |
| `REQ-02xx` | the domain/API boundary | [interfaces.md](interfaces.md) |
| `REQ-03xx` | the external services | [interfaces.md](interfaces.md) |
| `REQ-04xx` | persistence | [persistence.md](persistence.md) |
| `REQ-05xx` | incentives and Italian regulation | [computation.md](computation.md) |
| `REQ-06xx` | finance | [computation.md](computation.md) |
| `REQ-07xx` | CAPEX estimation | [computation.md](computation.md) |
| `REQ-08xx` | configuration and load profiles | [computation.md](computation.md) |
| `REQ-09xx` | scenario comparison | [interfaces.md](interfaces.md) |
| `REQ-10xx` | the command line | [interfaces.md](interfaces.md) |

An identifier is never reused and never renumbered. A requirement that stops being true
is struck through here with the change that removed it, rather than deleted — the number
outlives the requirement so that a stale reference resolves to an explanation.

## How a requirement is verified

A test declares what it covers with a `@verifies REQ-####` tag **in the docstring of the
test class**, one requirement per class:

```python
class TestEnergyBalance:
    """@verifies REQ-0102"""
```

The class is the unit rather than the function because a requirement is normally worth
several assertions, and tagging each one restates the same fact many times. Where a class
genuinely covers two requirements, it carries two tags.

The trace matrix is the projection of this document and those tags — it is generated, not
maintained here. There is no hand-written coverage table in this repository and there
should not be one.

## What is knowingly not verified

Two things, both stated in the companion's testing playbook and neither fixable by a test:

- **A real PVGIS or Trentino Solar response.** Both services are mocked everywhere.
  `REQ-03xx` constrains what this repository sends and how it parses what it receives; it
  cannot notice the upstream changing. That is a monitoring problem, not a testing one.
- **Whether the Italian regulatory values are still correct.** IRPEF rates, RID tariffs,
  CER TIP durations and IVA treatment change by legislation, not by commit. `REQ-05xx`
  fixes the *shape* of each calculation — that the deduction runs ten years, that CER TIP
  stops after twenty, that self-consumption is untaxed. The *values* live in
  `config/*.yaml` and are checked against `docs/variables-reference.md` by a person.

## Requirements not currently met

**None.** Every requirement in this directory is verified by a test that passes.

Two were open when these documents were first written, and both were closed on
2026-08-15 — in opposite directions, which is worth keeping in view when the next one
comes up:

- **REQ-0305** was a defect. A Trentino response of the wrong shape leaked `KeyError` past
  the fallback and failed the request. Fixed in `trentino_solar.py` — the component that
  owns the response, not the one that consumes it.
- **REQ-0405** was not a defect. A configured-but-unreachable database stopping the
  service is the intended behaviour; the requirement was rewritten to say so, and the
  caller-facing message belongs to `../celine-frontend`.

A requirement that turns out to describe the wrong thing is rewritten. It is not deleted,
and its number is not reused.
