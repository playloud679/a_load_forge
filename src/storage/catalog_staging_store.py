"""Catalog staging store: untrusted crawler ingestion workspace (lf-catalog-staging)."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Protocol

try:
    import saas
    from storage._firestore_client import get_firestore_client
except ImportError:
    from src import saas  # type: ignore[no-redef]
    from src.storage._firestore_client import get_firestore_client  # type: ignore[no-redef]

logger = logging.getLogger("load_forge.storage.catalog_staging")


class CatalogStagingStore(Protocol):
    """Protocol for untrusted crawler staging ingestion operations."""

    def save_candidate(
        self,
        run_id: str,
        target_id: str,
        candidate_data: Mapping[str, Any],
    ) -> str: ...

    def save_ingestion_run(
        self,
        run_id: str,
        plan_metadata: Mapping[str, Any],
        results: Sequence[Mapping[str, Any]],
        report_metadata: Mapping[str, Any] | None = None,
    ) -> str: ...

    def get_run(self, run_id: str) -> dict[str, Any] | None: ...

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]: ...

    def get_candidates_for_run(self, run_id: str) -> list[dict[str, Any]]: ...

    def save_validation_result(
        self,
        run_id: str,
        target_id: str,
        result_data: Mapping[str, Any],
    ) -> str: ...

    def save_rejected_record(
        self,
        run_id: str,
        record_data: Mapping[str, Any],
        reason: str,
    ) -> str: ...


class FirestoreCatalogStagingStore:
    """Production Firestore store strictly scoped to the lf-catalog-staging database."""

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str = "(default)",
        client: Any | None = None,
    ) -> None:
        self._database = database
        self._client = get_firestore_client(project=project, database=database, client=client)

    @property
    def database_name(self) -> str:
        return self._database

    def save_candidate(
        self,
        run_id: str,
        target_id: str,
        candidate_data: Mapping[str, Any],
    ) -> str:
        now = datetime.now(timezone.utc).isoformat()
        data = dict(candidate_data)
        data.update({
            "run_id": run_id,
            "target_id": target_id,
            "staged_at": now,
        })
        doc_ref = self._client.collection("catalog_candidates").document()
        doc_ref.set(data)
        return doc_ref.id

    def save_ingestion_run(
        self,
        run_id: str,
        plan_metadata: Mapping[str, Any],
        results: Sequence[Mapping[str, Any]],
        report_metadata: Mapping[str, Any] | None = None,
    ) -> str:
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "run_id": run_id,
            "created_at": now,
            "plan": dict(plan_metadata),
            "results": [dict(r) for r in results],
            "report": dict(report_metadata or {}),
            "publication_state": "staging_only",
        }
        self._client.collection("ingestion_runs").document(run_id).set(payload)
        logger.info("Saved ingestion run run_id=%s targets=%d", run_id, len(results))
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        doc = self._client.collection("ingestion_runs").document(run_id).get()
        return doc.to_dict() if doc.exists else None

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        collection = self._client.collection("ingestion_runs")
        return [
            doc.to_dict()
            for doc in collection.limit(max(1, int(limit))).stream()
            if doc.exists
        ]

    def get_candidates_for_run(self, run_id: str) -> list[dict[str, Any]]:
        query = (
            self._client.collection("catalog_candidates")
            .where("run_id", "==", run_id)
        )
        return [doc.to_dict() for doc in query.stream() if doc.exists]

    def save_validation_result(
        self,
        run_id: str,
        target_id: str,
        result_data: Mapping[str, Any],
    ) -> str:
        doc_id = f"{run_id}_{target_id}"
        self._client.collection("validation_results").document(doc_id).set(dict(result_data))
        return doc_id

    def save_rejected_record(
        self,
        run_id: str,
        record_data: Mapping[str, Any],
        reason: str,
    ) -> str:
        doc_ref = self._client.collection("rejected_records").document()
        doc_ref.set({
            "run_id": run_id,
            "reason": reason,
            "rejected_at": datetime.now(timezone.utc).isoformat(),
            "record": dict(record_data),
        })
        return doc_ref.id


class InMemoryCatalogStagingStore:
    """In-memory staging store for unit testing."""

    def __init__(self) -> None:
        self._candidates: list[dict[str, Any]] = []
        self._runs: dict[str, dict[str, Any]] = {}
        self._validation_results: dict[str, dict[str, Any]] = {}
        self._rejected: list[dict[str, Any]] = []

    def save_candidate(
        self,
        run_id: str,
        target_id: str,
        candidate_data: Mapping[str, Any],
    ) -> str:
        data = dict(candidate_data)
        data.update({
            "run_id": run_id,
            "target_id": target_id,
            "staged_at": datetime.now(timezone.utc).isoformat(),
        })
        self._candidates.append(data)
        return f"cand_{len(self._candidates)}"

    def save_ingestion_run(
        self,
        run_id: str,
        plan_metadata: Mapping[str, Any],
        results: Sequence[Mapping[str, Any]],
        report_metadata: Mapping[str, Any] | None = None,
    ) -> str:
        payload = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "plan": dict(plan_metadata),
            "results": [dict(r) for r in results],
            "report": dict(report_metadata or {}),
            "publication_state": "staging_only",
        }
        self._runs[run_id] = payload
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._runs.get(run_id)

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return list(self._runs.values())[: max(0, int(limit))]

    def get_candidates_for_run(self, run_id: str) -> list[dict[str, Any]]:
        return [c for c in self._candidates if c.get("run_id") == run_id]

    def save_validation_result(
        self,
        run_id: str,
        target_id: str,
        result_data: Mapping[str, Any],
    ) -> str:
        doc_id = f"{run_id}_{target_id}"
        self._validation_results[doc_id] = dict(result_data)
        return doc_id

    def save_rejected_record(
        self,
        run_id: str,
        record_data: Mapping[str, Any],
        reason: str,
    ) -> str:
        self._rejected.append({
            "run_id": run_id,
            "reason": reason,
            "rejected_at": datetime.now(timezone.utc).isoformat(),
            "record": dict(record_data),
        })
        return f"rej_{len(self._rejected)}"


_SHARED_MEMORY_CATALOG_STAGING_STORE: InMemoryCatalogStagingStore | None = None


def get_shared_memory_catalog_staging_store() -> InMemoryCatalogStagingStore:
    global _SHARED_MEMORY_CATALOG_STAGING_STORE
    if _SHARED_MEMORY_CATALOG_STAGING_STORE is None:
        _SHARED_MEMORY_CATALOG_STAGING_STORE = InMemoryCatalogStagingStore()
    return _SHARED_MEMORY_CATALOG_STAGING_STORE


def create_catalog_staging_store(
    settings: saas.SaaSSettings | None = None,
) -> CatalogStagingStore:
    if settings is None or settings.backend == "memory" or not settings.enabled:
        return get_shared_memory_catalog_staging_store()
    return FirestoreCatalogStagingStore(
        project=settings.gcp_project,
        database=settings.firestore_catalog_staging_db,
    )
