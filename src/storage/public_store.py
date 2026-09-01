"""Public domain store: community publications and versions (lf-public)."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Protocol

try:
    import saas
    from storage._firestore_client import get_firestore_client
    from storage.private_store import PrivateStore
except ImportError:
    from src import saas  # type: ignore[no-redef]
    from src.storage._firestore_client import get_firestore_client  # type: ignore[no-redef]
    from src.storage.private_store import PrivateStore  # type: ignore[no-redef]

logger = logging.getLogger("load_forge.storage.public")


class PublicStore(Protocol):
    """Protocol for public project catalog and version operations."""

    def publish_project(
        self,
        user: saas.SaaSUser,
        project_id: str,
        parameters: Mapping[str, Any],
        *,
        title: str,
        description: str = "",
        visibility: str = "unlisted",
        app_version: str,
        publication_id: str | None = None,
        source_revision: int = 1,
    ) -> saas.PublicProjectRecord: ...

    def get_public_project(self, publication_id: str) -> saas.PublicProjectRecord | None: ...

    def get_public_project_version(
        self, publication_id: str, version: int
    ) -> saas.PublicProjectVersion | None: ...

    def list_public_projects(
        self,
        *,
        query: str = "",
        topology: str = "",
        min_vb: float | None = None,
        max_vb: float | None = None,
        min_f3: float | None = None,
        max_f3: float | None = None,
        min_tuning_hz: float | None = None,
        max_tuning_hz: float | None = None,
        min_driver_size_in: float | None = None,
        max_driver_size_in: float | None = None,
        min_fs_hz: float | None = None,
        max_fs_hz: float | None = None,
        min_qts: float | None = None,
        max_qts: float | None = None,
        sort_by: str = "newest",
        limit: int = 50,
    ) -> list[saas.PublicProjectSummary]: ...

    def clone_public_project(
        self,
        user: saas.SaaSUser,
        publication_id: str,
        app_version: str,
        *,
        private_store: PrivateStore,
        version: int | None = None,
        new_name: str | None = None,
    ) -> saas.ProjectRecord: ...


class FirestorePublicStore:
    """Production Firestore store strictly scoped to the lf-public database."""

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

    def _public_project_ref(self, publication_id: str):
        return self._client.collection("public_projects").document(
            saas._validate_publication_id(publication_id)
        )

    def publish_project(
        self,
        user: saas.SaaSUser,
        project_id: str,
        parameters: Mapping[str, Any],
        *,
        title: str,
        description: str = "",
        visibility: str = "unlisted",
        app_version: str,
        publication_id: str | None = None,
        source_revision: int = 1,
    ) -> saas.PublicProjectRecord:
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise saas.SaaSConfigurationError(
                "google-cloud-firestore is required for the Firestore backend"
            ) from exc

        pub_title = saas._normalize_publication_title(title)
        pub_desc = saas._normalize_publication_description(description)
        norm_vis = str(visibility).strip().casefold()
        if norm_vis not in saas._PUBLICATION_VISIBILITIES:
            raise ValueError(f"Invalid visibility: {visibility}")
        pub_id = saas._validate_publication_id(publication_id or saas.new_publication_id())
        ref = self._public_project_ref(pub_id)
        transaction = self._client.transaction()
        now = firestore.SERVER_TIMESTAMP
        tech_summary = saas.extract_technical_summary(parameters)
        content_hash = saas.project_content_hash(pub_title, parameters)

        @firestore.transactional
        def do_publish(tx):
            snap = ref.get(transaction=tx)
            existing = snap.to_dict() if snap.exists else None
            if existing:
                if str(existing.get("owner_uid")) != user.uid:
                    raise saas.ProjectAccessError("Publication belongs to another user")
                pub_version = int(existing.get("publication_version", 1)) + 1
                created_at = existing.get("created_at") or now
            else:
                pub_version = 1
                created_at = now

            version_id = f"v_{pub_version:010d}"
            version_ref = ref.collection("versions").document(version_id)
            version_data = {
                "publication_id": pub_id,
                "version": pub_version,
                "version_id": version_id,
                "title": pub_title,
                "description": pub_desc,
                "content_hash": content_hash,
                "source_revision": source_revision,
                "published_at": now,
                "technical_summary": tech_summary,
                "parameters": parameters,
            }
            pub_data = {
                "publication_id": pub_id,
                "owner_uid": user.uid,
                "owner_display_name": user.name or user.email,
                "source_tenant_id": user.tenant_id,
                "source_project_id": project_id,
                "source_revision": source_revision,
                "publication_version": pub_version,
                "visibility": norm_vis,
                "title": pub_title,
                "description": pub_desc,
                "schema_version": saas.PUBLICATION_SCHEMA_VERSION,
                "app_version": str(app_version),
                "created_at": created_at,
                "updated_at": now,
                "published_at": now,
                "technical_summary": tech_summary,
                "provenance": {
                    "source_project_id": project_id,
                    "source_revision": source_revision,
                },
                "parameters": parameters,
            }
            tx.set(version_ref, version_data)
            tx.set(ref, pub_data)
            return True

        do_publish(transaction)
        saved = ref.get()
        if not saved.exists:
            raise saas.ProjectMissingError("Publication was not found after save")
        return saas._public_record_from_document(pub_id, saved.to_dict())

    def get_public_project(self, publication_id: str) -> saas.PublicProjectRecord | None:
        pub_id = saas._validate_publication_id(publication_id)
        snap = self._public_project_ref(pub_id).get()
        if not snap.exists:
            for showcase in saas.curated_community_showcase_projects():
                if showcase.publication_id == pub_id:
                    return showcase
            return None
        return saas._public_record_from_document(pub_id, snap.to_dict())

    def get_public_project_version(
        self, publication_id: str, version: int
    ) -> saas.PublicProjectVersion | None:
        pub_id = saas._validate_publication_id(publication_id)
        version_id = f"v_{int(version):010d}"
        snap = self._public_project_ref(pub_id).collection("versions").document(version_id).get()
        if not snap.exists:
            for showcase in saas.curated_community_showcase_projects():
                if showcase.publication_id == pub_id:
                    return saas.PublicProjectVersion(
                        publication_id=pub_id,
                        version=1,
                        version_id="v_0000000001",
                        title=showcase.title,
                        description=showcase.description,
                        content_hash="",
                        source_revision=1,
                        published_at=showcase.published_at,
                        technical_summary=showcase.technical_summary,
                        parameters=showcase.parameters,
                    )
            return None
        return saas._public_version_from_document(pub_id, snap.to_dict())

    def list_public_projects(
        self,
        *,
        query: str = "",
        topology: str = "",
        min_vb: float | None = None,
        max_vb: float | None = None,
        min_f3: float | None = None,
        max_f3: float | None = None,
        min_tuning_hz: float | None = None,
        max_tuning_hz: float | None = None,
        min_driver_size_in: float | None = None,
        max_driver_size_in: float | None = None,
        min_fs_hz: float | None = None,
        max_fs_hz: float | None = None,
        min_qts: float | None = None,
        max_qts: float | None = None,
        sort_by: str = "newest",
        limit: int = 50,
    ) -> list[saas.PublicProjectSummary]:
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise saas.SaaSConfigurationError(
                "google-cloud-firestore is required for the Firestore backend"
            ) from exc

        fetch_limit = max(50, min(500, int(limit) * 4))
        results = []
        snaps = []
        try:
            fs_query = (
                self._client.collection("public_projects")
                .where("visibility", "==", "public")
                .order_by("published_at", direction=firestore.Query.DESCENDING)
                .limit(fetch_limit)
            )
            snaps = list(fs_query.stream())
        except Exception as exc:
            logger.warning("Ordered public projects query failed, falling back to unordered stream: %s", exc)
            try:
                fs_query = (
                    self._client.collection("public_projects")
                    .where("visibility", "==", "public")
                    .limit(fetch_limit)
                )
                snaps = list(fs_query.stream())
            except Exception as inner_exc:
                logger.warning("Filtered public query failed, querying limit stream: %s", inner_exc)
                try:
                    snaps = list(self._client.collection("public_projects").limit(fetch_limit).stream())
                except Exception as final_exc:
                    logger.error("Failed to stream public projects: %s", final_exc)
                    snaps = []

        for snap in snaps:
            try:
                rec = saas._public_record_from_document(snap.id, snap.to_dict())
                if rec.visibility == "public":
                    results.append(saas.PublicProjectSummary(**{
                        field: getattr(rec, field)
                        for field in saas.PublicProjectSummary.__dataclass_fields__
                    }))
            except Exception as exc:
                logger.warning("Skipping malformed public project %s: %s", snap.id, exc)

        if not results:
            showcases = saas.curated_community_showcase_projects()
            results = [
                saas.PublicProjectSummary(**{
                    field: getattr(rec, field)
                    for field in saas.PublicProjectSummary.__dataclass_fields__
                })
                for rec in showcases
            ]

        return saas._filter_and_sort_public_projects(
            results,
            query=query,
            topology=topology,
            min_vb=min_vb,
            max_vb=max_vb,
            min_f3=min_f3,
            max_f3=max_f3,
            min_tuning_hz=min_tuning_hz,
            max_tuning_hz=max_tuning_hz,
            min_driver_size_in=min_driver_size_in,
            max_driver_size_in=max_driver_size_in,
            min_fs_hz=min_fs_hz,
            max_fs_hz=max_fs_hz,
            min_qts=min_qts,
            max_qts=max_qts,
            sort_by=sort_by,
            limit=limit,
        )

    def clone_public_project(
        self,
        user: saas.SaaSUser,
        publication_id: str,
        app_version: str,
        *,
        private_store: PrivateStore,
        version: int | None = None,
        new_name: str | None = None,
    ) -> saas.ProjectRecord:
        """Explicit cross-domain clone operation: reads from public store, saves to private store."""
        pub = self.get_public_project(publication_id)
        if pub is None:
            raise saas.ProjectMissingError("Public project not found")
        if version is not None:
            target_version = self.get_public_project_version(publication_id, version)
            if target_version is None:
                raise saas.ProjectMissingError("Public project version not found")
            source_params = target_version.parameters
            source_version_num = target_version.version
            title_to_use = target_version.title
        else:
            source_params = pub.parameters
            source_version_num = pub.publication_version
            title_to_use = pub.title

        clone_name = new_name or f"{title_to_use} (Clone)"
        cloned_params = json.loads(json.dumps(source_params, allow_nan=False))
        if "project" in cloned_params and isinstance(cloned_params["project"], dict):
            cloned_params["project"]["name"] = saas._normalize_project_name(clone_name)
            cloned_params["project"]["provenance"] = {
                "source_publication_id": publication_id,
                "source_publication_version": source_version_num,
                "original_author_uid": pub.owner_uid,
                "original_author_name": pub.owner_display_name,
                "cloned_at": datetime.now(timezone.utc).isoformat(),
            }
        return private_store.save_project(
            user,
            clone_name,
            cloned_params,
            app_version,
            project_id=saas.new_project_id(),
            expected_revision=0,
        )


class InMemoryPublicStore:
    """In-memory public store for unit tests and local development."""

    def __init__(self) -> None:
        self._public_projects: dict[str, saas.PublicProjectRecord] = {}
        self._public_versions: dict[str, list[saas.PublicProjectVersion]] = {}

    def publish_project(
        self,
        user: saas.SaaSUser,
        project_id: str,
        parameters: Mapping[str, Any],
        *,
        title: str,
        description: str = "",
        visibility: str = "unlisted",
        app_version: str,
        publication_id: str | None = None,
        source_revision: int = 1,
    ) -> saas.PublicProjectRecord:
        pub_title = saas._normalize_publication_title(title)
        pub_desc = saas._normalize_publication_description(description)
        norm_vis = str(visibility).strip().casefold()
        if norm_vis not in saas._PUBLICATION_VISIBILITIES:
            raise ValueError(f"Invalid visibility: {visibility}")
        pub_id = saas._validate_publication_id(publication_id or saas.new_publication_id())
        now = datetime.now(timezone.utc)
        existing = self._public_projects.get(pub_id)
        if existing:
            if existing.owner_uid != user.uid:
                raise saas.ProjectAccessError("Publication belongs to another user")
            pub_version = existing.publication_version + 1
            created_at = existing.created_at
        else:
            pub_version = 1
            created_at = now

        content_hash = saas.project_content_hash(pub_title, parameters)
        tech_summary = saas.extract_technical_summary(parameters)
        record = saas.PublicProjectRecord(
            publication_id=pub_id,
            owner_uid=user.uid,
            owner_display_name=user.name or user.email,
            source_tenant_id=user.tenant_id,
            source_project_id=project_id,
            source_revision=source_revision,
            publication_version=pub_version,
            visibility=norm_vis,
            title=pub_title,
            description=pub_desc,
            schema_version=saas.PUBLICATION_SCHEMA_VERSION,
            app_version=str(app_version),
            created_at=created_at,
            updated_at=now,
            published_at=now,
            technical_summary=tech_summary,
            provenance={
                "source_project_id": project_id,
                "source_revision": source_revision,
            },
            parameters=json.loads(json.dumps(parameters, allow_nan=False)),
        )
        self._public_projects[pub_id] = record
        versions = self._public_versions.setdefault(pub_id, [])
        version_id = f"v_{pub_version:010d}"
        versions.append(saas.PublicProjectVersion(
            publication_id=pub_id,
            version=pub_version,
            version_id=version_id,
            title=pub_title,
            description=pub_desc,
            content_hash=content_hash,
            source_revision=source_revision,
            published_at=now,
            technical_summary=tech_summary,
            parameters=json.loads(json.dumps(parameters, allow_nan=False)),
        ))
        return record

    def get_public_project(self, publication_id: str) -> saas.PublicProjectRecord | None:
        pub_id = saas._validate_publication_id(publication_id)
        if pub_id in self._public_projects:
            return self._public_projects[pub_id]
        for showcase in saas.curated_community_showcase_projects():
            if showcase.publication_id == pub_id:
                return showcase
        return None

    def get_public_project_version(
        self, publication_id: str, version: int
    ) -> saas.PublicProjectVersion | None:
        pub_id = saas._validate_publication_id(publication_id)
        versions = self._public_versions.get(pub_id, [])
        found = next((v for v in versions if v.version == int(version)), None)
        if found is not None:
            return found
        for showcase in saas.curated_community_showcase_projects():
            if showcase.publication_id == pub_id:
                return saas.PublicProjectVersion(
                    publication_id=pub_id,
                    version=1,
                    version_id="v_0000000001",
                    title=showcase.title,
                    description=showcase.description,
                    content_hash="",
                    source_revision=1,
                    published_at=showcase.published_at,
                    technical_summary=showcase.technical_summary,
                    parameters=showcase.parameters,
                )
        return None

    def list_public_projects(
        self,
        *,
        query: str = "",
        topology: str = "",
        min_vb: float | None = None,
        max_vb: float | None = None,
        min_f3: float | None = None,
        max_f3: float | None = None,
        min_tuning_hz: float | None = None,
        max_tuning_hz: float | None = None,
        min_driver_size_in: float | None = None,
        max_driver_size_in: float | None = None,
        min_fs_hz: float | None = None,
        max_fs_hz: float | None = None,
        min_qts: float | None = None,
        max_qts: float | None = None,
        sort_by: str = "newest",
        limit: int = 50,
    ) -> list[saas.PublicProjectSummary]:
        summaries = [
            saas.PublicProjectSummary(**{
                field: getattr(rec, field)
                for field in saas.PublicProjectSummary.__dataclass_fields__
            })
            for rec in self._public_projects.values()
            if rec.visibility == "public"
        ]
        if not summaries:
            showcases = saas.curated_community_showcase_projects()
            summaries = [
                saas.PublicProjectSummary(**{
                    field: getattr(rec, field)
                    for field in saas.PublicProjectSummary.__dataclass_fields__
                })
                for rec in showcases
            ]
        return saas._filter_and_sort_public_projects(
            summaries,
            query=query,
            topology=topology,
            min_vb=min_vb,
            max_vb=max_vb,
            min_f3=min_f3,
            max_f3=max_f3,
            min_tuning_hz=min_tuning_hz,
            max_tuning_hz=max_tuning_hz,
            min_driver_size_in=min_driver_size_in,
            max_driver_size_in=max_driver_size_in,
            min_fs_hz=min_fs_hz,
            max_fs_hz=max_fs_hz,
            min_qts=min_qts,
            max_qts=max_qts,
            sort_by=sort_by,
            limit=limit,
        )

    def clone_public_project(
        self,
        user: saas.SaaSUser,
        publication_id: str,
        app_version: str,
        *,
        private_store: PrivateStore,
        version: int | None = None,
        new_name: str | None = None,
    ) -> saas.ProjectRecord:
        pub = self.get_public_project(publication_id)
        if pub is None:
            raise saas.ProjectMissingError("Public project not found")
        if version is not None:
            target_version = self.get_public_project_version(publication_id, version)
            if target_version is None:
                raise saas.ProjectMissingError("Public project version not found")
            source_params = target_version.parameters
            source_version_num = target_version.version
            title_to_use = target_version.title
        else:
            source_params = pub.parameters
            source_version_num = pub.publication_version
            title_to_use = pub.title

        clone_name = new_name or f"{title_to_use} (Clone)"
        cloned_params = json.loads(json.dumps(source_params, allow_nan=False))
        if "project" in cloned_params and isinstance(cloned_params["project"], dict):
            cloned_params["project"]["name"] = saas._normalize_project_name(clone_name)
            cloned_params["project"]["provenance"] = {
                "source_publication_id": publication_id,
                "source_publication_version": source_version_num,
                "original_author_uid": pub.owner_uid,
                "original_author_name": pub.owner_display_name,
                "cloned_at": datetime.now(timezone.utc).isoformat(),
            }
        return private_store.save_project(
            user,
            clone_name,
            cloned_params,
            app_version,
            project_id=saas.new_project_id(),
            expected_revision=0,
        )


_SHARED_MEMORY_PUBLIC_STORE: InMemoryPublicStore | None = None


def get_shared_memory_public_store() -> InMemoryPublicStore:
    global _SHARED_MEMORY_PUBLIC_STORE
    if _SHARED_MEMORY_PUBLIC_STORE is None:
        _SHARED_MEMORY_PUBLIC_STORE = InMemoryPublicStore()
    return _SHARED_MEMORY_PUBLIC_STORE


def create_public_store(settings: saas.SaaSSettings) -> PublicStore:
    """Create a public store bound to the configured public database."""
    if settings.backend == "memory" or not settings.enabled:
        return get_shared_memory_public_store()
    return FirestorePublicStore(
        project=settings.gcp_project,
        database=settings.firestore_public_db,
    )
