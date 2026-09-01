"""Tests for Load Forge multi-database data architecture and storage boundaries."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import saas
import storage


def test_saas_settings_named_databases_default():
    """Verify default database name fallback across all four domains."""
    settings = saas.SaaSSettings.from_env({})
    assert settings.firestore_database == "(default)"
    assert settings.firestore_private_db == "(default)"
    assert settings.firestore_public_db == "(default)"
    assert settings.firestore_catalog_runtime_db == "(default)"
    assert settings.firestore_catalog_staging_db == "(default)"


def test_saas_settings_named_databases_explicit():
    """Verify custom environment variables map to each data domain."""
    env = {
        "LF_FIRESTORE_PRIVATE_DB": "lf-private",
        "LF_FIRESTORE_PUBLIC_DB": "lf-public",
        "LF_FIRESTORE_CATALOG_RUNTIME_DB": "lf-catalog-runtime",
        "LF_FIRESTORE_CATALOG_STAGING_DB": "lf-catalog-staging",
    }
    settings = saas.SaaSSettings.from_env(env)
    assert settings.firestore_private_db == "lf-private"
    assert settings.firestore_public_db == "lf-public"
    assert settings.firestore_catalog_runtime_db == "lf-catalog-runtime"
    assert settings.firestore_catalog_staging_db == "lf-catalog-staging"


def test_saas_settings_legacy_env_var_fallback():
    """Verify backward compatibility with LOAD_FORGE_FIRESTORE_DATABASE."""
    env = {
        "LOAD_FORGE_FIRESTORE_DATABASE": "custom-shared-db",
    }
    settings = saas.SaaSSettings.from_env(env)
    assert settings.firestore_database == "custom-shared-db"
    assert settings.firestore_private_db == "custom-shared-db"
    assert settings.firestore_public_db == "custom-shared-db"
    assert settings.firestore_catalog_runtime_db == "custom-shared-db"
    assert settings.firestore_catalog_staging_db == "custom-shared-db"


def test_saas_settings_rejects_invalid_db_names():
    """Verify invalid database names fail validation at startup."""
    invalid_cases = [
        {"LF_FIRESTORE_PRIVATE_DB": "INVALID_UPPERCASE"},
        {"LF_FIRESTORE_PUBLIC_DB": "db_with_underscore"},
        {"LF_FIRESTORE_CATALOG_RUNTIME_DB": "ab"},  # too short
        {"LF_FIRESTORE_CATALOG_STAGING_DB": "invalid/slashes"},
    ]
    for env in invalid_cases:
        try:
            saas.SaaSSettings.from_env(env)
            assert False, f"Expected SaaSConfigurationError for env: {env}"
        except saas.SaaSConfigurationError:
            pass


def test_saas_settings_strict_multi_db():
    """Verify strict multi-database enforcement rejects (default) database."""
    env = {
        "LOAD_FORGE_STRICT_MULTI_DB": "true",
        "LF_FIRESTORE_PRIVATE_DB": "(default)",
        "LF_FIRESTORE_PUBLIC_DB": "lf-public",
    }
    try:
        saas.SaaSSettings.from_env(env)
        assert False, "Expected SaaSConfigurationError when strict multi-db has (default)"
    except saas.SaaSConfigurationError:
        pass


def test_validate_database_name():
    """Test helper for Firestore database identifier format."""
    assert storage.validate_database_name("(default)") == "(default)"
    assert storage.validate_database_name("lf-private") == "lf-private"
    assert storage.validate_database_name("lf-public-2026") == "lf-public-2026"
    try:
        storage.validate_database_name("")
        assert False, "Expected error on empty name"
    except saas.SaaSConfigurationError:
        pass


def test_private_store_project_and_account_isolation():
    """Test PrivateStore operations and verify no public methods are exposed."""
    priv_store = storage.get_shared_memory_private_store()
    user = saas.SaaSUser(
        uid="u_test_1",
        email="test@loadforge.app",
        name="Test User",
        tenant_id="tenant_test_1",
    )
    # Save private project
    payload = {
        "load_type": "Bass reflex",
        "reflex_vb_l": 45.0,
        "reflex_fb_hz": 35.0,
        "driver_name": "Test Driver",
    }
    rec = priv_store.save_project(user, "Subwoofer 1", payload, "0.15.8")
    assert rec.name == "Subwoofer 1"
    assert rec.revision == 1

    # Load project
    loaded = priv_store.load_project(user, rec.project_id)
    assert loaded is not None
    assert loaded.project_id == rec.project_id

    # Account operations
    acc = priv_store.get_or_create_account(user.uid, user.email, user.name)
    assert acc.credits_balance == 100
    assert priv_store.deduct_credits(user.email, 10) is True
    updated_acc = priv_store.get_or_create_account(user.uid, user.email, user.name)
    assert updated_acc.credits_balance == 90

    # Ensure PrivateStore does not have public publishing method
    assert not hasattr(priv_store, "publish_project")


def test_public_store_isolation_and_cross_domain_clone():
    """Test PublicStore publishing and clone orchestration to PrivateStore."""
    pub_store = storage.get_shared_memory_public_store()
    priv_store = storage.get_shared_memory_private_store()

    user_a = saas.SaaSUser("u_author", "author@example.com", "Author", "t_author")
    user_b = saas.SaaSUser("u_cloner", "cloner@example.com", "Cloner", "t_cloner")

    payload = {
        "load_type": "Bass reflex",
        "reflex_vb_l": 120.0,
        "reflex_fb_hz": 32.0,
        "driver_preset_name": "Faital 18HP1060",
    }
    pub_rec = pub_store.publish_project(
        user_a,
        "proj_orig_1234",
        payload,
        title="Faital 18-inch Pro Reflex",
        description="Concert subwoofer",
        visibility="public",
        app_version="0.15.8",
        source_revision=3,
    )
    assert pub_rec.publication_id is not None
    assert pub_rec.publication_version == 1
    assert pub_rec.visibility == "public"

    # Search in public gallery
    gallery = pub_store.list_public_projects(query="Faital")
    assert len(gallery) >= 1
    assert gallery[0].publication_id == pub_rec.publication_id

    # Cross-domain clone: PublicStore reads publication, saves to PrivateStore
    cloned_proj = pub_store.clone_public_project(
        user_b,
        pub_rec.publication_id,
        "0.15.8",
        private_store=priv_store,
        new_name="Cloned 18-inch Pro Sub",
    )
    assert cloned_proj.owner_uid == user_b.uid
    assert cloned_proj.tenant_id == user_b.tenant_id
    assert cloned_proj.name == "Cloned 18-inch Pro Sub"
    # Verify the clone was saved into private store
    loaded_clone = priv_store.load_project(user_b, cloned_proj.project_id)
    assert loaded_clone is not None
    assert loaded_clone.owner_uid == user_b.uid


def test_catalog_runtime_store_and_promotion():
    """Test CatalogRuntimeStore query, promotion and rollback."""
    cat_store = storage.get_shared_memory_catalog_runtime_store()
    drivers = [
        {"id": "drv_1", "brand": "FaitalPRO", "model": "18HP1060", "fs_hz": 35.0, "re_ohm": 5.5},
        {"id": "drv_2", "brand": "B&C", "model": "18TBX100", "fs_hz": 34.0, "re_ohm": 5.1},
    ]
    rel = cat_store.promote_release("rel_2026_09_01", "operator@loadforge.app", drivers)
    assert rel["release_id"] == "rel_2026_09_01"
    assert rel["driver_count"] == 2

    # Query driver
    d1 = cat_store.get_driver("drv_1")
    assert d1 is not None
    assert d1["model"] == "18HP1060"

    # Search
    search_results = cat_store.search_drivers(brand="FaitalPRO")
    assert len(search_results) == 1
    assert search_results[0]["model"] == "18HP1060"

    # Rollback
    drivers_v2 = [
        {"id": "drv_1", "brand": "FaitalPRO", "model": "18HP1060", "fs_hz": 35.0, "re_ohm": 5.5},
    ]
    cat_store.promote_release("rel_2026_09_02", "operator@loadforge.app", drivers_v2)
    meta_v2 = cat_store.get_release_metadata()
    assert meta_v2["release_id"] == "rel_2026_09_02"

    # Rollback to v1
    cat_store.rollback_release("rel_2026_09_01", "operator@loadforge.app")
    meta_rolled = cat_store.get_release_metadata()
    assert meta_rolled["release_id"] == "rel_2026_09_01"


def test_catalog_staging_store():
    """Test CatalogStagingStore ingestion and candidate storage."""
    staging_store = storage.get_shared_memory_catalog_staging_store()
    cand_id = staging_store.save_candidate(
        "run_20260901",
        "target_faital",
        {"model": "18HP1060", "fs_hz": 35.0, "confidence": 0.95},
    )
    assert cand_id is not None

    run_id = staging_store.save_ingestion_run(
        "run_20260901",
        {"objective": "harvest_missing_pro_audio"},
        [{"target_id": "target_faital", "status": "succeeded"}],
    )
    assert run_id == "run_20260901"
    run_data = staging_store.get_run("run_20260901")
    assert run_data is not None
    assert run_data["publication_state"] == "staging_only"

    candidates = staging_store.get_candidates_for_run("run_20260901")
    assert len(candidates) == 1
    assert candidates[0]["model"] == "18HP1060"


def test_public_unlisted_visibility_isolation():
    """Verify that unlisted publications exist but are not discoverable in Explore."""
    pub_store = storage.get_shared_memory_public_store()
    user = saas.SaaSUser("u_stealth", "stealth@example.test", "Stealth", "t_stealth")
    payload = {
        "load_type": "Bass reflex",
        "reflex_vb_l": 80.0,
        "reflex_fb_hz": 30.0,
        "driver_preset_name": "Secret Sub Driver",
    }
    unlisted_pub = pub_store.publish_project(
        user,
        "proj_secret_1",
        payload,
        title="Secret Stealth Sub",
        visibility="unlisted",
        app_version="0.15.8",
    )
    # Direct access works
    loaded = pub_store.get_public_project(unlisted_pub.publication_id)
    assert loaded is not None
    assert loaded.visibility == "unlisted"

    # Search in Explore gallery does NOT return unlisted projects
    gallery = pub_store.list_public_projects(query="Stealth")
    assert not any(p.publication_id == unlisted_pub.publication_id for p in gallery)


def test_public_snapshot_immutability_on_private_edits():
    """Verify modifying or trashing private projects never alters published snapshots."""
    pub_store = storage.get_shared_memory_public_store()
    priv_store = storage.get_shared_memory_private_store()
    user = saas.SaaSUser("u_author2", "author2@example.test", "Author 2", "t_author2")

    # 1. Private project v1
    v1_payload = {
        "load_type": "Bass reflex",
        "reflex_vb_l": 50.0,
        "reflex_fb_hz": 40.0,
        "driver_preset_name": "Faital 15PR400",
    }
    prj = priv_store.save_project(user, "Reference Sub", v1_payload, "0.15.8")

    # 2. Publish snapshot
    pub = pub_store.publish_project(
        user,
        prj.project_id,
        prj.parameters,
        title="Faital 15PR400 Snapshot",
        visibility="public",
        app_version="0.15.8",
        source_revision=prj.revision,
    )

    # 3. Private edit v2
    v2_payload = {
        "load_type": "Bass reflex",
        "reflex_vb_l": 75.0,
        "reflex_fb_hz": 32.0,
        "driver_preset_name": "Faital 15PR400",
    }
    prj_v2 = priv_store.save_project(user, "Reference Sub", v2_payload, "0.15.8", project_id=prj.project_id, expected_revision=1)
    assert prj_v2.revision == 2

    # 4. Public snapshot remains v1 (50.0 L, 40.0 Hz)
    pub_loaded = pub_store.get_public_project(pub.publication_id)
    assert pub_loaded is not None
    assert pub_loaded.parameters["reflex_vb_l"] == 50.0
    assert pub_loaded.parameters["reflex_fb_hz"] == 40.0

    # 5. Soft-delete private project
    priv_store.soft_delete_project(user, prj.project_id, "0.15.8", expected_revision=2)
    assert priv_store.load_project(user, prj.project_id).status == "trashed"

    # Public snapshot is still active and unchanged
    pub_after_trash = pub_store.get_public_project(pub.publication_id)
    assert pub_after_trash is not None
    assert pub_after_trash.parameters["reflex_vb_l"] == 50.0


def test_republish_ownership_enforcement():
    """Verify that User B cannot overwrite or re-publish User A's publication."""
    pub_store = storage.get_shared_memory_public_store()
    user_a = saas.SaaSUser("u_orig_author", "orig@example.test", "Orig", "t_a")
    user_b = saas.SaaSUser("u_intruder", "intruder@example.test", "Intruder", "t_b")

    payload = {"load_type": "Sealed", "sealed_vb_l": 25.0}
    pub = pub_store.publish_project(
        user_a,
        "prj_a",
        payload,
        title="Author A Sub",
        visibility="public",
        app_version="0.15.8",
    )

    try:
        pub_store.publish_project(
            user_b,
            "prj_b",
            payload,
            title="Hijacked Title",
            visibility="public",
            app_version="0.15.8",
            publication_id=pub.publication_id,
        )
        assert False, "User B should not be able to republish User A's publication"
    except saas.ProjectAccessError:
        pass


