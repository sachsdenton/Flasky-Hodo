"""Persistent archive of saved VAD loops.

Each archive is a folder on disk containing the raw VAD files and a
``manifest.json`` describing the snapshot context (site, METAR, storm
motion, frame list).  The on-disk layout is::

    data/archives/
        KCRP/                                      # VAD site code
            2026-04-30_1954Z_VAD_KNQI/             # archive_id
                manifest.json
                <original_vad_filename_1>
                <original_vad_filename_2>
                ...

When METAR is omitted, the trailing ``_KNQI`` is dropped from the folder
name.  Folder names are derived from the *newest* frame's valid time so
multiple snapshots taken minutes apart still produce distinct ids.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

ARCHIVE_ROOT = os.path.join("data", "archives")

# Filesystem operations are guarded by a single coarse lock. The number of
# saves/loads is small and the operations are short, so contention isn't a
# concern.
_archive_lock = threading.Lock()

_SAFE_TOKEN = re.compile(r"[^A-Za-z0-9_\-]")


def _safe(token: str) -> str:
    """Strip anything but alphanumerics, underscore, hyphen from ``token``."""
    return _SAFE_TOKEN.sub("", token or "")


def _ensure_root() -> None:
    os.makedirs(ARCHIVE_ROOT, exist_ok=True)


def _archive_dir(site_id: str, archive_id: str) -> str:
    return os.path.join(ARCHIVE_ROOT, _safe(site_id), _safe(archive_id))


def _manifest_path(site_id: str, archive_id: str) -> str:
    return os.path.join(_archive_dir(site_id, archive_id), "manifest.json")


def _load_manifest(site_id: str, archive_id: str) -> Optional[Dict[str, Any]]:
    p = _manifest_path(site_id, archive_id)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r") as fh:
            return json.load(fh)
    except Exception:
        return None


def build_archive_id(newest_valid_time: datetime, metar_station: Optional[str]) -> str:
    """Build the canonical archive folder name.

    Format: ``{YYYY-MM-DD}_{HHMM}Z_VAD[_{METAR}]``.
    """
    base = newest_valid_time.strftime("%Y-%m-%d_%H%MZ_VAD")
    if metar_station:
        return f"{base}_{_safe(metar_station.upper())}"
    return base


def save_archive(
    site_id: str,
    frames: List[Dict[str, Any]],
    metar: Optional[Dict[str, Any]],
    storm_motion: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Persist ``frames`` (list of ``{file_id, valid_time, cached_path}``
    dicts) as a new archive.  Returns the resulting manifest.

    Raises ``ValueError`` for malformed input.
    """
    if not site_id:
        raise ValueError("site_id is required")
    if not frames:
        raise ValueError("at least one frame is required")

    site_id = site_id.upper()

    # Normalize valid_time on each frame to a datetime for sorting.
    normalized: List[Dict[str, Any]] = []
    for f in frames:
        vt = f.get("valid_time")
        if isinstance(vt, str):
            try:
                # Accept the canonical "YYYY-MM-DD HH:MM UTC" format produced
                # by the API as well as ISO-8601.
                vt_dt = datetime.strptime(vt, "%Y-%m-%d %H:%M UTC")
            except ValueError:
                try:
                    vt_dt = datetime.fromisoformat(vt.replace("Z", "+00:00"))
                except ValueError:
                    vt_dt = None
        elif isinstance(vt, datetime):
            vt_dt = vt
        else:
            vt_dt = None

        if vt_dt is None:
            # Without a parseable valid_time we can't order frames or build
            # the archive id; surface this loudly instead of silently
            # generating a degenerate manifest.
            raise ValueError(f"frame {f.get('file_id')} missing valid_time")

        cached_path = f.get("cached_path")
        if not cached_path or not os.path.exists(cached_path):
            # Skip frames whose raw file is no longer on disk; the user can
            # still archive a partially-loaded loop.
            continue

        normalized.append({
            "file_id": str(f["file_id"]),
            "valid_time": vt_dt,
            "cached_path": cached_path,
        })

    if not normalized:
        raise ValueError("none of the supplied frames have a cached file on disk")

    normalized.sort(key=lambda r: r["valid_time"])  # oldest → newest
    newest = normalized[-1]["valid_time"]

    metar_station = (metar or {}).get("station") if metar else None
    archive_id = build_archive_id(newest, metar_station)

    with _archive_lock:
        _ensure_root()
        dest_dir = _archive_dir(site_id, archive_id)
        os.makedirs(dest_dir, exist_ok=True)

        frame_records: List[Dict[str, Any]] = []
        for f in normalized:
            fname = os.path.basename(f["cached_path"])
            dest = os.path.join(dest_dir, fname)
            # Skip the copy when the file is already there (re-saves are a
            # no-op aside from manifest refresh).
            if not os.path.exists(dest) or os.path.getsize(dest) != os.path.getsize(f["cached_path"]):
                shutil.copy2(f["cached_path"], dest)
            frame_records.append({
                "file_id": f["file_id"],
                "valid_time": f["valid_time"].strftime("%Y-%m-%d %H:%M UTC"),
                "filename": fname,
            })

        manifest = {
            "site_id": site_id,
            "archive_id": archive_id,
            "saved_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "newest_valid_time": newest.strftime("%Y-%m-%d %H:%M UTC"),
            "metar": metar or None,
            "storm_motion": storm_motion or None,
            "frames": frame_records,
        }
        with open(_manifest_path(site_id, archive_id), "w") as fh:
            json.dump(manifest, fh, indent=2)

    return manifest


