#!/usr/bin/env python3
"""Create releases from changed payloads without editing addon source versions."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def safe_path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative.replace('\\', '/'))
    if not relative or path.is_absolute() or '..' in path.parts or ':' in relative:
        raise ValueError(f'Unsafe package path: {relative}')
    result = (root / str(path)).resolve()
    result.relative_to(root.resolve())
    return result


def version_tuple(text: str) -> tuple[int, int, int]:
    if not re.fullmatch(r'\d+\.\d+\.\d+', text):
        raise ValueError(f'Unsupported package version: {text}')
    return tuple(map(int, text.split('.')))


def main_dll(package: dict) -> str | None:
    names = [PurePosixPath(f['source'].replace('\\', '/')).name for f in package['files']]
    compact = ''.join(package['name'].split())
    for candidate in (f'Plugin.{compact}.dll', f'{compact}.dll'):
        matches = [n for n in names if n.casefold() == candidate.casefold()]
        if len(matches) == 1:
            return matches[0]
    # A package containing one DLL needs no special naming convention.
    dlls = [n for n in names if n.lower().endswith('.dll')]
    return dlls[0] if len(dlls) == 1 else None


def build(root: Path, output: Path, repository: str, tag: str, bump: str = 'patch', force_package: str = '') -> dict:
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    previous = {p['id']: p for p in manifest.get('packages', [])}
    seen = set()
    changed = []
    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    for metadata_path in sorted((root / 'packages').glob('*/package.json')):
        package = json.loads(metadata_path.read_text(encoding='utf-8-sig'))
        for field in ('id', 'name', 'type', 'version', 'description', 'files', 'restartRequired', 'vcVersions'):
            if field not in package:
                raise ValueError(f'{metadata_path}: missing {field}')
        package_id = package['id']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', package_id) or package_id in seen:
            raise ValueError(f'Invalid or duplicate package id: {package_id}')
        seen.add(package_id)
        if not package['files']:
            raise ValueError(f'{package_id}: empty files list')
        payloads = []
        destinations = set()
        archive_names = set()
        for file in package['files']:
            source = safe_path(metadata_path.parent, file['source'])
            safe_path(metadata_path.parent, file['destination'])
            destination = file['destination'].replace('\\', '/')
            archive_name = file['source'].replace('\\', '/')
            if destination.casefold() in destinations or archive_name.casefold() in archive_names:
                raise ValueError(f'{package_id}: duplicate file path')
            if archive_name.casefold() == 'package.json':
                raise ValueError('Payload cannot replace package.json')
            destinations.add(destination.casefold())
            archive_names.add(archive_name.casefold())
            digest = hashlib.sha256(source.read_bytes()).hexdigest().upper()
            payloads.append((source, archive_name, destination, digest))
        identity = {k: v for k, v in package.items() if k != 'version'}
        identity['content'] = sorted((name, dest, digest) for _, name, dest, digest in payloads)
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest().upper()
        old = previous.get(package_id)
        force = bool(force_package) and force_package == package_id
        if old and old.get('contentSha256') == fingerprint and not force:
            continue
        source_version = version_tuple(package['version'])
        base = version_tuple(old['version']) if old else source_version
        if not old:
            next_version = base
        elif bump == 'major':
            next_version = (base[0] + 1, 0, 0)
        elif bump == 'minor':
            next_version = (base[0], base[1] + 1, 0)
        else:
            next_version = (base[0], base[1], base[2] + 1)
        package['version'] = '.'.join(map(str, next_version))
        zip_name = f"{package_id}-{package['version']}.zip"
        zip_path = output / zip_name
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('package.json', json.dumps(package, ensure_ascii=False, indent=2))
            for source, name, _, _ in payloads:
                archive.write(source, name)
        primary = main_dll(package)
        if package['type'].lower() == 'addon' and not primary:
            raise ValueError(f'{package_id}: cannot identify the main DLL from package name/files')
        primary_files = [(name, dest, digest) for _, name, dest, digest in payloads
                         if PurePosixPath(name).name == primary]
        if primary and (len(primary_files) != 1 or primary_files[0][1].casefold() != f'vcRoot/{primary}'.casefold()):
            raise ValueError(f'{package_id}: main DLL destination must be vcRoot/{primary}')
        entry = {
            'id': package_id, 'name': package['name'], 'type': package['type'],
            'version': package['version'], 'description': package['description'],
            'downloadUrl': f'https://github.com/{repository}/releases/download/{urllib.parse.quote(tag, safe="")}/{urllib.parse.quote(zip_name)}',
            'sha256': hashlib.sha256(zip_path.read_bytes()).hexdigest().upper(),
            'contentSha256': fingerprint, 'publishedAt': now, 'archiveType': 'zip',
            'restartRequired': package['restartRequired'], 'systemPackage': package.get('systemPackage', False),
            'vcVersions': package['vcVersions'], 'releaseNotes': package.get('releaseNotes', []),
            'contentFiles': [{'destination': dest, 'sha256': digest} for _, _, dest, digest in payloads],
        }
        if primary:
            entry['mainDll'] = primary
            entry['mainDllSha256'] = primary_files[0][2]
        previous[package_id] = entry
        changed.append(zip_name)
    if force_package and force_package not in seen:
        raise ValueError(f'Unknown package id: {force_package}')
    manifest['schemaVersion'] = 1
    if changed:
        manifest['updatedAt'] = now
    manifest['packages'] = sorted(previous.values(), key=lambda p: (p['type'], p['name'].casefold()))
    (output / 'manifest.next.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = {'changed': changed, 'count': len(changed), 'tag': tag}
    (output / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=Path('.'))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--bump', choices=['patch', 'minor', 'major'], default='patch')
    parser.add_argument('--force-package', default='')
    args = parser.parse_args()
    print(json.dumps(build(args.repo_root, args.output_dir, args.repository, args.tag, args.bump, args.force_package)))