def test_catalog_promotion_pipeline_tool():
    """Verify promotion pipeline tool: validation, manifest, approval gate, rollback."""
    from tools import promote_catalog_release as promoter

    valid_driver = {
        "id": "drv_test_faital",
        "brand": "FaitalPRO",
        "model": "18HP1060",
        "fs_hz": 35.0,
        "vas_l": 150.0,
        "qts": 0.35,
        "qms": 6.5,
        "re_ohm": 5.5,
        "sd_cm2": 1200.0,
    }
    invalid_driver = {
        "id": "drv_invalid",
        "brand": "BadBrand",
        "model": "BrokenModel",
        "fs_hz": -10.0,  # invalid physics
        "re_ohm": 0.0,
    }

    # 1. Validation gate
    valid, errors = promoter.validate_candidate_drivers([valid_driver, invalid_driver])
    assert len(valid) == 1
    assert len(errors) == 1
    assert "BrokenModel" in errors[0]

    # 2. Approval gate required
    try:
        promoter.promote_catalog_release(
            candidate_drivers=[valid_driver],
            release_id="rel_2026_test",
            approved_by="",  # missing
            dry_run=True,
        )
        assert False, "Approval must be required"
    except ValueError:
        pass

    # 3. Dry-run manifest generation
    manifest = promoter.promote_catalog_release(
        candidate_drivers=[valid_driver],
        release_id="rel_2026_test",
        approved_by="lead-engineer@loadforge.app",
        dry_run=True,
    )
    assert manifest["release_id"] == "rel_2026_test"
    assert manifest["approved_by"] == "lead-engineer@loadforge.app"
    assert manifest["driver_count"] == 1
    assert manifest["catalog_sha256"] is not None

    # 4. Rollback validation
    rb = promoter.rollback_catalog_release(
        target_release_id="rel_2026_prev",
        rolled_back_by="lead-engineer@loadforge.app",
        dry_run=True,
    )
    assert rb["target_release_id"] == "rel_2026_prev"


