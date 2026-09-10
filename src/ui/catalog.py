"""Driver/preset library, catalog maintenance and price helpers."""

from __future__ import annotations

from functools import cache, lru_cache
from pathlib import Path
import hashlib
import html
import json
import os

import numpy as np
import pandas as pd
import streamlit as st

import acoustics as _acoustics
import presets as _presets
import pricing as _pricing

from . import account as _account
from . import constants as _constants
from . import finder as _finder
from . import optimizer as _optimizer
from . import runtime as _runtime
from . import state as _state


def _render_catalog_crawl_report() -> None:
    """Show staging progress/report without coupling the app to the daemon."""
    report = _state._read_json_object(_constants._CATALOG_CRAWL_REPORT)
    progress = _state._read_json_object(_constants._CATALOG_CRAWL_PROGRESS)
    retailer_report = _state._read_json_object(_constants._RETAILER_CRAWL_REPORT)
    additions_report = _state._read_json_object(_constants._CATALOG_ADDITIONS_REPORT)
    if not report and not progress and not retailer_report and not additions_report:
        return
    phase = str(progress.get("phase") or "").replace("_", " ")
    active = phase not in {"", "complete", "sleeping", "failed"}
    if not active:
        return
    label = f"Catalog crawl · {phase}"
    with st.expander(label, expanded=True):
        if progress:
            st.caption(
                f"Status: {phase or 'unknown'} · updated "
                f"{str(progress.get('updated_at') or 'n/a')[:19]}"
            )
            if active:
                progress_bits = []
                for key, title in (
                    ("brands", "brands"),
                    ("covered", "covered"),
                    ("unresolved", "unresolved"),
                    ("verified", "verified"),
                    ("targets_complete", "targets complete"),
                    ("targets_total", "targets total"),
                ):
                    if key in progress:
                        progress_bits.append(f"{title}: {progress[key]}")
                if progress_bits:
                    st.write(" · ".join(progress_bits))
        summary = report.get("registry_summary") or {}
        if summary:
            c1, c2 = st.columns(2)
            c1.metric(
                "Official coverage",
                f"{int(summary.get('covered_brand_labels', 0)):,} / "
                f"{int(summary.get('catalog_brands', 0)):,}",
            )
            c2.metric(
                "Official targets",
                f"{int(summary.get('ready_official_targets', 0)):,}",
            )
            st.caption(
                f"Aliases {int(summary.get('brand_aliases', 0)):,} · "
                f"needs discovery {int(summary.get('needs_discovery', 0)):,} · "
                f"brand cleanup {int(summary.get('needs_brand_cleanup', 0)):,}"
            )
        if report:
            state = str(report.get("publication_state") or "unknown")
            unchanged = bool(report.get("catalog_unchanged"))
            st.caption(
                f"Publication: {state}. Existing catalog "
                f"{'unchanged' if unchanged else 'changed unexpectedly'}."
            )
        if additions_report:
            st.divider()
            st.markdown("**Reviewed catalog additions**")
            added = int(additions_report.get("added", 0))
            latest_batch = int(additions_report.get("latest_batch_added", added))
            latest_visible = int(
                additions_report.get("latest_batch_visible_added", latest_batch)
            )
            final_records = int(additions_report.get("final_records", 0))
            app_visible = int(additions_report.get("app_visible_records", 0))
            latest_label = f"+{latest_batch:,} latest batch"
            if latest_visible != latest_batch:
                latest_label += f" / +{latest_visible:,} app-visible"
            st.caption(
                f"{added:,} new validated drivers published append-only "
                f"({latest_label}) · "
                f"catalog {final_records:,} · app-visible {app_visible:,}."
            )
            latest_by_brand = additions_report.get("latest_batch_by_brand") or {}
            if isinstance(latest_by_brand, dict) and latest_by_brand:
                st.caption(
                    "Latest batch: "
                    + " · ".join(
                        f"{brand} {int(count):,}"
                        for brand, count in latest_by_brand.items()
                    )
                )
            latest_visible_by_brand = (
                additions_report.get("latest_batch_visible_by_brand") or {}
            )
            if (
                isinstance(latest_visible_by_brand, dict)
                and latest_visible_by_brand
                and latest_visible_by_brand != latest_by_brand
            ):
                st.caption(
                    "Net app-visible: "
                    + " · ".join(
                        f"{brand} {int(count):,}"
                        for brand, count in latest_visible_by_brand.items()
                    )
                )
            added_names = [
                str(name)
                for name in additions_report.get(
                    "added_names_sample",
                    additions_report.get("added_names", []),
                )
                if str(name).strip()
            ]
            if added_names:
                names_count = int(
                    additions_report.get("added_names_count", len(added_names))
                )
                suffix = (
                    f" · … {names_count - len(added_names):,} more"
                    if names_count > len(added_names)
                    else ""
                )
                st.caption("Sample: " + " · ".join(added_names) + suffix)
        retailer_summary = retailer_report.get("summary") or {}
        if retailer_summary:
            st.divider()
            st.markdown(f"**Retail gaps · {retailer_report.get('source', 'source')}**")
            st.caption(
                f"{int(retailer_summary.get('observations', 0)):,} products · "
                f"{int(retailer_summary.get('exact_catalog_matches', 0)):,} exact matches · "
                f"{int(retailer_summary.get('potential_catalog_gaps', 0)):,} potential gaps · "
                f"{int(retailer_summary.get('pages_failed', 0)):,} failed pages"
            )

def _catalog_record_display_identity(
    record: dict,
    fallback_name: str,
) -> tuple[str, str]:
    """Return the normalized identity shown by Catalog Maintenance."""
    manufacturer = _presets._external_catalog_manufacturer(
        str(record.get("matched_brand", record.get("brand", "")))
    )
    raw_model = _presets._external_catalog_identity_model(
        record, fallback_name
    )
    part_number = _presets._external_catalog_part_number(
        manufacturer, raw_model
    )
    return manufacturer, part_number or raw_model

