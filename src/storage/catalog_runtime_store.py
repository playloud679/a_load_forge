"""Catalog runtime store: trusted production driver catalog (lf-catalog-runtime)."""

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

logger = logging.getLogger("load_forge.storage.catalog_runtime")


class CatalogRuntimeStore(Protocol):
    """Protocol for trusted production driver catalog reads and promotion."""

    def get_driver(self, driver_id: str) -> dict[str, Any] | None: ...

    def search_drivers(
        self,
        query: str = "",
        brand: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]: ...

    def get_release_metadata(self, release_id: str | None = None) -> dict[str, Any] | None: ...

    def list_drivers(self, limit: int = 100) -> list[dict[str, Any]]: ...

    def promote_release(
        self,
        release_id: str,
        approved_by: str,
        drivers: Sequence[Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def rollback_release(
        self,
        target_release_id: str,
        rolled_back_by: str,
    ) -> dict[str, Any]: ...


class FirestoreCatalogRuntimeStore:
    """Production Firestore store strictly scoped to the lf-catalog-runtime database."""

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

    def get_driver(self, driver_id: str) -> dict[str, Any] | None:
        doc = self._client.collection("drivers").document(str(driver_id)).get()
        return doc.to_dict() if doc.exists else None

    def search_drivers(
        self,
        query: str = "",
        brand: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        collection = self._client.collection("drivers")
        results: list[dict[str, Any]] = []
        q = collection.limit(max(50, min(500, int(limit) * 3)))
        if brand.strip():
            q = collection.where("brand", "==", brand.strip())
        for doc in q.stream():
            data = doc.to_dict()
            if not data:
                continue
            if query.strip():
                name = str(data.get("name") or data.get("model") or "").casefold()
                brand_name = str(data.get("brand") or "").casefold()
                if query.casefold() not in name and query.casefold() not in brand_name:
                    continue
            results.append(data)
            if len(results) >= limit:
                break
        return results

    def get_release_metadata(self, release_id: str | None = None) -> dict[str, Any] | None:
        if release_id:
            doc = self._client.collection("releases").document(str(release_id)).get()
            return doc.to_dict() if doc.exists else None
        # Get active release
        doc = self._client.collection("catalog_metadata").document("active_release").get()
        if not doc.exists:
            return None
        active_info = doc.to_dict()
        active_id = str(active_info.get("release_id", ""))
        if not active_id:
            return active_info
        rel_doc = self._client.collection("releases").document(active_id).get()
        return rel_doc.to_dict() if rel_doc.exists else active_info

    def list_drivers(self, limit: int = 100) -> list[dict[str, Any]]:
        collection = self._client.collection("drivers")
        return [
            doc.to_dict()
            for doc in collection.limit(max(1, int(limit))).stream()
            if doc.exists
        ]

    def promote_release(
        self,
        release_id: str,
        approved_by: str,
        drivers: Sequence[Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Controlled promotion: writes versioned release metadata and driver documents."""
        now = datetime.now(timezone.utc).isoformat()
        rel_data = {
            "release_id": release_id,
            "approved_by": approved_by,
            "promoted_at": now,
            "driver_count": len(drivers),
            "metadata": dict(metadata or {}),
        }
        # Write release record
        self._client.collection("releases").document(release_id).set(rel_data)
        # Write drivers batch
        batch = self._client.batch()
        count = 0
        for item in drivers:
            driver_dict = dict(item)
            doc_id = str(driver_dict.get("id") or driver_dict.get("model") or f"drv_{count}")
            ref = self._client.collection("drivers").document(doc_id)
            batch.set(ref, driver_dict)
            count += 1
            if count % 450 == 0:
                batch.commit()
                batch = self._client.batch()
        batch.commit()
        # Set active release pointer
        self._client.collection("catalog_metadata").document("active_release").set({
            "release_id": release_id,
            "updated_at": now,
            "approved_by": approved_by,
            "driver_count": len(drivers),
        })
        logger.info(
            "Promoted catalog release release_id=%s approved_by=%s count=%d",
            release_id,
            approved_by,
            len(drivers),
        )
        return rel_data

    def rollback_release(
        self,
        target_release_id: str,
        rolled_back_by: str,
    ) -> dict[str, Any]:
        rel_doc = self._client.collection("releases").document(target_release_id).get()
        if not rel_doc.exists:
            raise saas.ProjectMissingError(f"Target release {target_release_id!r} was not found")
        rel_data = rel_doc.to_dict()
        now = datetime.now(timezone.utc).isoformat()
        self._client.collection("catalog_metadata").document("active_release").set({
            "release_id": target_release_id,
            "rolled_back_at": now,
            "rolled_back_by": rolled_back_by,
            "driver_count": rel_data.get("driver_count", 0),
        })
        logger.info(
            "Rolled back catalog to release_id=%s by=%s",
            target_release_id,
            rolled_back_by,
        )
        return rel_data


class InMemoryCatalogRuntimeStore:
    """In-memory runtime catalog store for unit testing."""

    def __init__(self) -> None:
        self._drivers: dict[str, dict[str, Any]] = {}
        self._releases: dict[str, dict[str, Any]] = {}
        self._active_release_id: str | None = None

    def get_driver(self, driver_id: str) -> dict[str, Any] | None:
        return self._drivers.get(driver_id)

    def search_drivers(
        self,
        query: str = "",
        brand: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for data in self._drivers.values():
            if brand.strip() and str(data.get("brand") or "").casefold() != brand.strip().casefold():
                continue
            if query.strip():
                name = str(data.get("name") or data.get("model") or "").casefold()
                b = str(data.get("brand") or "").casefold()
                if query.casefold() not in name and query.casefold() not in b:
                    continue
            results.append(data)
            if len(results) >= limit:
                break
        return results

    def get_release_metadata(self, release_id: str | None = None) -> dict[str, Any] | None:
        target_id = release_id or self._active_release_id
        if not target_id:
            return None
        return self._releases.get(target_id)

    def list_drivers(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(self._drivers.values())[: max(0, int(limit))]

    def promote_release(
        self,
        release_id: str,
        approved_by: str,
        drivers: Sequence[Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        rel_data = {
            "release_id": release_id,
            "approved_by": approved_by,
            "promoted_at": now,
            "driver_count": len(drivers),
            "metadata": dict(metadata or {}),
        }
        self._releases[release_id] = rel_data
        self._active_release_id = release_id
        for count, item in enumerate(drivers):
            driver_dict = dict(item)
            doc_id = str(driver_dict.get("id") or driver_dict.get("model") or f"drv_{count}")
            self._drivers[doc_id] = driver_dict
        return rel_data

    def rollback_release(
        self,
        target_release_id: str,
        rolled_back_by: str,
    ) -> dict[str, Any]:
        if target_release_id not in self._releases:
            raise saas.ProjectMissingError(f"Target release {target_release_id!r} was not found")
        self._active_release_id = target_release_id
        rel_data = self._releases[target_release_id]
        return rel_data


_SHARED_MEMORY_CATALOG_RUNTIME_STORE: InMemoryCatalogRuntimeStore | None = None


def get_shared_memory_catalog_runtime_store() -> InMemoryCatalogRuntimeStore:
    global _SHARED_MEMORY_CATALOG_RUNTIME_STORE
    if _SHARED_MEMORY_CATALOG_RUNTIME_STORE is None:
        _SHARED_MEMORY_CATALOG_RUNTIME_STORE = InMemoryCatalogRuntimeStore()
    return _SHARED_MEMORY_CATALOG_RUNTIME_STORE


def create_catalog_runtime_store(
    settings: saas.SaaSSettings | None = None,
) -> CatalogRuntimeStore:
    if settings is None or settings.backend == "memory" or not settings.enabled:
        return get_shared_memory_catalog_runtime_store()
    return FirestoreCatalogRuntimeStore(
        project=settings.gcp_project,
        database=settings.firestore_catalog_runtime_db,
    )