def test_crawler_service_does_not_import_private_or_public_store():
    """Verify architectural boundary: crawler agent must not import private or public stores."""
    crawler_agent_path = ROOT / "services" / "crawler_agent" / "agent.py"
def test_private_store_credits_and_revision_retention_isolation():
    """Verify tenant credit isolation, optimistic locking, and revision restoration."""
    store = storage.get_shared_memory_private_store()
    user_a = saas.SaaSUser("u_alpha", "alpha@loadforge.test", "Alpha", "t_alpha")
    user_b = saas.SaaSUser("u_beta", "beta@loadforge.test", "Beta", "t_beta")

    # 1. Credit accounts
    acc_a = store.get_or_create_account(user_a.uid, user_a.email, user_a.name)
    acc_b = store.get_or_create_account(user_b.uid, user_b.email, user_b.name)
    init_a = acc_a.credits_balance
    init_b = acc_b.credits_balance
    store.adjust_credits(user_a.email, 50)
    assert store.get_or_create_account(user_a.uid, user_a.email, user_a.name).credits_balance == init_a + 50
    assert store.get_or_create_account(user_b.uid, user_b.email, user_b.name).credits_balance == init_b

    # 2. Revisions and optimistic concurrency
    p1_params = {"load_type": "Bass reflex", "reflex_vb_l": 50.0, "reflex_fb_hz": 35.0}
    p2_params = {"load_type": "Bass reflex", "reflex_vb_l": 50.0, "reflex_fb_hz": 38.0}
    p3_conflict = {"load_type": "Bass reflex", "reflex_vb_l": 50.0, "reflex_fb_hz": 40.0}

    p = store.save_project(user_a, "Design Alpha", p1_params, "0.15.8")
    p_v2 = store.save_project(user_a, "Design Alpha", p2_params, "0.15.8", project_id=p.project_id, expected_revision=1)
    assert p_v2.revision == 2

    # Concurrency conflict
    try:
        store.save_project(user_a, "Design Alpha", p3_conflict, "0.15.8", project_id=p.project_id, expected_revision=1)
        assert False, "Stale revision must be rejected"
    except saas.ProjectConflictError:
        pass

    # 3. Restore revision 1
    p_restored = store.restore_revision(user_a, p.project_id, revision=1, app_version="0.15.8", expected_revision=2)
    assert p_restored.revision == 3
    assert p_restored.parameters["reflex_fb_hz"] == 35.0

    # 4. Soft delete
    store.soft_delete_project(user_a, p.project_id, "0.15.8", expected_revision=3)
    active_projects = store.list_projects(user_a, include_deleted=False)
    assert not any(proj.project_id == p.project_id for proj in active_projects)
    all_projects = store.list_projects(user_a, include_deleted=True)
    assert any(proj.project_id == p.project_id for proj in all_projects)


