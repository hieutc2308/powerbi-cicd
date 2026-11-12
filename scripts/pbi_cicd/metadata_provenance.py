"""Validate ticket/source identity before reusing local TE2 artifacts."""

from __future__ import annotations

import hashlib
import json

from pbi_cicd.config_loader import ProjectPaths


def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_fingerprint(paths: ProjectPaths) -> str:
    """Hash project definitions and shared BPA rules, excluding machine-local state."""
    digest = hashlib.sha256()
    files = [p for p in paths.project_dir.rglob("*") if p.is_file() and ".pbi" not in p.relative_to(paths.project_dir).parts and p.suffix.lower() != ".pbix"]
    for path in sorted(files):
        resolved = path.resolve()
        if not resolved.is_relative_to(paths.project_dir):
            raise ValueError(f"Source file escapes ticket {paths.ticket}: {path}")
        digest.update(path.relative_to(paths.project_dir).as_posix().encode())
        digest.update(bytes.fromhex(_digest(path)))
    digest.update(bytes.fromhex(_digest(paths.rules_file)))
    if paths.config_file.is_file():
        digest.update(bytes.fromhex(_digest(paths.config_file)))
    return digest.hexdigest()


def record_te2_provenance(paths: ProjectPaths) -> dict:
    """Record only after a successful fresh TE2 extraction and BPA invocation."""
    metadata = paths.dist_dir / "te2-metadata.json"
    bpa = paths.dist_dir / "te2-bpa.txt"
    json.loads(metadata.read_text(encoding="utf-8-sig"))
    record = {
        "ticket": paths.ticket,
        "pbip": paths.pbip_file.relative_to(paths.root).as_posix(),
        "sourceFingerprint": source_fingerprint(paths),
        "metadataSha256": _digest(metadata), "bpaSha256": _digest(bpa),
    }
    (paths.dist_dir / "te2-source.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def te2_provenance_status(paths: ProjectPaths) -> str:
    """Treat missing, modified, copied, or outdated metadata as unusable."""
    marker = paths.dist_dir / "te2-source.json"
    if not marker.is_file():
        return "missing"
    try:
        record = json.loads(marker.read_text(encoding="utf-8"))
        valid = (
            record.get("ticket") == paths.ticket
            and record.get("pbip") == paths.pbip_file.relative_to(paths.root).as_posix()
            and record.get("sourceFingerprint") == source_fingerprint(paths)
            and record.get("metadataSha256") == _digest(paths.dist_dir / "te2-metadata.json")
            and record.get("bpaSha256") == _digest(paths.dist_dir / "te2-bpa.txt")
        )
        return "valid" if valid else "stale"
    except (OSError, ValueError, TypeError):
        return "stale"
