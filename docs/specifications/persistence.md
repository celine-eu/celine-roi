# Specifications — persistence

Storing computed estimates is the only thing this service does that is not a computation,
and it is **optional**. See [index.md](index.md) for what these requirements are and are
not.

Everything here is about what happens when the database is absent, unreachable or
misconfigured, because that is where the design intent lives. The happy path is the easy
part.

---

## REQ-04xx

### REQ-0401 — the service computes with no database

With persistence disabled, the application starts, serves its documentation, and answers
computation requests normally. No connection pool is created.

Persistence is a place to put results, not a dependency of producing them. A code path
that assumes a connection exists breaks this.

*Verified by* `tests/test_persistence_optional.py::TestServiceRunsWithoutADatabase`

### REQ-0402 — the retrieval endpoints degrade, they do not error

With persistence disabled, `GET /estimates` and `GET /estimates/{id}` return **503** with
a message saying persistence is not configured. Not 500, and not an empty 200 — a caller
must be able to tell "there is no store" from "the store is empty".

*Verified by* `tests/test_persistence_optional.py::TestRetrievalEndpointsDegradeCleanly`

### REQ-0403 — a failed write never fails the request that caused it

`scenario` and `compare` persist their results as background tasks. A write that raises
is logged and discarded; the caller still receives its result.

The consequence is deliberate and worth stating plainly: **a broken write shows up in the
logs, not in a response.** Nothing will page you.

*Verified by* `tests/test_persistence_optional.py::TestAFailedWriteDoesNotFailTheRequest`

### REQ-0404 — an unset `DATABASE_URL` selects the development default

`Settings.database_url` has a non-empty built-in default pointing at the local
development database, so a fresh checkout runs with nothing exported. Every deployment
overrides it through the environment.

The consequence is that there are **two knobs, not one**:

| Want | Set |
|---|---|
| a specific database | `DATABASE_URL=postgresql://…` |
| the dev default | leave it unset |
| **no persistence at all** | `DATABASE_URL=""` — the empty string, not unset |

This is worth stating because the code reads the other way round: the guard in
`init_pool` is `if not database_url`, which looks like "unset means off". It is not —
unset means *default*, and only the empty string means off.

The default's credentials are development ones, deliberately committed so the compose
stack works out of the box. They are not a secret and are not used anywhere real.

*Verified by* `tests/test_persistence_optional.py::TestUnsetIsNotTheSameAsDisabled`

### REQ-0405 — a configured but unreachable database is fatal at startup

If `DATABASE_URL` is set and nothing is listening, `init_pool()` raises inside the
lifespan and the service does not start. **This is intended**, and it is the one place
where "persistence is optional" stops applying.

The distinction is between not asking for a database and asking for one that is not
there:

| Situation | Outcome |
|---|---|
| no database configured (`DATABASE_URL=""`) | supported — REQ-0401 |
| a database configured but absent | the service refuses to start |

Starting anyway would mean serving normally while discarding every write, and REQ-0403
guarantees the caller is never told about a failed write. Failing at startup is what makes
that guarantee safe to give: a silent write failure is acceptable *because* a database
that was asked for is known to be there.

**The caller-facing side of this is not this repository's job.** A ROI service that is
down is handled by `../celine-frontend`, which shows a graceful message. Degrading here
would move that concern into the wrong component and hide the outage from the one that
can explain it.

*Verified by*
`tests/test_persistence_optional.py::TestAConfiguredButUnreachableDatabaseIsFatal`

### REQ-0406 — an estimate is retrievable exactly as it was stored

A saved estimate returns with its endpoint, status, request body, response body, duration
and creation time intact, including the JSON structure of the request and response. An
unknown identifier is a 404. A failed computation is stored too, with its error message
and a null response.

*Verified by* `tests/test_estimates.py::TestSaveEstimate`,
`tests/test_estimates.py::TestEstimatesAPI`

### REQ-0407 — listing is most-recent-first, filterable and paginated

The listing returns estimates newest first, can be filtered to one endpoint, and paginates
without repeating a row across pages.

*Verified by* `tests/test_estimates.py::TestListEstimates`

### REQ-0408 — the schema is owned by the migrations

The `estimates` table is created by the Alembic migrations, which are the only definition
of the schema that runs anywhere. The tests build their database by running them.

Two mechanisms coexist here and they are not interchangeable: the SQLAlchemy model in
`db.py` is the source Alembic autogenerates *from*, while queries at run time are
parameterised SQL through asyncpg. Neither carries a change across to the other. A test
fixture that built the schema from the model would pass while a broken migration shipped,
which is why it does not.

The migrated schema is checked against the model's columns and their nullability, so the
two cannot drift apart silently.

*Verified by* `tests/test_estimates.py::TestMigrationsMatchTheModel`

### ~~REQ-0409~~ — withdrawn

Allocated for "the persistence tests skip cleanly when there is no database", then
withdrawn: that is a property of the test suite, not of the service, and requirements
here describe the service. The rule itself still holds and is stated where it belongs, in
the companion's testing playbook.

The number is not reused.