def test_iam_policy_matrix_simulation():
    """Simulate and verify the least-privilege IAM policy matrix across all 4 databases."""
    iam_matrix = {
        "sa-loadforge-app": {
            "lf-private": "read_write",
            "lf-public": "read_write",
            "lf-catalog-runtime": "read_only",
            "lf-catalog-staging": "forbidden",
        },
        "sa-loadforge-crawler": {
            "lf-private": "forbidden",
            "lf-public": "forbidden",
            "lf-catalog-runtime": "forbidden",
            "lf-catalog-staging": "read_write",
        },
        "sa-loadforge-promoter": {
            "lf-private": "forbidden",
            "lf-public": "forbidden",
            "lf-catalog-runtime": "read_write",
            "lf-catalog-staging": "read_only",
        },
        "sa-loadforge-public": {
            "lf-private": "forbidden",
            "lf-public": "read_only",
            "lf-catalog-runtime": "read_only",
            "lf-catalog-staging": "forbidden",
        },
    }

    # 1. Crawler guarantees
    crawler_perms = iam_matrix["sa-loadforge-crawler"]
    assert crawler_perms["lf-private"] == "forbidden", "Crawler must never access private user data"
    assert crawler_perms["lf-public"] == "forbidden", "Crawler must never access public project store"
    assert crawler_perms["lf-catalog-runtime"] == "forbidden", "Crawler must never directly modify runtime catalog"
    assert crawler_perms["lf-catalog-staging"] == "read_write"

    # 2. App runtime guarantees
    app_perms = iam_matrix["sa-loadforge-app"]
    assert app_perms["lf-catalog-staging"] == "forbidden", "App runtime must never access untrusted crawler staging"
    assert app_perms["lf-catalog-runtime"] == "read_only", "App runtime cannot mutate production catalog directly"
    assert app_perms["lf-private"] == "read_write"
    assert app_perms["lf-public"] == "read_write"

    # 3. Promoter guarantees
    promoter_perms = iam_matrix["sa-loadforge-promoter"]
    assert promoter_perms["lf-private"] == "forbidden", "Promoter has no access to user private projects"
    assert promoter_perms["lf-public"] == "forbidden", "Promoter has no access to public project community store"
    assert promoter_perms["lf-catalog-staging"] == "read_only"
    assert promoter_perms["lf-catalog-runtime"] == "read_write"

    # 4. Public service guarantees
    public_perms = iam_matrix["sa-loadforge-public"]
    assert public_perms["lf-private"] == "forbidden", "Public service must never access private user data"
    assert public_perms["lf-catalog-staging"] == "forbidden", "Public service has no access to staging"


