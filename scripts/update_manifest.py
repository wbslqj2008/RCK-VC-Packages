#!/usr/bin/env python3
"""GitHub Release 자산을 읽어 manifest.json을 자동 갱신한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from auto_publish import main_dll, version_tuple


REQUIRED_PACKAGE_FIELDS = {
    "id",
    "name",
    "type",
    "version",
    "description",
    "restartRequired",
    "vcVersions",
    "files",
}


def fail(message: str) -> "NoReturn":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def is_safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value.replace("\\", "/"))
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def read_package(zip_path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = set(archive.namelist())
            if "package.json" not in names:
                fail(f"{zip_path.name}: ZIP 루트에 package.json이 없습니다.")

            package = json.loads(archive.read("package.json").decode("utf-8-sig"))
            missing = sorted(REQUIRED_PACKAGE_FIELDS - set(package))
            if missing:
                fail(f"{zip_path.name}: package.json 필수 항목 누락: {', '.join(missing)}")

            if not isinstance(package["files"], list) or not package["files"]:
                fail(f"{zip_path.name}: files 목록이 비어 있습니다.")

            for file_entry in package["files"]:
                source = str(file_entry.get("source", ""))
                destination = str(file_entry.get("destination", ""))
                if not is_safe_relative_path(source):
                    fail(f"{zip_path.name}: 안전하지 않은 source 경로: {source}")
                if not is_safe_relative_path(destination):
                    fail(f"{zip_path.name}: 안전하지 않은 destination 경로: {destination}")
                if source not in names:
                    fail(f"{zip_path.name}: package.json에 지정된 파일이 ZIP에 없습니다: {source}")

            return package
    except zipfile.BadZipFile:
        fail(f"정상적인 ZIP 파일이 아닙니다: {zip_path.name}")
    except json.JSONDecodeError as exc:
        fail(f"{zip_path.name}: package.json JSON 오류: {exc}")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_manifest_entry(
    package: dict[str, Any],
    zip_path: Path,
    repository: str,
    tag: str,
    published_at: str,
) -> dict[str, Any]:
    asset = urllib.parse.quote(zip_path.name)
    entry = {
        "id": package["id"],
        "name": package["name"],
        "type": package["type"],
        "version": package["version"],
        "description": package["description"],
        "downloadUrl": f"https://github.com/{repository}/releases/download/{urllib.parse.quote(tag)}/{asset}",
        "sha256": sha256(zip_path),
        "publishedAt": published_at or utc_now(),
        "archiveType": "zip",
        "restartRequired": bool(package.get("restartRequired", True)),
        "systemPackage": bool(package.get("systemPackage", False)),
        "vcVersions": list(package.get("vcVersions", [])),
        "releaseNotes": list(package.get("releaseNotes", [])),
    }
    with zipfile.ZipFile(zip_path) as archive:
        contents = []
        primary = main_dll(package)
        for file in package['files']:
            digest = hashlib.sha256(archive.read(file['source'])).hexdigest().upper()
            contents.append({'destination': file['destination'], 'sha256': digest})
            if PurePosixPath(file['source']).name == primary:
                entry['mainDll'] = primary
                entry['mainDllSha256'] = digest
        entry['contentFiles'] = contents
    return entry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--published-at", default="")
    args = parser.parse_args()

    assets = sorted(args.assets_dir.glob("*.zip"))
    if not assets:
        fail("Release에 처리할 ZIP Asset이 없습니다.")

    if args.manifest.exists():
        manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    else:
        manifest = {"schemaVersion": 1, "packages": []}

    existing = {entry["id"]: entry for entry in manifest.get("packages", [])}
    seen_ids: set[str] = set()

    for zip_path in assets:
        package = read_package(zip_path)
        package_id = str(package["id"])
        if package_id in seen_ids:
            fail(f"같은 Release에 동일한 패키지 ID가 두 번 들어 있습니다: {package_id}")
        seen_ids.add(package_id)
        old = existing.get(package_id)
        if old and version_tuple(str(package['version'])) < version_tuple(str(old['version'])):
            print(f"SKIPPED: older release for {package_id}")
            continue
        existing[package_id] = build_manifest_entry(
            package=package,
            zip_path=zip_path,
            repository=args.repository,
            tag=args.tag,
            published_at=args.published_at,
        )
        print(f"UPDATED: {package_id} {package['version']} <- {zip_path.name}")

    manifest["schemaVersion"] = 1
    manifest["updatedAt"] = utc_now()
    manifest["packages"] = sorted(
        existing.values(),
        key=lambda item: (str(item.get("type", "")), str(item.get("name", "")).casefold()),
    )

    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Manifest written: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
