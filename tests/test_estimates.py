"""Tests for the estimates persistence layer."""

from __future__ import annotations

import os
import uuid

import pytest

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://celine:celine@localhost:25432/celine",
)

try:
    import asyncpg  # noqa: F401
except ImportError:
    pytest.skip("asyncpg not installed", allow_module_level=True)


@pytest.fixture()
async def pool():
    """Create a temporary asyncpg pool for testing."""
    try:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    except (OSError, asyncpg.PostgresError):
        pytest.skip("Postgres not reachable")
    async with _pool.acquire() as conn:
        await conn.execute(
            (
                __import__("pathlib").Path(__file__).parent.parent / "sql" / "init.sql"
            ).read_text()
        )
    yield _pool
    await _pool.close()


class TestSaveEstimate:
    async def test_save_and_retrieve_scenario(self, pool) -> None:
        from celine.roi.api.database import save_estimate, get_estimate

        request_data = {"system": {"kwp": 10, "latitude": 46.0}}
        response_data = {"summary": {"npv_eur": 5000}}

        estimate_id = await save_estimate(
            pool=pool,
            endpoint="scenario",
            status="success",
            request=request_data,
            response=response_data,
            duration_ms=1234,
        )

        assert isinstance(estimate_id, uuid.UUID)

        record = await get_estimate(pool, estimate_id)
        assert record is not None
        assert record["endpoint"] == "scenario"
        assert record["status"] == "success"
        assert record["request"] == request_data
        assert record["response"] == response_data
        assert record["duration_ms"] == 1234
        assert record["created_at"] is not None

    async def test_save_error_estimate(self, pool) -> None:
        from celine.roi.api.database import save_estimate, get_estimate

        estimate_id = await save_estimate(
            pool=pool,
            endpoint="scenario",
            status="error",
            request={"system": {"kwp": 10}},
            response=None,
            duration_ms=50,
            error_message="PVGIS unreachable",
        )

        record = await get_estimate(pool, estimate_id)
        assert record["status"] == "error"
        assert record["response"] is None
        assert record["error_message"] == "PVGIS unreachable"

    async def test_get_nonexistent_returns_none(self, pool) -> None:
        from celine.roi.api.database import get_estimate

        record = await get_estimate(pool, uuid.uuid4())
        assert record is None


class TestListEstimates:
    async def test_list_returns_recent_first(self, pool) -> None:
        from celine.roi.api.database import save_estimate, list_estimates

        ids = []
        for idx in range(3):
            eid = await save_estimate(
                pool=pool,
                endpoint="scenario",
                status="success",
                request={"idx": idx},
                response={"summary": {"npv_eur": idx * 1000}},
                duration_ms=100,
            )
            ids.append(eid)

        result = await list_estimates(pool, limit=3, offset=0)
        assert result["total"] >= 3
        assert len(result["items"]) >= 3
        returned_ids = [item["id"] for item in result["items"]]
        assert returned_ids.index(ids[2]) < returned_ids.index(ids[0])

    async def test_list_filter_by_endpoint(self, pool) -> None:
        from celine.roi.api.database import save_estimate, list_estimates

        await save_estimate(
            pool=pool,
            endpoint="compare",
            status="success",
            request={"test": "filter"},
            response={"summary_table": "..."},
            duration_ms=200,
        )

        result = await list_estimates(pool, limit=100, offset=0, endpoint="compare")
        assert result["total"] >= 1
        assert all(item["endpoint"] == "compare" for item in result["items"])

    async def test_list_pagination(self, pool) -> None:
        from celine.roi.api.database import list_estimates

        page1 = await list_estimates(pool, limit=2, offset=0)
        page2 = await list_estimates(pool, limit=2, offset=2)
        if page1["total"] >= 4:
            ids1 = {item["id"] for item in page1["items"]}
            ids2 = {item["id"] for item in page2["items"]}
            assert ids1.isdisjoint(ids2)