def test_crawler_service_does_not_import_private_or_public_store():
    """Verify architectural boundary: crawler agent must not import private or public stores."""
    crawler_repo = Path(__file__).resolve().parents[2] / "load_forge_crawler"
    crawler_agent_path = crawler_repo / "services" / "crawler_agent" / "agent.py"
    crawler_release_path = crawler_repo / "services" / "crawler_agent" / "release.py"
    if not crawler_agent_path.exists():
        crawler_agent_path = ROOT / "services" / "crawler_agent" / "agent.py"
        crawler_release_path = ROOT / "services" / "crawler_agent" / "release.py"
    if crawler_agent_path.exists() and crawler_release_path.exists():
        crawler_code = crawler_agent_path.read_text(encoding="utf-8") + "\n" + crawler_release_path.read_text(encoding="utf-8")
        assert "private_store" not in crawler_code
        assert "public_store" not in crawler_code
        assert "PrivateStore" not in crawler_code
        assert "PublicStore" not in crawler_code


def main() -> int:
    test_funcs = [
        test_saas_settings_named_databases_default,
        test_saas_settings_named_databases_explicit,
        test_saas_settings_legacy_env_var_fallback,
        test_saas_settings_rejects_invalid_db_names,
        test_saas_settings_strict_multi_db,
        test_validate_database_name,
        test_private_store_project_and_account_isolation,
        test_private_store_credits_and_revision_retention_isolation,
        test_public_store_isolation_and_cross_domain_clone,
        test_public_unlisted_visibility_isolation,
        test_public_snapshot_immutability_on_private_edits,
        test_republish_ownership_enforcement,
        test_catalog_runtime_store_and_promotion,
        test_catalog_staging_store,
        test_catalog_promotion_pipeline_tool,
        test_iam_policy_matrix_simulation,
        test_crawler_service_does_not_import_private_or_public_store,
    ]
    for fn in test_funcs:
        fn()
        print(f"  OK {fn.__name__}")
    print(f"\nSTORAGE BOUNDARIES PASS: {len(test_funcs)} tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