def list_archives() -> List[Dict[str, Any]]:
    """Return a list of ``{site_id, archives:[manifest, ...]}`` grouped by
    site.  Sites with no archives are omitted; archives within each site
    are ordered newest-first.
    """
    if not os.path.exists(ARCHIVE_ROOT):
        return []

    sites: List[Dict[str, Any]] = []
    for site_id in sorted(os.listdir(ARCHIVE_ROOT)):
        site_dir = os.path.join(ARCHIVE_ROOT, site_id)
        if not os.path.isdir(site_dir):
            continue
        archives: List[Dict[str, Any]] = []
        for archive_id in os.listdir(site_dir):
            manifest = _load_manifest(site_id, archive_id)
            if manifest:
                archives.append(manifest)
        if not archives:
            continue
        archives.sort(key=lambda m: m.get("newest_valid_time", ""), reverse=True)
        sites.append({"site_id": site_id, "archives": archives})
    return sites


def get_archive(site_id: str, archive_id: str) -> Optional[Dict[str, Any]]:
    return _load_manifest(site_id.upper(), archive_id)


def get_archive_frame_path(site_id: str, archive_id: str, file_id: str) -> Optional[str]:
    manifest = get_archive(site_id, archive_id)
    if not manifest:
        return None
    for frame in manifest.get("frames", []):
        if frame.get("file_id") == file_id:
            p = os.path.join(_archive_dir(site_id.upper(), archive_id), frame["filename"])
            if os.path.exists(p):
                return p
    return None


def delete_archive(site_id: str, archive_id: str) -> bool:
    """Remove an archive folder.  Returns True if something was deleted."""
    site_id = site_id.upper()
    # Guard against path traversal — the safe-tokenized id must round-trip.
    if _safe(archive_id) != archive_id or _safe(site_id) != site_id:
        return False
    target = _archive_dir(site_id, archive_id)
    if not os.path.isdir(target):
        return False
    with _archive_lock:
        shutil.rmtree(target, ignore_errors=True)
        # Also drop the site folder if it's now empty.
        site_dir = os.path.dirname(target)
        try:
            if os.path.isdir(site_dir) and not os.listdir(site_dir):
                os.rmdir(site_dir)
        except OSError:
            pass
    return True