def _render_catalog_maintenance() -> None:
    """Administrator-only editor for the persistent driver price catalog."""
    if not _maintenance_allowed():
        st.error("Catalog Maintenance is restricted to the administrator.")
        return
    st.markdown(
        """<style>
        section[data-testid="stSidebar"] { display: none !important; }
        [data-testid="stMainBlockContainer"] { max-width: 100% !important; padding: .35rem 1rem !important; }
        [data-testid="stVerticalBlock"] { gap: .35rem !important; }
        .maintenance-heading { font-size: 1.55rem; font-weight: 700; line-height: 1.15; margin: .1rem 0 .35rem; }
        .maintenance-meta { color: #8b949e; font-size: .78rem; margin: -.05rem 0 .25rem; }
        div[data-testid="stDataEditor"] [role="row"] { min-height: 30px !important; }
        div[data-testid="stDataEditor"] { width: 100% !important; }
        </style>""",
        unsafe_allow_html=True,
    )
    catalog_paths = {
        "Proprietario": "catalog_proprietario.json",
        "LSDB": "catalog_lsdb.json",
        "VituixCAD": "catalog_vituixcad.json",
        "Speaker Box Lite": "catalog_speakerboxlite.json",
    }
    c_back, c_title = st.columns([1.5, 8.5], vertical_alignment="center")
    with c_back:
        if st.button("← Back to app", key="maintenance_back_btn"):
            _state._select_workspace("Bass Match")
            st.rerun()
    with c_title:
        st.markdown('<div class="maintenance-heading">Catalog Maintenance</div>', unsafe_allow_html=True)
    notice = str(st.session_state.pop("maintenance_notice", ""))
    if notice:
        st.success(notice)
    catalog_col, search_col, save_col, duplicate_col, delete_col, backup_col, restore_col = st.columns(
        [1.25, 2.75, .8, 1.45, 1.25, 1.4, 1.15],
        gap="small",
        vertical_alignment="bottom",
    )
    with catalog_col:
        catalog_label = st.selectbox(
            "Catalog",
            tuple(catalog_paths),
            key="maintenance_catalog",
            label_visibility="collapsed",
        )
    path = _constants._PROJECT_ROOT / "data" / catalog_paths[catalog_label]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        unified_catalog = isinstance(payload.get("presets"), list)
        if unified_catalog:
            prices = {
                str(item.get("name") or item.get("model") or index): item
                for index, item in enumerate(payload["presets"])
                if isinstance(item, dict)
            }
        else:
            prices = payload.setdefault("prices", {})
    except (OSError, json.JSONDecodeError) as exc:
        st.error(f"Could not load price catalog: {exc}")
        return
    with search_col:
        query = st.text_input(
            "Search",
            key="maintenance_query",
            placeholder="Search name, brand or model…",
            label_visibility="collapsed",
        )
    with save_col:
        save_clicked = st.button(
            "Save",
            type="primary",
            key="maintenance_save",
            width="stretch",
        )
    with duplicate_col:
        duplicate_clicked = st.button(
            "Duplicate selected",
            key="maintenance_duplicate",
            width="stretch",
        )
    with delete_col:
        delete_clicked = st.button(
            "Delete selected",
            key="maintenance_delete",
            width="stretch",
        )
    backup_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    with backup_col:
        st.download_button(
            "Download backup",
            data=backup_bytes,
            file_name=f"{path.stem}_backup.json",
            mime="application/json",
            key="maintenance_backup_download",
            width="stretch",
        )
    with restore_col:
        with st.popover("Restore backup", width="stretch"):
            uploaded = st.file_uploader(
                "JSON backup",
                type=["json"],
                key="maintenance_restore_upload",
            )
            if uploaded is not None and st.button(
                "Restore selected catalog",
                key="maintenance_restore_button",
                type="primary",
                width="stretch",
            ):
                try:
                    restored = json.loads(uploaded.getvalue().decode("utf-8"))
                    if not isinstance(restored, dict) or not (
                        isinstance(restored.get("prices"), dict)
                        or isinstance(restored.get("presets"), list)
                    ):
                        raise ValueError("backup must contain prices or presets")
                    path.write_text(json.dumps(restored, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    _pricing._load_driver_price_records.cache_clear()
                    st.success("Full library restored")
                    st.rerun()
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as exc:
                    st.error(f"Restore failed: {exc}")
    keys = [str(k) for k in prices]
    matches = [k for k in keys if not query or query.casefold() in k.casefold()]
    st.markdown(
        f'<div class="maintenance-meta">{catalog_label} · {len(prices):,} records · {len(matches):,} shown</div>',
        unsafe_allow_html=True,
    )
    if unified_catalog:
        mechanical_fields = (
            "overall_diameter_mm", "cutout_diameter_mm", "depth_mm",
            "mounting_depth_mm", "bolt_circle_mm", "mounting_hole_count",
            "mounting_hole_diameter_mm", "weight_kg",
        )
        essential_fields = (
            "overall_diameter_mm", "cutout_diameter_mm", "depth_mm", "weight_kg",
        )

        def has_positive(record: dict, field: str) -> bool:
            value = (record.get("mechanical") or {}).get(field)
            return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0

        catalog_records = list(prices.values())
        any_mechanical = sum(
            any(has_positive(record, field) for field in mechanical_fields)
            for record in catalog_records
        )
        essential_complete = sum(
            all(has_positive(record, field) for field in essential_fields)
            for record in catalog_records
        )
        fully_complete = sum(
            all(has_positive(record, field) for field in mechanical_fields)
            for record in catalog_records
        )
        metric_any, metric_essential, metric_full = st.columns(3)
        metric_any.metric("Any real mechanical data", f"{any_mechanical:,} / {len(catalog_records):,}")
        metric_essential.metric("Essential 4 complete", f"{essential_complete:,} / {len(catalog_records):,}")
        metric_full.metric("All 8 complete", f"{fully_complete:,} / {len(catalog_records):,}")
        coverage_labels = {
            "overall_diameter_mm": "overall",
            "cutout_diameter_mm": "cutout",
            "depth_mm": "depth",
            "mounting_depth_mm": "mount depth",
            "bolt_circle_mm": "bolt circle",
            "mounting_hole_count": "hole count",
            "mounting_hole_diameter_mm": "hole Ø",
            "weight_kg": "weight",
        }
        coverage = " · ".join(
            f"{coverage_labels[field]} {sum(has_positive(record, field) for record in catalog_records):,}"
            for field in mechanical_fields
        )
        st.caption(f"Verified mechanical field coverage: {coverage}")
    rows = []
    original_rows = {}
    for key in matches:
        record = dict(prices.get(key) or {})
        driver = dict(record.get("driver") or {})
        mechanical = dict(record.get("mechanical") or {})
        published = dict(record.get("published_specs") or {})
        manufacturer, part_number = _catalog_record_display_identity(
            record, key
        )
        status = str(record.get("availability", "InStock")).rsplit("/", 1)[-1]
        if status not in {"InStock", "OutOfStock", "Discontinued"}:
            status = "InStock"
        row = {"_key": key, "Name": record.get("matched_name", record.get("name", key)),
               "Brand": manufacturer, "MPN": part_number,
               "Xmax mm": float(driver.get("xmax_mm") or 0),
               "Pmax W": float(driver.get("pe_w") or 0),
               "Le mH": float(driver.get("le_mh") or 0),
               "Overall mm": mechanical.get("overall_diameter_mm"),
               "Cutout mm": mechanical.get("cutout_diameter_mm"),
               "Depth mm": mechanical.get("depth_mm"),
               "Mount depth mm": mechanical.get("mounting_depth_mm"),
               "Bolt circle mm": mechanical.get("bolt_circle_mm"),
               "Weight kg": mechanical.get("weight_kg"),
               "Znom ohm": published.get("nominal_impedance_ohm"),
               "Sensitivity dB": published.get("sensitivity_db"),
               "Voice coil mm": published.get("voice_coil_diameter_mm"),
               "Xmech mm": published.get("xmech_mm"),
               "Nominal diameter in": published.get("nominal_diameter_in"),
               "Price": float(record.get("price") or 0),
               "Currency": record.get("currency", record.get("price_currency", "EUR")), "Link": record.get("price_url") or record.get("url", ""),
               "Status": status, "Select": False}
        rows.append(row)
        original_rows[key] = row
    def compact_width(column: str, minimum: int, maximum: int) -> int:
        longest = max((len(str(row.get(column, ""))) for row in rows), default=0)
        return min(maximum, max(minimum, 22 + longest * 7))

    edited = st.data_editor(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        height=860,
        disabled=[
            "_key", "Overall mm", "Cutout mm", "Depth mm", "Mount depth mm",
            "Bolt circle mm", "Weight kg", "Znom ohm", "Sensitivity dB",
            "Voice coil mm", "Xmech mm", "Nominal diameter in",
        ],
        column_config={
            "_key": None,
            "Name": None,
            "Brand": st.column_config.TextColumn(
                "Manufacturer", width=compact_width("Brand", 85, 150)
            ),
            "MPN": st.column_config.TextColumn(
                "Part number", width=compact_width("MPN", 90, 180)
            ),
            "Xmax mm": st.column_config.NumberColumn(
                "Xmax (mm)", width=92, min_value=0.0, format="%.2f"
            ),
            "Pmax W": st.column_config.NumberColumn(
                "Pmax (W)", width=92, min_value=0.0, format="%.1f"
            ),
            "Le mH": st.column_config.NumberColumn(
                "Le (mH)", width=82, min_value=0.0, format="%.3f"
            ),
            "Overall mm": st.column_config.NumberColumn("Overall Ø", width=92, format="%.1f mm"),
            "Cutout mm": st.column_config.NumberColumn("Cutout Ø", width=88, format="%.1f mm"),
            "Depth mm": st.column_config.NumberColumn("Depth", width=82, format="%.1f mm"),
            "Mount depth mm": st.column_config.NumberColumn("Mount depth", width=105, format="%.1f mm"),
            "Bolt circle mm": st.column_config.NumberColumn("Bolt circle", width=96, format="%.1f mm"),
            "Weight kg": st.column_config.NumberColumn("Weight", width=82, format="%.2f kg"),
            "Znom ohm": st.column_config.NumberColumn("Znom", width=75, format="%.1f Ω"),
            "Sensitivity dB": st.column_config.NumberColumn("Sensitivity", width=100, format="%.1f dB"),
            "Voice coil mm": st.column_config.NumberColumn("Voice coil Ø", width=100, format="%.1f mm"),
            "Xmech mm": st.column_config.NumberColumn("Xmech", width=82, format="%.2f mm"),
            "Nominal diameter in": st.column_config.NumberColumn("Nominal Ø", width=95, format='%.2f"'),
            "Price": st.column_config.NumberColumn("Price", width=82, format="%.2f"),
            "Currency": st.column_config.TextColumn("Currency", width=82),
            "Link": st.column_config.LinkColumn("Link", width=82, display_text="Open"),
            "Status": st.column_config.SelectboxColumn("Status", options=["InStock", "OutOfStock", "Discontinued"], width=120),
            "Select": st.column_config.CheckboxColumn("Select", width=74),
        },
        key=f"maintenance_table_{catalog_label}_{st.session_state.get('maintenance_table_revision', 0)}",
    )
    edited_rows = edited.to_dict("records")
    selected_keys = [
        str(row.get("_key", ""))
        for row in edited_rows
        if row.get("Select") and str(row.get("_key", "")) in prices
    ]
    selection_action = duplicate_clicked or delete_clicked
    if selection_action and not selected_keys:
        st.warning("Select at least one row first.")
    elif save_clicked or selection_action:
        for row in edited_rows:
            key = str(row.get("_key", ""))
            if key not in prices:
                continue
            if not any(
                row.get(column) != original_rows[key].get(column)
                for column in (
                    "Name", "Brand", "MPN", "Xmax mm", "Pmax W", "Le mH",
                    "Price", "Currency", "Link", "Status",
                )
            ):
                continue
            driver = dict(prices[key].get("driver") or {})
            driver.update(
                xmax_mm=float(row.get("Xmax mm") or 0),
                pe_w=float(row.get("Pmax W") or 0),
                le_mh=float(row.get("Le mH") or 0),
            )
            updated = dict(price=float(row.get("Price") or 0), currency=str(row.get("Currency") or "EUR").upper(),
                           availability=str(row.get("Status") or "InStock"), matched_name=str(row.get("Name") or key),
                           matched_brand=str(row.get("Brand") or ""), matched_mpn=str(row.get("MPN") or key),
                           part_number_override=str(row.get("MPN") or key),
                           driver=driver,
                           source="Manual catalog maintenance")
            updated["price_url" if unified_catalog else "url"] = str(row.get("Link") or "")
            prices[key].update(updated)
        if delete_clicked:
            for key in selected_keys:
                prices.pop(key, None)
        elif duplicate_clicked:
            for source_key in selected_keys:
                new_key = source_key + "-copy"
                i = 2
                while new_key in prices:
                    new_key = f"{source_key}-copy-{i}"
                    i += 1
                copied = dict(prices[source_key])
                copied["matched_name"] = new_key
                if unified_catalog:
                    copied["name"] = new_key
                prices[new_key] = copied
        if unified_catalog:
            payload["presets"] = list(prices.values())
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _pricing._load_driver_price_records.cache_clear()
        st.session_state["maintenance_table_revision"] = int(
            st.session_state.get("maintenance_table_revision", 0)
        ) + 1
        if delete_clicked:
            st.session_state["maintenance_notice"] = f"Deleted {len(selected_keys)} selected record(s)."
        elif duplicate_clicked:
            st.session_state["maintenance_notice"] = f"Duplicated {len(selected_keys)} selected record(s)."
        else:
            st.session_state["maintenance_notice"] = "Catalog saved."
        st.rerun()

def _maintenance_allowed() -> bool:
    """Restrict catalog editing and user management to the explicitly configured administrator."""
    acc = _account._get_current_user_account()
    if acc and acc.is_admin:
        return True
    admin_email = str(
        os.getenv("LOAD_FORGE_ADMIN_EMAIL", "playloud79@gmail.com")
    ).strip().casefold()
    if _runtime._CURRENT_SAAS_USER is None:
        return not _runtime._SAAS_SETTINGS.enabled and bool(admin_email)
    uid = str(os.getenv("LOAD_FORGE_ADMIN_UID", "")).strip()
    return bool(
        (admin_email and str(_runtime._CURRENT_SAAS_USER.email).casefold() == admin_email)
        or (uid and str(_runtime._CURRENT_SAAS_USER.uid) == uid)
    )

def _catalog_path_for_preset(preset_name: str) -> Path | None:
    """Return the editable source catalog for one external driver preset."""
    if not preset_name or preset_name == "Custom":
        return None
    try:
        provenance = _acoustics.driver_preset_provenance_category(preset_name)
    except ValueError:
        return None
    filename = _constants._CATALOG_PATH_BY_PROVENANCE.get(provenance)
    return (
        _constants._PROJECT_ROOT / "data" / filename
        if filename is not None
        else None
    )

def _driver_catalog_mapping(driver: _acoustics.DriverTS) -> dict[str, float]:
    """Serialize the editable Box Design driver fields for a catalog record."""
    return {
        "fs_hz": float(driver.fs_hz), "vas_l": float(driver.vas_l),
        "qts": float(driver.qts), "qms": float(driver.qms),
        "re_ohm": float(driver.re_ohm), "sd_cm2": float(driver.sd_cm2),
        "le_mh": float(driver.le_mh), "le10k_mh": float(driver.le10k_mh or 0.0),
        "xmax_mm": float(driver.xmax_mm), "pe_w": float(driver.pe_w),
        "mms_g": float(driver.mms_g or 0.0),
        "cms_mm_per_n": float(driver.cms_mm_per_n or 0.0),
        "bl_tm": float(driver.bl_tm or 0.0),
    }

def _update_catalog_driver_from_box_design(
    preset_name: str,
    driver: _acoustics.DriverTS,
    *,
    path: Path | None = None,
) -> str:
    """Persist the selected external preset's T/S values from Box Design."""
    target_path = path or _catalog_path_for_preset(preset_name)
    if target_path is None:
        raise ValueError("This driver is not backed by an editable catalog")
    try:
        payload = json.loads(target_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read the source catalog: {exc}") from exc
    records = payload.get("presets") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError("The source catalog has no editable preset records")
    selected_fields = _driver_catalog_mapping(_acoustics.get_driver_preset(preset_name))
    preset_info = _acoustics.driver_preset_info(preset_name)
    selected_brand = _presets._external_catalog_manufacturer(preset_info.brand)
    selected_part_number = _presets._external_catalog_part_number(
        selected_brand, preset_info.part_number or preset_info.model,
    )
    matching_record = None
    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get("name", "")) == preset_name:
            matching_record = record
            break
        record_brand, record_part_number = _catalog_record_display_identity(
            record, str(record.get("name", "")),
        )
        if (
            selected_part_number
            and record_brand.casefold() == selected_brand.casefold()
            and record_part_number.casefold() == selected_part_number.casefold()
        ):
            matching_record = record
            break
        stored = record.get("driver")
        if not isinstance(stored, dict):
            continue
        try:
            matches_selected = all(
                np.isclose(float(stored.get(field, 0.0) or 0.0), value,
                           rtol=1e-9, atol=1e-9)
                for field, value in selected_fields.items()
                if field in {"fs_hz", "vas_l", "qts", "qms", "re_ohm", "sd_cm2"}
            )
        except (TypeError, ValueError):
            matches_selected = False
        if matches_selected:
            matching_record = record
            break
    if matching_record is None:
        raise ValueError("Could not find the selected driver in its source catalog")
    matching_record["driver"] = _driver_catalog_mapping(driver)
    try:
        target_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ValueError(f"Could not update the source catalog: {exc}") from exc
    for loader in (
        _presets._load_loudspeaker_database_presets,
        _presets._load_manufacturer_presets,
        _presets._load_vituixcad_presets,
        _presets._load_speakerboxlite_presets,
        _presets._external_tiers,
        _presets.driver_preset_names,
        _presets.driver_preset_info,
        _presets.driver_preset_provenance_category,
        _presets.get_driver_preset,
    ):
        loader.cache_clear()
    return str(matching_record.get("name", preset_name))

@lru_cache(maxsize=32768)
def _driver_preset_family(name: str) -> str:
    try:
        return _acoustics.driver_preset_info(name).brand
    except ValueError:
        return "Other"

@lru_cache(maxsize=32768)
def _driver_preset_identity_fields(name: str) -> tuple[str, str]:
    """Return the normalized manufacturer and part number shown at runtime."""
    try:
        info = _acoustics.driver_preset_info(name)
    except ValueError:
        return "Other", name
    manufacturer = info.brand.strip() or "Other"
    part_number = info.part_number.strip() or info.model.strip() or name
    return manufacturer, part_number

@lru_cache(maxsize=32768)
def _driver_preset_display_label(name: str) -> str:
    """Format a catalog key without exposing its source-decorated raw name."""
    manufacturer, part_number = _driver_preset_identity_fields(name)
    if manufacturer.casefold() == part_number.casefold():
        return manufacturer
    return f"{manufacturer} — {part_number}"

@lru_cache(maxsize=32768)
def _driver_preset_source(name: str) -> str:
    try:
        return _acoustics.driver_preset_provenance_category(name)
    except ValueError:
        return "Load Forge database"

def _available_driver_preset_names() -> list[str]:
    """Return driver preset names visible to the current user.

    Non-admin users are strictly restricted to the Load Forge proprietary catalog and Z Bench.
    Third-party aggregate databases (LSDB, VituixCAD, Speaker Box Lite) are accessible
    exclusively to administrators.
    """
    _acoustics.check_dynamic_catalog_freshness()
    names = _acoustics.driver_preset_names()
    if _maintenance_allowed():
        return names
    return [
        name for name in names
        if _driver_preset_source(name) not in _constants._RESTRICTED_THIRD_PARTY_SOURCES
    ]

@st.fragment(run_every=2)
def _poll_catalog_refresh() -> None:
    """Publish completed catalog refreshes while keeping network I/O off reruns."""
    if _acoustics.check_dynamic_catalog_freshness():
        st.rerun()

def _render_driver_mechanical_drawing(
    mechanical: _presets.MechanicalDimensions | None,
) -> None:
    """Render a compact, mobile-safe front/side driver envelope drawing."""
    if mechanical is None:
        st.caption("Mechanical dimensions not published for this driver.")
        return
    values = {
        "Overall Ø": mechanical.overall_diameter_mm,
        "Cutout Ø": mechanical.cutout_diameter_mm,
        "Depth": mechanical.depth_mm,
        "Bolt circle": mechanical.bolt_circle_mm,
        "Weight": mechanical.weight_kg,
    }
    shown = {label: value for label, value in values.items() if value is not None}
    if not shown:
        st.caption("Mechanical dimensions not published for this driver.")
        return
    metrics = st.columns(min(3, len(shown)))
    for column, (label, value) in zip(metrics * ((len(shown) + 2) // 3), shown.items()):
        unit = "kg" if label == "Weight" else "mm"
        column.metric(label, f"{value:.1f} {unit}")
    overall = mechanical.overall_diameter_mm or 100.0
    cutout = mechanical.cutout_diameter_mm or overall * 0.85
    scale = 150.0 / max(overall, 1.0)
    outer_r = overall * scale / 2.0
    inner_r = cutout * scale / 2.0
    st.markdown(
        f'''<div style="max-width:360px;margin:.6rem auto 0;text-align:center">
        <svg viewBox="0 0 360 210" width="100%" role="img" aria-label="Driver mechanical drawing">
          <rect x="1" y="1" width="358" height="208" rx="10" fill="#080b10" stroke="#26313d"/>
          <circle cx="105" cy="105" r="{outer_r:.1f}" fill="#151c25" stroke="#10b981" stroke-width="3"/>
          <circle cx="105" cy="105" r="{inner_r:.1f}" fill="#080b10" stroke="#f2c14e" stroke-width="2" stroke-dasharray="5 4"/>
          <line x1="{105-outer_r:.1f}" y1="180" x2="{105+outer_r:.1f}" y2="180" stroke="#b8c2cc"/>
          <text x="105" y="198" fill="#b8c2cc" text-anchor="middle" font-size="12">overall Ø / cutout Ø</text>
          <rect x="220" y="55" width="70" height="100" rx="4" fill="#151c25" stroke="#10b981" stroke-width="3"/>
          <line x1="305" y1="55" x2="305" y2="155" stroke="#f2c14e"/>
          <text x="310" y="110" fill="#b8c2cc" font-size="12" transform="rotate(90 310 110)">depth</text>
        </svg></div>''',
        unsafe_allow_html=True,
    )

def _driver_preset_exact_source(name: str) -> str:
    try:
        return _acoustics.driver_preset_info(name).source
    except ValueError:
        return "Built-in"

def _driver_class_label(value: str) -> str:
    """Return the compact class label shown throughout the UI."""
    return _constants._PRESET_CLASS_FILTER_ALIASES.get(str(value), str(value))

def _driver_preset_price(name: str) -> float | None:
    try:
        return _acoustics.driver_preset_info(name).price
    except ValueError:
        return None

def _driver_preset_currency(name: str) -> str:
    try:
        return _acoustics.driver_preset_info(name).currency
    except ValueError:
        return ""

@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def _current_exchange_rates() -> tuple[dict[str, float], str]:
    """Return current EUR-based ECB rates and their published reference date."""
    return _pricing.load_ecb_reference_rates()

def _normalized_preset_price(
    name: str, target_currency: str, rates: dict[str, float] | None = None
) -> float | None:
    # Callers iterating the full preset catalog must pass ``rates``: hitting
    # the st.cache_data-backed rates once per preset costs ~0.5 s of pure
    # cache overhead per rerun.
    if rates is None:
        rates, _ = _current_exchange_rates()
    return _pricing.convert_price(
        _driver_preset_price(name),
        _driver_preset_currency(name),
        target_currency,
        rates,
    )

def _all_preset_price_currencies() -> list[str]:
    return list(_acoustics.all_preset_price_currencies())

def _preset_price_currencies(names: list[str]) -> list[str]:
    all_names = _available_driver_preset_names()
    if len(names) == len(all_names):
        return _all_preset_price_currencies()
    return sorted(
        {
            _driver_preset_currency(name)
            for name in names
            if _driver_preset_price(name) is not None and _driver_preset_currency(name)
        }
    )

def _all_preset_price_values(currency: str | None = None) -> list[float]:
    rates = _current_exchange_rates()[0] if currency else None
    rates_tuple = tuple(sorted(rates.items())) if rates else ()
    return list(_acoustics.all_preset_price_values(currency or "", rates_tuple))

def _preset_price_values(names: list[str], currency: str | None = None) -> list[float]:
    all_names = _available_driver_preset_names()
    if len(names) == len(all_names):
        return _all_preset_price_values(currency)
    values = []
    rates = _current_exchange_rates()[0] if currency else None
    for name in names:
        price = (
            _normalized_preset_price(name, currency, rates)
            if currency
            else _driver_preset_price(name)
        )
        if price is not None and np.isfinite(float(price)):
            values.append(float(price))
    return values

def _purchase_markdown(info: _acoustics.DriverPresetInfo) -> str | None:
    """Return a markdown purchase link for a preset, or None without a URL."""
    if not info.url:
        return None
    host = info.url.split("//", 1)[-1].split("/", 1)[0].removeprefix("www.")
    if info.price is not None and np.isfinite(float(info.price)):
        label = f"Buy · {float(info.price):.2f} {info.currency}".rstrip() + f" · {host}"
    else:
        label = f"Buy · {host}"
    return f"[{label}]({info.url})"

def _size_bucket(size_in: float) -> str:
    if size_in <= 1.5:
        return "1 in"
    if size_in <= 2.5:
        return "2 in"
    if size_in <= 3.5:
        return "3 in"
    if size_in <= 4.5:
        return "4 in"
    if size_in <= 5.5:
        return "5 in"
    if size_in <= 7.0:
        return "6 in"
    if size_in <= 9.0:
        return "8 in"
    if size_in <= 11.0:
        return "10 in"
    if size_in <= 13.5:
        return "12 in"
    if size_in <= 16.5:
        return "15 in"
    if size_in <= 19.5:
        return "18 in"
    return "21 in"

@lru_cache(maxsize=32768)
def _driver_preset_size(name: str) -> str:
    try:
        info = _acoustics.driver_preset_info(name)
        if info.size_in is not None:
            return _size_bucket(info.size_in)
    except ValueError:
        pass
    lower = name.lower()
    if lower.startswith("turbosound ts-15"):
        return "15 in"
    if (
        lower.startswith("beyma 12")
        or lower.startswith("turbosound ts-12")
        or lower.startswith("sb audience bianco-12")
        or lower.startswith("lavoce wsf122")
        or "rss315" in lower
        or "30w/4558" in lower
    ):
        return "12 in"
    try:
        driver = _acoustics.get_driver_preset(name)
    except ValueError:
        return "Other"
    piston_diameter_mm = float(np.sqrt(driver.sd_cm2 / 10_000.0 * 4.0 / np.pi) * 1000.0)
    piston_inches = piston_diameter_mm / 25.4
    return _size_bucket(piston_inches)

def _all_available_preset_families() -> list[str]:
    present = set(_acoustics.all_preset_brands())
    ordered = [family for family in _constants._PRESET_FAMILY_ORDER if family == "All" or family in present]
    extras = sorted(present.difference(ordered), key=str.casefold)
    return [*ordered, *extras]

def _available_preset_families(names: list[str]) -> list[str]:
    all_names = _available_driver_preset_names()
    if len(names) == len(all_names):
        return _all_available_preset_families()
    present = {_driver_preset_family(name) for name in names}
    ordered = [family for family in _constants._PRESET_FAMILY_ORDER if family == "All" or family in present]
    extras = sorted(present.difference(ordered), key=str.casefold)
    return [*ordered, *extras]

def _set_filter_group_from_all(all_key: str, item_keys: tuple[str, ...]) -> None:
    """Apply the All checkbox value to every concrete option in a group."""
    selected = bool(st.session_state.get(all_key, False))
    for item_key in item_keys:
        st.session_state[item_key] = selected

def _sync_filter_group_all(all_key: str, item_keys: tuple[str, ...]) -> None:
    """Turn All on only when every concrete option is selected."""
    st.session_state[all_key] = bool(item_keys) and all(
        bool(st.session_state.get(item_key, False))
        for item_key in item_keys
    )

def _sync_filter_multiselect(
    filter_key: str,
    widget_key: str,
    synced_key: str,
) -> None:
    """Store a compact multiselect as the existing project filter format."""
    selected = [str(value) for value in st.session_state.get(widget_key, [])]
    aggregate = selected or ["All"]
    st.session_state[filter_key] = aggregate
    st.session_state[synced_key] = tuple(aggregate)

def _render_finder_library_filters(all_preset_names: list[str]) -> None:
    """Render Finder library filters."""
    col_search, col_refresh = st.columns([5, 1])
    with col_search:
        st.text_input(
            "Search preset",
            key="preset_search",
            placeholder="Manufacturer or part number",
        )
    with col_refresh:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button(
            "🔄",
            key="refresh_presets_btn_finder",
            help="Refresh driver library from cloud catalog & Z-Bench",
            use_container_width=True,
        ):
            _acoustics.invalidate_preset_caches()
            _acoustics.check_dynamic_catalog_freshness(force=True)
            st.rerun()
    is_admin = _maintenance_allowed()
    provenance_options = (
        list(_constants._PRESET_SOURCE_FILTERS)
        if is_admin
        else [opt for opt in _constants._PRESET_SOURCE_FILTERS if opt not in _constants._RESTRICTED_THIRD_PARTY_SOURCES]
    )
    filter_options = (
        ("preset_source_filter", "Provenance", provenance_options),
        (
            "preset_family_filter",
            "Manufacturer",
            _available_preset_families(all_preset_names),
        ),
        ("preset_size_filter", "Size", list(_constants._PRESET_SIZE_FILTERS)),
        ("preset_class_filter", "Class", list(_constants._PRESET_CLASS_FILTERS)),
    )
    if not _finder._show_advanced_controls():
        # Simple mode hides the expert catalog filters; clear any value they
        # still carry so a hidden filter cannot silently change the results.
        for hidden_key in (
            "preset_source_filter", "preset_size_filter", "preset_class_filter",
        ):
            st.session_state[hidden_key] = ["All"]
            st.session_state[f"{hidden_key}__select_v5"] = []
            st.session_state[f"{hidden_key}__select_v5__aggregate"] = ("All",)
        filter_options = tuple(
            option for option in filter_options
            if option[0] == "preset_family_filter"
        )
    for key, label, options in filter_options:
        raw_current = st.session_state.get(key, ["All"])
        current = [raw_current] if isinstance(raw_current, str) else list(raw_current)
        if key == "preset_source_filter":
            current = [
                _constants._PRESET_SOURCE_FILTER_ALIASES.get(str(option), str(option))
                for option in current
            ]
        elif key == "preset_class_filter":
            current = [
                _constants._PRESET_CLASS_FILTER_ALIASES.get(str(option), str(option))
                for option in current
            ]
        concrete_options = [option for option in options if option != "All"]
        selected = (
            []
            if not current or "All" in current or _constants._PRESET_FILTER_NONE in current
            else [option for option in current if option in concrete_options]
        )
        widget_key = f"{key}__select_v5"
        synced_key = f"{widget_key}__aggregate"
        requested_state = tuple(selected or ["All"])
        if st.session_state.get(synced_key) != requested_state:
            st.session_state[widget_key] = selected
            st.session_state[synced_key] = requested_state
        selected = st.multiselect(
            label,
            concrete_options,
            key=widget_key,
            placeholder="All",
            on_change=_sync_filter_multiselect,
            args=(key, widget_key, synced_key),
            help="Leave empty to include every option.",
        )
        aggregate = [str(value) for value in selected] or ["All"]
        st.session_state[key] = aggregate
        st.session_state[synced_key] = tuple(aggregate)
    if not _finder._show_advanced_controls():
        st.caption("Advanced filters (Provenance, Size, Class) are hidden.")

    preset_currencies = _preset_price_currencies(all_preset_names)
    if preset_currencies:
        if st.session_state["preset_price_currency"] not in preset_currencies:
            st.session_state["preset_price_currency"] = preset_currencies[0]
        st.selectbox("Price currency", preset_currencies, key="preset_price_currency")
        price_currency = str(st.session_state["preset_price_currency"])
        rates, rates_date = _current_exchange_rates()
        preset_prices = _preset_price_values(all_preset_names, price_currency)
        price_max_available = max(preset_prices)
        if st.session_state["preset_max_price"] <= 0.0:
            st.session_state["preset_max_price"] = float(price_max_available)
        st.session_state["preset_max_price"] = min(
            float(price_max_available),
            max(0.0, float(st.session_state["preset_max_price"])),
        )
        st.checkbox("Filter by max price", key="preset_price_enabled")
        if st.session_state["preset_price_enabled"]:
            st.number_input(
                f"Max price ({price_currency})",
                min_value=0.0,
                max_value=float(price_max_available),
                step=1.0,
                key="preset_max_price",
            )
        if len(preset_currencies) > 1:
            if rates and rates_date:
                st.caption(
                    f"Prices normalized to {price_currency} · ECB reference rates "
                    f"{rates_date}."
                )
            else:
                st.warning(
                    f"ECB rates unavailable: only prices already in "
                    f"{price_currency} can be compared."
                )
    else:
        st.session_state["preset_price_enabled"] = False
        st.checkbox("Filter by max price", key="preset_price_enabled", disabled=True)
        st.caption("Price unavailable in the current preset dataset.")

def _filter_driver_preset_names(
    names: list[str],
    *,
    source: str | list[str],
    family: str | list[str],
    size: str | list[str],
    search: str,
    max_price: float | None = None,
    max_price_currency: str | None = None,
    selected: str | None = None,
    driver_class: str | list[str] = "All",
    max_mms_g: float | None = None,
    max_le_mh: float | None = None,
) -> list[str]:
    def selected_values(value: str | list[str]) -> set[str]:
        values = {str(item) for item in ([value] if isinstance(value, str) else value)}
        return set() if not values or "All" in values else values

    is_admin = _maintenance_allowed()
    source_values = {
        _constants._PRESET_SOURCE_FILTER_ALIASES.get(value, value)
        for value in selected_values(source)
        if is_admin or _constants._PRESET_SOURCE_FILTER_ALIASES.get(value, value) not in _constants._RESTRICTED_THIRD_PARTY_SOURCES
    }
    family_values = selected_values(family)
    size_values = selected_values(size)
    class_values = {
        _constants._PRESET_CLASS_ENGINE_VALUES.get(value, value)
        for value in selected_values(driver_class)
    }
    query = search.strip().casefold()
    # The default view has no active filters.  Avoid touching every preset's
    # metadata on the first Streamlit run; names remain server-side and the
    # visible table is capped/paginated later.
    if not (
        source_values or family_values or size_values or class_values or query
        or max_price is not None or max_mms_g is not None or max_le_mh is not None
    ):
        if not is_admin:
            return [name for name in names if _driver_preset_source(name) not in _constants._RESTRICTED_THIRD_PARTY_SOURCES]
        return list(names)
    rates = _current_exchange_rates()[0] if max_price is not None else None
    filtered = []
    for name in names:
        source_name = _driver_preset_source(name)
        if not is_admin and source_name in _constants._RESTRICTED_THIRD_PARTY_SOURCES:
            continue
        if source_values and source_name not in source_values:
            continue
        if family_values and _driver_preset_family(name) not in family_values:
            continue
        if size_values and _driver_preset_size(name) not in size_values:
            continue
        if class_values and _driver_preset_class(name) not in class_values:
            continue
        if query:
            manufacturer, part_number = _driver_preset_identity_fields(name)
            searchable = " ".join((name, manufacturer, part_number)).casefold()
            if query not in searchable:
                continue
        if max_mms_g is not None or max_le_mh is not None:
            try:
                driver = _acoustics.get_driver_preset(name)
            except Exception:
                continue
            if max_mms_g is not None:
                mms_g = driver.mms_g
                if (
                    mms_g is None
                    or not np.isfinite(float(mms_g))
                    or float(mms_g) <= 0.0
                    or float(mms_g) > float(max_mms_g)
                ):
                    continue
            if max_le_mh is not None:
                le_mh = driver.le_mh
                if (
                    not np.isfinite(float(le_mh))
                    or float(le_mh) <= 0.0
                    or float(le_mh) > float(max_le_mh)
                ):
                    continue
        if max_price is not None:
            price = _normalized_preset_price(name, str(max_price_currency or ""), rates)
            if price is None or float(price) > float(max_price):
                continue
        filtered.append(name)
    if selected and selected != "Custom" and selected in names and selected not in filtered:
        filtered.insert(0, selected)
    return filtered

def _sync_finder_library_selection(filtered_preset_names: list[str]) -> None:
    """Drop table row selections that belong to a previous filtered pool."""
    state = st.session_state.get("finder_driver_library_table")
    if not isinstance(state, dict):
        return
    shown_count = min(len(filtered_preset_names), _constants._LIBRARY_TABLE_MAX_ROWS)
    selection = state.get("selection")
    if not isinstance(selection, dict):
        return
    rows = selection.get("rows", [])
    valid_rows = [
        row for row in rows
        if isinstance(row, int) and 0 <= row < shown_count
    ]
    if valid_rows != rows:
        state["selection"] = {**selection, "rows": valid_rows}
        st.session_state["finder_driver_library_table"] = state

def _driver_preset_class(name: str) -> str:
    # functools.cache would restart cold on every Streamlit rerun (this whole
    # script is re-executed, redefining the function); the session_state dict
    # survives reruns so the 10k-preset catalog is classified once per session.
    class_cache = st.session_state.setdefault("_driver_class_cache", {})
    cached = class_cache.get(name)
    if cached is None:
        try:
            cached = _acoustics.classify_driver_bandwidth(
                _acoustics.get_driver_preset(name)).driver_class
        except Exception:
            cached = "Woofer"
        class_cache[name] = cached
    return cached

def _apply_driver_preset(driver: _acoustics.DriverTS):
    st.session_state["driver_fs_hz"] = float(driver.fs_hz)
    st.session_state["driver_vas_l"] = float(driver.vas_l)
    st.session_state["driver_qts"] = float(driver.qts)
    st.session_state["driver_qms"] = float(driver.qms)
    st.session_state["driver_re_ohm"] = float(driver.re_ohm)
    st.session_state["driver_sd_mode"] = "Sd"
    st.session_state["driver_sd_cm2"] = float(driver.sd_cm2)
    st.session_state["driver_diameter_mm"] = float(np.sqrt(driver.sd_cm2 / 10_000.0 * 4.0 / np.pi) * 1000.0)
    st.session_state["driver_le_mh"] = float(driver.le_mh)
    st.session_state["driver_le10k_mh"] = float(driver.le10k_mh or 0.0)
    st.session_state["driver_xmax_mm"] = float(driver.xmax_mm)
    st.session_state["driver_pe_w"] = float(driver.pe_w)
    st.session_state["driver_mms_g"] = float(driver.mms_g or 0.0)
    st.session_state["driver_cms_mm_n"] = float(driver.cms_mm_per_n or 0.0)
    st.session_state["driver_bl_tm"] = float(driver.bl_tm or 0.0)

def _on_driver_preset_change():
    preset_name = st.session_state.get("driver_preset_name", "Custom")
    if preset_name == "Custom":
        st.session_state.pop("_admin_catalog_source_preset", None)
        return
    try:
        _apply_driver_preset(_acoustics.get_driver_preset(preset_name))
        st.session_state["_admin_catalog_source_preset"] = preset_name
        # Re-read through the configuration so multi-driver setups get a box
        # sized for the composite Vas/Sd, not the single unit.
        composite = _state._driver_from_state()
        if _state._box_strategy_is_auto():
            _optimizer._apply_suggested_box_for(composite)
            _finder._mark_auto_alignment_synced(composite)
    except Exception:
        _runtime.logger.exception("Could not apply driver preset")

def _finder_price_currency(df: pd.DataFrame) -> str:
    """Currency used for value ranking: sidebar choice, else the most common."""
    priced = df[df["Price"].notna() & df["Currency"].astype(bool)]
    if priced.empty:
        return ""
    currencies = priced["Currency"].astype(str)
    sidebar = str(st.session_state.get("preset_price_currency", "EUR"))
    if sidebar and (currencies == sidebar).any():
        return sidebar
    return str(currencies.mode().iloc[0])

def _value_sorted_frame(df: pd.DataFrame, currency: str) -> pd.DataFrame:
    """Sort by F3 × price in one currency; rows without it keep F3 order below."""
    scored = df.copy()
    scored["Value"] = [
        _acoustics.price_extension_score(
            f3, price if str(cur) == currency else float("nan"))
        for f3, price, cur in zip(
            scored["F3 Hz"], scored["Price"], scored["Currency"], strict=True)
    ]
    scored = scored.sort_values(
        ["Value", "F3 Hz"], kind="stable").reset_index(drop=True)
    scored["Value"] = scored["Value"].replace(np.inf, np.nan)
    return scored

def _normalize_price_frame(df: pd.DataFrame, target_currency: str) -> pd.DataFrame:
    """Return a copy whose available prices share one display currency."""
    normalized = df.copy()
    rates, _ = _current_exchange_rates()
    converted = [
        _pricing.convert_price(price, source, target_currency, rates)
        for price, source in zip(
            normalized["Price"], normalized["Currency"], strict=True
        )
    ]
    normalized["Price"] = [
        value if value is not None else np.nan for value in converted
    ]
    normalized["Currency"] = [
        target_currency if value is not None else "" for value in converted
    ]
    return normalized

def _finder_load_context() -> tuple[list[str], bool]:
    """Return active Finder loads and whether infinite baffle is the only one."""
    finder_load_types = list(st.session_state.get("finder_load_types", []))
    if not finder_load_types:
        finder_load_types = [str(st.session_state.get("load_type", "DCCAV"))]
    return finder_load_types, finder_load_types == ["Infinite baffle"]

def _finder_result_context_signature(_preset_names: list[str]) -> str:
    """Identify user inputs that can change a Bass Match result set.

    The live catalog and price-file mtimes are deliberately excluded: their
    background refresh must not make a completed result table disappear while
    the user selects a row. A later Run Bass Match always reads fresh data.
    """
    finder_load_types, _ = _finder_load_context()
    context = {
        "ranking_version": _constants._FINDER_RANKING_VERSION,
        "load_types": finder_load_types,
        "volume_l": float(_state._finder_value("finder_volume_l")),
        "driver_configuration": str(
            _state._finder_value("finder_driver_configuration")
        ),
        "objective": str(_state._finder_value("finder_objective")),
        "search_profile": str(_state._finder_value("finder_search_profile")),
        "reflex_resonator_type": str(
            _state._finder_value("finder_reflex_resonator_type")
        ),
        "voltage_v": float(_state._finder_value("finder_voltage")),
        "max_ripple_db": float(_state._finder_value("finder_max_ripple_db")),
        "max_excursion_ratio": float(
            _state._finder_value("finder_excursion_ratio")
        ),
        "max_group_delay_ms": float(_state._finder_value("finder_max_gd_ms")),
        "min_spl_db": float(_state._finder_value("finder_min_spl_db")),
        "min_mol_f3_db": float(_state._finder_value("finder_min_mol_f3_db")),
        "max_f3_hz": float(_state._finder_value("finder_max_f3_hz")),
        "max_mms_g": float(_state._finder_value("finder_max_mms_g")),
        "max_le_mh": float(_state._finder_value("finder_max_le_mh")),
        "f_min_hz": float(_state._finder_value("finder_f_min")),
        "f_max_hz": float(_state._finder_value("finder_f_max")),
        "points": int(_state._finder_value("finder_points")),
        "preset_search": str(st.session_state.get("preset_search", "")),
        "preset_source_filter": _state._json_safe(
            st.session_state.get("preset_source_filter", ["All"])
        ),
        "preset_family_filter": _state._json_safe(
            st.session_state.get("preset_family_filter", ["All"])
        ),
        "preset_size_filter": _state._json_safe(
            st.session_state.get("preset_size_filter", ["All"])
        ),
        "preset_class_filter": _state._json_safe(
            st.session_state.get("preset_class_filter", ["All"])
        ),
        "preset_price_enabled": bool(
            st.session_state.get("preset_price_enabled", False)
        ),
        "preset_max_price": float(
            st.session_state.get("preset_max_price", 0.0) or 0.0
        ),
        "preset_price_currency": str(
            st.session_state.get("preset_price_currency", "EUR")
        ),
    }
    encoded = json.dumps(
        context,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

def _finder_controls_signature() -> str:
    """Identify Finder controls without ephemeral table-row selection state."""
    context = {
        key: _state._json_safe(st.session_state.get(key, default))
        for key, default in _constants._FINDER_DEFAULTS.items()
    }
    for key, default in {
        "finder_load_types": [],
        "preset_search": "",
        "preset_source_filter": ["All"],
        "preset_family_filter": ["All"],
        "preset_size_filter": ["All"],
        "preset_class_filter": ["All"],
        "preset_price_enabled": False,
        "preset_max_price": 0.0,
        "preset_price_currency": "EUR",
    }.items():
        context[key] = _state._json_safe(st.session_state.get(key, default))
    encoded = json.dumps(
        context,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

def _filter_finder_performance_rows(
    rows: list[dict],
    min_spl_db: float,
    min_mol_f3_db: float,
    max_f3_hz: float,
    max_ripple_db: float = 0.0,
) -> list[dict]:
    """Apply Finder's hard output constraints to simulated candidate rows."""
    filtered = rows
    if min_spl_db > 0.0:
        filtered = [
            row for row in filtered
            if np.isfinite(float(row.get("Peak dB", np.nan)))
            and float(row["Peak dB"]) >= min_spl_db
        ]
    if min_mol_f3_db > 0.0:
        filtered = [
            row for row in filtered
            if np.isfinite(float(row.get("MOL @ F3 dB", np.nan)))
            and float(row["MOL @ F3 dB"]) >= min_mol_f3_db
        ]
    if max_f3_hz > 0.0:
        filtered = [
            row for row in filtered
            if np.isfinite(float(row.get("F3 Hz", np.nan)))
            and float(row["F3 Hz"]) <= max_f3_hz
        ]
    if max_ripple_db > 0.0:
        filtered = [
            row for row in filtered
            if not np.isfinite(float(row.get("Ripple dB", np.nan)))
            or float(row["Ripple dB"]) <= max_ripple_db + 1e-6
        ]
    return filtered

def _finder_candidate_precheck(
    ts: _acoustics.DriverTS,
    load_type: str,
    voltage_v: float,
    min_spl_db: float,
    max_ripple_db: float,
    max_f3_hz: float = 0.0,
    min_mol_f3_db: float = 0.0,
    max_volume_l: float = 0.0,
    fast_prefilter: bool = True,
) -> str | None:
    """Return why a candidate can be rejected before enclosure simulation."""
    return _acoustics.candidate_precheck(
        ts, load_type, voltage_v, min_spl_db, max_ripple_db,
        max_f3_hz=max_f3_hz, min_mol_f3_db=min_mol_f3_db,
        max_volume_l=max_volume_l, fast_prefilter=fast_prefilter,
    )

def _finder_driver_identity(name: str) -> tuple[str, str, str]:
    """Return one physical brand/model/impedance identity across catalogs."""
    return _acoustics.driver_preset_identity(name)

def _finder_preset_preference(name: str) -> tuple[int, int, float, str]:
    """Prefer Load Forge provenance, then an available lower price."""
    return _acoustics.driver_preset_preference(name)

def _deduplicate_finder_preset_names_tuple(
    preset_names: tuple[str, ...],
) -> tuple[tuple[str, ...], int]:
    """Choose one preferred catalog record for each physical driver."""
    return _acoustics.deduplicate_driver_preset_names(preset_names)

def _deduplicate_finder_preset_names(
    preset_names: list[str],
) -> tuple[list[str], int]:
    """Choose one preferred catalog record for each physical driver."""
    unique_tuple, duplicate_count = _acoustics.deduplicate_driver_preset_names(
        tuple(preset_names)
    )
    return list(unique_tuple), duplicate_count

def _deduplicate_finder_result_rows(
    rows: list[dict],
) -> tuple[list[dict], int]:
    """Keep one preferred catalog result per physical driver, load topology and resonator."""
    unique_rows: list[dict] = []
    seen: set[tuple[tuple[str, str, str], str, str]] = set()
    for row in rows:
        identity = _finder_driver_identity(str(row.get("Driver", "")))
        load_type = str(row.get("Load", ""))
        resonator = str(row.get("Resonator", ""))
        key = (identity, load_type, resonator)
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows, len(rows) - len(unique_rows)

def _prefilter_finder_candidate_pools(
    preset_names: tuple[str, ...],
    load_types: tuple[str, ...],
    voltage_v: float,
    min_spl_db: float,
    max_ripple_db: float,
    max_f3_hz: float,
    min_mol_f3_db: float,
    max_volume_l: float,
    fast_prefilter: bool,
    driver_configuration: str,
    pool_fingerprint: tuple = (),
) -> tuple[tuple[tuple[str, tuple[str, ...]], ...], dict[str, int]]:
    """Build per-load candidate pools using only pre-simulation information."""
    return _acoustics.prefilter_finder_candidate_pools(
        preset_names,
        load_types,
        voltage_v,
        min_spl_db,
        max_ripple_db,
        max_f3_hz,
        min_mol_f3_db,
        max_volume_l,
        fast_prefilter,
        driver_configuration,
        pool_fingerprint=pool_fingerprint,
    )

def _finder_prefilter(
    preset_names: list[str],
) -> tuple[dict[str, list[str]], dict[str, int]]:
    """Return current per-load pools and their pre-simulation counts."""
    finder_load_types, _ = _finder_load_context()
    unique_names, duplicate_rows = _deduplicate_finder_preset_names(
        preset_names
    )
    pool_rows, stats = _prefilter_finder_candidate_pools(
        tuple(unique_names),
        tuple(finder_load_types),
        float(_state._finder_value("finder_voltage")),
        float(st.session_state.get("finder_min_spl_db", 0.0) or 0.0),
        float(st.session_state.get("finder_max_ripple_db", 0.0) or 0.0),
        float(st.session_state.get("finder_max_f3_hz", 0.0) or 0.0),
        float(st.session_state.get("finder_min_mol_f3_db", 0.0) or 0.0),
        float(_state._finder_value("finder_volume_l")),
        bool(st.session_state.get("finder_fast_prefilter", True)),
        str(_state._finder_value("finder_driver_configuration")),
        _finder._finder_pool_fingerprint(1),
    )
    duplicate_simulations = duplicate_rows * len(finder_load_types)
    stats = {
        **stats,
        "input_drivers": len(preset_names),
        "unique_drivers": len(unique_names),
        "duplicate_rows": duplicate_rows,
        "total_simulations": (
            stats["total_simulations"] + duplicate_simulations
        ),
        "rejected_simulations": (
            stats["rejected_simulations"] + duplicate_simulations
        ),
        "duplicate_simulations": duplicate_simulations,
    }
    return {
        load_type: list(names)
        for load_type, names in pool_rows
    }, stats

@st.cache_data(show_spinner=False)
def _driver_coverage_summary(preset_names: tuple[str, ...]) -> dict[str, int]:
    """Per-field coverage percentages across the filtered catalog."""
    counts = {label: 0 for label in _acoustics.DRIVER_COVERAGE_LABELS}
    total = 0
    for name in preset_names:
        try:
            info = _acoustics.driver_preset_info(name)
            ts = _acoustics.get_driver_preset(name)
        except Exception:
            continue
        total += 1
        for label in _acoustics.driver_data_coverage(
            ts, info.size_in, info.price
        )["missing"]:
            counts[label] = counts.get(label, 0) + 1
    if not total:
        return {}
    return {
        "Drivers": total,
        **{
            label: int(round(100.0 * (total - missing) / total))
            for label, missing in counts.items()
        },
    }

def _refresh_finder_result_catalog_metadata(rows: object) -> list[dict]:
    """Fill metadata gaps in saved Finder rows from the current catalog.

    Finder results are persisted in projects and Streamlit session state, so
    rows calculated before a catalog-metadata fix can outlive the code that
    produced them.  Refreshing nominal size is safe without re-simulating: it
    is display/filter metadata and does not enter the acoustic solver.
    """
    if not isinstance(rows, (list, tuple)):
        return []
    refreshed: list[dict] = []
    for saved in rows:
        if not isinstance(saved, dict):
            continue
        row = dict(saved)
        if _state._table_value_missing(row.get("Size in")):
            try:
                size_in = _acoustics.driver_preset_info(
                    str(row.get("Driver", ""))
                ).size_in
            except ValueError:
                size_in = None
            if size_in is not None:
                row["Size in"] = float(size_in)
        if row.get("_driver_ts"):
            try:
                coverage = _acoustics.driver_data_coverage(
                    _acoustics.DriverTS(**row["_driver_ts"]),
                    row.get("Size in"),
                    row.get("Price"),
                )
            except Exception:
                coverage = None
            if coverage is not None:
                row["Data"] = coverage["status"]
                row["Data %"] = coverage["score"]
                row["_data_missing"] = coverage["missing"]
        refreshed.append(row)
    return refreshed

@st.cache_data(show_spinner=False)
def _driver_library_frame(
    # Cache busted to reflect nominal-size preservation in imported catalogs.
    preset_names: tuple[str, ...],
    target_currency: str = "",
    exchange_rates: tuple[tuple[str, float], ...] = (),
    catalog_revision: int = 0,
) -> pd.DataFrame:
    """Build the complete filtered driver library table once per filter set."""
    del catalog_revision  # Cache identity includes refreshed cloud metadata.
    rates = dict(exchange_rates)
    rows = []
    for name in preset_names:
        try:
            info = _acoustics.driver_preset_info(name)
            ts_p = _acoustics.get_driver_preset(name)
            ref = _acoustics.driver_reference_metrics(ts_p)
            price = (
                _pricing.convert_price(
                    info.price, info.currency, target_currency, rates
                )
                if target_currency
                else info.price
            )
            rows.append({
                "Driver": name,
                "Manufacturer": info.brand,
                "Part number": info.part_number or info.model or name,
                "Nominal in": info.size_in,
                "Sd cm²": ts_p.sd_cm2,
                "Effective Ø in": (
                    np.sqrt(4.0 * ts_p.sd_cm2 / np.pi) / 2.54
                ),
                "Fs Hz": ts_p.fs_hz,
                "Qts": ts_p.qts,
                "Vas L": ts_p.vas_l,
                "SPL dB": ref.spl_2v83_db,
                "Price": price if price is not None else np.nan,
                "Currency": (
                    target_currency if target_currency and price is not None
                    else info.currency if not target_currency and price is not None
                    else ""
                ),
                "Category": _driver_preset_source(name),
                "Source": info.source,
            })
        except Exception:
            manufacturer, part_number = _driver_preset_identity_fields(name)
            rows.append({
                "Driver": name,
                "Manufacturer": manufacturer,
                "Part number": part_number,
            })
    library_columns = [
        "Driver", "Manufacturer", "Part number", "Nominal in", "Sd cm²",
        "Effective Ø in",
        "Fs Hz", "Qts", "Vas L", "SPL dB",
        "Price", "Currency", "Category", "Source",
    ]
    if not rows:
        return pd.DataFrame(columns=(
            *library_columns,
        ))
    display = _state._clean_display_table_frame(pd.DataFrame(rows))
    if "Price" not in display:
        display["Price"] = np.nan
    if "Currency" not in display:
        display["Currency"] = ""
    return display[[name for name in library_columns if name in display]]

def _selected_library_preset_names(
    filtered_preset_names: list[str],
) -> list[str]:
    """Return the currently selected rows from the visible candidate pool."""
    shown_names = filtered_preset_names[:_constants._LIBRARY_TABLE_MAX_ROWS]
    table_state = st.session_state.get("finder_driver_library_table")
    if not isinstance(table_state, dict):
        return []
    selected_rows = table_state.get("selection", {}).get("rows", [])
    return [
        shown_names[index]
        for index in selected_rows
        if isinstance(index, int) and 0 <= index < len(shown_names)
    ]

def _finder_filter_summary(
    key: str,
    aliases: dict[str, str] | None = None,
) -> str:
    """Return a compact, truthful summary for one library filter group."""
    raw_value = st.session_state.get(key, ["All"])
    values = [raw_value] if isinstance(raw_value, str) else list(raw_value)
    if not values or "All" in values:
        return "Any"
    if _constants._PRESET_FILTER_NONE in values:
        return "None"
    normalized = [
        (aliases or {}).get(str(value), str(value))
        for value in values
    ]
    if len(normalized) <= 2:
        return " + ".join(normalized)
    return f"{len(normalized)} selected"

def _finder_brief_constraints(
    selected_preset_count: int,
) -> list[tuple[str, str]]:
    """Expose every operative Bass Match input in the compact main brief."""
    finder_load_types, only_infinite_baffle = _finder_load_context()
    uses_reflex = "Bass reflex" in finder_load_types
    uses_pr = uses_reflex and _state._reflex_uses_passive_radiator(finder=True)
    only_pr = finder_load_types == ["Bass reflex"] and uses_pr
    optimizer_applies = not only_infinite_baffle and not only_pr

    display_loads = [
        "Reflex (PR)" if item == "Bass reflex" and uses_pr else item
        for item in finder_load_types
    ]
    load_summary = (
        " + ".join(display_loads)
        if len(display_loads) <= 2
        else f"{len(display_loads)} selected"
    )

    def upper_limit(key: str, unit: str, *, off_at_zero: bool = True) -> str:
        value = float(_state._finder_value(key))
        if off_at_zero and value <= 0.0:
            return "Off"
        return f"≤ {value:g} {unit}"

    def lower_limit(key: str, unit: str) -> str:
        value = float(_state._finder_value(key))
        return "Off" if value <= 0.0 else f"≥ {value:g} {unit}"

    search_query = str(st.session_state.get("preset_search", "")).strip()
    price_enabled = bool(st.session_state.get("preset_price_enabled", False))
    price_currency = str(st.session_state.get("preset_price_currency", "EUR"))
    max_price = float(st.session_state.get("preset_max_price", 0.0) or 0.0)
    objective = str(_state._finder_value("finder_objective"))
    if not optimizer_applies:
        objective = "N/A"
    elif uses_pr:
        objective = f"{objective} · PR starter"

    constraints = [
        ("Loads", load_summary),
        ("Configuration", str(_state._finder_value("finder_driver_configuration"))),
        (
            "Resonator",
            str(_state._finder_value("finder_reflex_resonator_type"))
            if uses_reflex else "N/A",
        ),
        (
            "Maximum box",
            "N/A" if only_infinite_baffle
            else upper_limit("finder_volume_l", "L", off_at_zero=False),
        ),
        ("Voltage", f"{float(_state._finder_value('finder_voltage')):g} V"),
        ("Optimization", objective),
        ("Minimum SPL", lower_limit("finder_min_spl_db", "dB")),
        ("Minimum MOL @ F3", lower_limit("finder_min_mol_f3_db", "dB")),
        ("Maximum F3", upper_limit("finder_max_f3_hz", "Hz")),
        (
            "Maximum ripple",
            upper_limit("finder_max_ripple_db", "dB", off_at_zero=False)
            if optimizer_applies else "N/A",
        ),
        (
            "Maximum excursion",
            upper_limit("finder_excursion_ratio", "× Xmax")
            if optimizer_applies else "N/A",
        ),
        (
            "Maximum delay",
            upper_limit("finder_max_gd_ms", "ms")
            if optimizer_applies else "N/A",
        ),
        ("Maximum Mms", upper_limit("finder_max_mms_g", "g")),
        ("Maximum Le", upper_limit("finder_max_le_mh", "mH")),
        ("Search", search_query or "Any"),
        (
            "Provenance",
            _finder_filter_summary(
                "preset_source_filter",
                _constants._PRESET_SOURCE_FILTER_ALIASES,
            ),
        ),
        ("Manufacturer", _finder_filter_summary("preset_family_filter")),
        ("Size", _finder_filter_summary("preset_size_filter")),
        (
            "Class",
            _finder_filter_summary(
                "preset_class_filter",
                _constants._PRESET_CLASS_FILTER_ALIASES,
            ),
        ),
        (
            "Maximum price",
            f"≤ {max_price:g} {price_currency}".strip()
            if price_enabled else "Off",
        ),
        (
            "Evaluation range",
            f"{float(_state._finder_value('finder_f_min')):g}–"
            f"{float(_state._finder_value('finder_f_max')):g} Hz",
        ),
        ("Profile", str(_state._finder_value("finder_search_profile"))),
        ("Resolution", f"{int(_state._finder_value('finder_points'))} points"),
        ("Results shown", "All usable"),
        (
            "Candidate pool",
            f"{selected_preset_count} selected"
            if selected_preset_count else "All filtered",
        ),
    ]
    return constraints

def _render_finder_constraint_grid(
    constraints: list[tuple[str, str]],
) -> None:
    cards = "".join(
        "<div class='finder-constraint' "
        f"title='{html.escape(label)}: {html.escape(value)}'>"
        f"<div class='finder-constraint-label'>{html.escape(label)}</div>"
        f"<div class='finder-constraint-value'>{html.escape(value)}</div>"
        "</div>"
        for label, value in constraints
    )
    st.markdown(
        f"<div class='finder-constraint-grid'>{cards}</div>",
        unsafe_allow_html=True,
    )

@st.cache_data(show_spinner=False)
def _passive_radiator_library_frame(search: str = "") -> pd.DataFrame:
    rows = []
    for name in _acoustics.passive_radiator_preset_names():
        pr = _acoustics.get_passive_radiator_preset(name)
        if search:
            query = search.casefold().strip()
            if (
                query not in pr.name.casefold()
                and query not in pr.brand.casefold()
                and query not in pr.model.casefold()
            ):
                continue
        rows.append({
            "Radiator": pr.name,
            "Brand": pr.brand,
            "Model": pr.model,
            "Sp cm²": pr.sp_cm2,
            "Fp Hz": pr.fp_hz,
            "Qmp": pr.qmp,
            "Mmp g": pr.mmp_g,
            "Xmax mm": pr.xmax_mm,
            "Source": pr.source,
            "URL": pr.url,
        })
    columns = [
        "Radiator", "Brand", "Model", "Sp cm²", "Fp Hz", "Qmp", "Mmp g", "Xmax mm", "Source", "URL",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)

def _render_passive_radiator_library() -> None:
    """Render the catalog of passive radiators in a selectable table."""
    st.caption(
        "Select one passive radiator to apply it directly to Box Design (Bass reflex + PR resonator)."
    )
    search_val = st.text_input(
        "Filter passive radiators",
        key="finder_pr_library_search",
        placeholder="Search brand or model (Dayton, SB Acoustics, PURIFI, SEAS, ...)",
    )
    pr_df = _passive_radiator_library_frame(search_val)
    st.caption(f"{len(pr_df)} passive radiators available in the catalog.")
    table_state = st.dataframe(
        pr_df,
        width="stretch",
        height=680,
        hide_index=True,
        key="finder_pr_library_table",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Radiator": None,
            "Sp cm²": st.column_config.NumberColumn("Sp (cm²)", format="%.1f"),
            "Fp Hz": st.column_config.NumberColumn("Fp (Hz)", format="%.1f"),
            "Qmp": st.column_config.NumberColumn("Qmp", format="%.2f"),
            "Mmp g": st.column_config.NumberColumn("Mmp (g)", format="%.1f"),
            "Xmax mm": st.column_config.NumberColumn("Xmax (mm)", format="%.1f"),
            "URL": st.column_config.LinkColumn("Product Link"),
        },
    )
    selected_rows = getattr(table_state.selection, "rows", []) if table_state else []
    if not selected_rows:
        with st.container(key="emerald_info_pr_library_selection"):
            st.info("Select a passive radiator row to apply it to Box Design.")
        return

    selected_index = int(selected_rows[0])
    if not 0 <= selected_index < len(pr_df):
        return
    selected_name = str(pr_df.iloc[selected_index]["Radiator"])
    st.button(
        f"Apply {selected_name} to Box Design",
        type="primary",
        width="stretch",
        key="finder_use_library_pr",
        on_click=_finder._apply_library_pr,
        args=(selected_name,),
    )

def _render_driver_library(filtered_preset_names: list[str]) -> None:
    """Render every filtered driver in a scrollable, selectable library."""
    cat_mode = st.radio(
        "Library Catalog",
        ["Loudspeaker Drivers", f"Passive Radiators ({len(_acoustics.passive_radiator_preset_names())})"],
        horizontal=True,
        key="finder_library_catalog_tab",
    )
    if cat_mode and "Passive Radiators" in cat_mode:
        _render_passive_radiator_library()
        return

    st.caption(
        "Select one driver to open it directly in Box Design, or select "
        "several to limit the next Bass Match run."
    )

    # Re-serializing the full 10k-row catalog to the browser on every rerun
    # (each row selection or widget change) costs seconds of frontend time;
    # cap the table and let search/filters narrow the rest.
    shown_names = filtered_preset_names[:_constants._LIBRARY_TABLE_MAX_ROWS]

    if not filtered_preset_names:
        st.warning("No drivers match the current search and filters.")
        st.button(
            "Reset candidate filters",
            type="primary",
            width="stretch",
            key="finder_reset_candidate_filters",
            on_click=_state._reset_candidate_filters,
            help="Clear search, catalog, price, Mms and Le filters.",
        )
        return

    if len(shown_names) < len(filtered_preset_names):
        st.caption(
            f"{len(filtered_preset_names)} presets match the current filters · "
            f"showing the first {len(shown_names)}. Use search or Library "
            "filters to narrow the list."
        )
    else:
        st.caption(
            f"{len(filtered_preset_names)} drivers match the current filters. "
            "Scroll the table to browse the complete list."
        )
    price_currency = str(st.session_state.get("preset_price_currency", "EUR"))
    rates, rates_date = _current_exchange_rates()
    library_df = _driver_library_frame(
        tuple(shown_names),
        price_currency,
        tuple(sorted(rates.items())),
        _presets._CATALOG_CACHE_REVISION,
    )
    if price_currency:
        rate_note = f" · ECB {rates_date}" if rates_date else ""
        st.caption(f"Library prices shown in {price_currency}{rate_note}.")
    table_state = st.dataframe(
        library_df,
        width="stretch",
        height=720,
        hide_index=True,
        key="finder_driver_library_table",
        on_select="rerun",
        selection_mode="multi-row",
        column_config={
            "Driver": None,
            "Nominal in": st.column_config.NumberColumn("Nominal Ø (in)", format="%.1f"),
            "Size in": st.column_config.NumberColumn(format="%.1f"),
            "Fs Hz": st.column_config.NumberColumn(format="%.1f"),
            "Qts": st.column_config.NumberColumn(format="%.3f"),
            "Vas L": st.column_config.NumberColumn(format="%.1f"),
            "SPL dB": st.column_config.NumberColumn(format="%.0f"),
            "Price": st.column_config.NumberColumn(
                f"Price ({price_currency})" if price_currency else "Price",
                format="%.2f",
            ),
            "Currency": None,
        },
    )
    
    selected_rows = getattr(table_state.selection, "rows", []) if table_state else []
    if not selected_rows:
        with st.container(key="emerald_info_library_selection"):
            st.info(
                "No pool limit selected. Bass Match will evaluate every driver "
                "allowed by the Library filters."
            )
        return
        
    if len(selected_rows) > 1:
        with st.container(key="emerald_info_library_multi_selection"):
            st.info(
                f"{len(selected_rows)} drivers selected. Run Bass Match above "
                "to rank only this pool."
            )
        return
        
    selected_index = int(selected_rows[0])
    if not 0 <= selected_index < len(library_df):
        return
    selected_name = str(library_df.iloc[selected_index]["Driver"])
    st.button(
        f"Open {_driver_preset_display_label(selected_name)} in Box Design",
        type="primary",
        width="stretch",
        key="finder_use_library_driver",
        on_click=_finder._apply_library_driver,
        args=(selected_name,),
    )
