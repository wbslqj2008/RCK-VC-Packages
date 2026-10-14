#!/usr/bin/env python3
"""Create releases from changed payloads without editing addon source versions."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
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


def version_history(old: dict | None, archived: list[dict] | None = None) -> list[dict]:
    if not old:
        return []
    # Keep enough file identity to recognize a manually copied older package.
    version = old['version']
    asset = urllib.parse.unquote(urllib.parse.urlparse(old.get('downloadUrl', '')).path.rsplit('/', 1)[-1])
    match = re.fullmatch(re.escape(old['id']) + r'-(\d+\.\d+\.\d+)\.zip', asset)
    if match:
        version = match.group(1)
    current = {'version': version, 'contentFiles': old.get('contentFiles', [])}
    for field in ('mainDll', 'mainDllSha256'):
        if old.get(field):
            current[field] = old[field]
    snapshots = [current] + old.get('versions', []) + (archived or [])
    unique = []
    seen = set()
    for snapshot in snapshots:
        if not snapshot.get('contentFiles') and not snapshot.get('mainDllSha256'):
            continue
        fingerprint = json.dumps(snapshot, sort_keys=True)
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(snapshot)
    return unique[:30]


def load_manifest_history(root: Path) -> dict[str, list[dict]]:
    """Recover already published file identities from the checkout's manifest commits."""
    if not (root / '.git').exists():
        return {}
    try:
        commits = subprocess.run(['git', 'log', '-n', '100', '--format=%H', '--', 'manifest.json'],
                                 cwd=root, check=True, capture_output=True, text=True, encoding='utf-8').stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return {}
    versions: dict[str, list[dict]] = {}
    for commit in commits:
        if not re.fullmatch(r'[0-9a-fA-F]{40,64}', commit):
            continue
        try:
            text = subprocess.run(['git', 'show', f'{commit}:manifest.json'], cwd=root, check=True,
                                  capture_output=True, text=True, encoding='utf-8').stdout
            historical = json.loads(text.lstrip('\ufeff'))
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError, UnicodeError):
            continue
        for entry in historical.get('packages', []):
            if not isinstance(entry, dict) or not entry.get('id') or not entry.get('version'):
                continue
            versions.setdefault(entry['id'], []).extend(version_history(entry))
    return versions


def build(root: Path, output: Path, repository: str, tag: str, bump: str = 'patch', force_package: str = '', release_notes: str = '', *, force: bool = False) -> dict:
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    before = json.dumps(manifest, sort_keys=True)
    previous = {p['id']: p for p in manifest.get('packages', [])}
    archived = load_manifest_history(root)
    metadata_paths = sorted((root / 'packages').glob('*/package.json'))
    available_ids = [json.loads(p.read_text(encoding='utf-8-sig'))['id'] for p in metadata_paths]
    # Preserve a real rck.studio ID, but accept the common shorthand in this repository.
    if force_package == 'rck.studio' and force_package not in available_ids and 'rck.rckstudio' in available_ids:
        force_package = 'rck.rckstudio'
    if force_package and force_package not in available_ids:
        raise ValueError(f'Unknown package id: {force_package}. Available IDs: {", ".join(available_ids)}')
    if bump not in ('patch', 'minor', 'major'):
        raise ValueError(f'Unsupported bump: {bump}')
    if bump != 'patch' and not force_package:
        raise ValueError('A package_id is required for a minor/major release. Ordinary uploads use patch automatically.')
    seen = set()
    changed = []
    package_updates = []
    releases = []
    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    for metadata_path in metadata_paths:
        package = json.loads(metadata_path.read_text(encoding='utf-8-sig'))
        for field in ('id', 'name', 'type', 'version', 'description', 'files', 'restartRequired', 'vcVersions'):
            if field not in package:
                raise ValueError(f'{metadata_path}: missing {field}')
        package_id = package['id']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', package_id) or package_id in seen:
            raise ValueError(f'Invalid or duplicate package id: {package_id}')
        seen.add(package_id)
        if force_package and package_id != force_package:
            continue
        if package['type'] not in ('addon', 'ecatalog'):
            raise ValueError(f'{package_id}: type must be addon or ecatalog')
        if not package['files']:
            raise ValueError(f'{package_id}: empty files list')
        payloads = []
        destinations = set()
        archive_names = set()
        for file in package['files']:
            source = safe_path(metadata_path.parent, file['source'])
            safe_path(metadata_path.parent, file['destination'])
            destination = file['destination'].replace('\\', '/')
            prefix = 'ecatalog/' if package['type'] == 'ecatalog' else 'vcRoot/'
            if not destination.startswith(prefix):
                raise ValueError(f'{package_id}: destination must start with {prefix}')
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
        explicit_release = force or bump in ('minor', 'major')
        old_asset_version = None
        if old:
            asset_name = urllib.parse.unquote(urllib.parse.urlparse(old.get('downloadUrl', '')).path.rsplit('/', 1)[-1])
            match = re.fullmatch(re.escape(package_id) + r'-(\d+\.\d+\.\d+)\.zip', asset_name)
            if match:
                old_asset_version = match.group(1)
        inconsistent = old_asset_version is not None and old_asset_version != old['version']
        if old and old.get('contentSha256') == fingerprint and not explicit_release and not inconsistent:
            if archived.get(package_id):
                old['versions'] = version_history(old, archived[package_id])
            if package['version'] != old['version']:
                package_updates.append({'path': metadata_path.relative_to(root).as_posix(), 'id': package_id, 'version': old['version']})
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
        note = release_notes.strip()
        notes = [note] if note else package.get('releaseNotes', [])
        package['releaseNotes'] = notes
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
            'vcVersions': package['vcVersions'], 'releaseNotes': notes,
            'contentFiles': [{'destination': dest, 'sha256': digest} for _, _, dest, digest in payloads],
            'versions': version_history(old, archived.get(package_id)),
        }
        if primary:
            entry['mainDll'] = primary
            entry['mainDllSha256'] = primary_files[0][2]
        for field in ('developer', 'documentationDestination', 'documentationUrl'):
            if package.get(field):
                entry[field] = package[field]
        previous[package_id] = entry
        changed.append(zip_name)
        package_updates.append({'path': metadata_path.relative_to(root).as_posix(), 'id': package_id, 'version': package['version']})
        releases.append({'id': package_id, 'from': old['version'] if old else None, 'to': package['version']})
    if force_package and force_package not in seen:
        raise ValueError(f'Unknown package id: {force_package}')
    manifest['schemaVersion'] = 1
    if changed:
        manifest['updatedAt'] = now
    manifest['packages'] = sorted(previous.values(), key=lambda p: (p['type'], p['name'].casefold()))
    (output / 'manifest.next.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'package-updates.json').write_text(json.dumps(package_updates, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = {'changed': changed, 'count': len(changed), 'tag': tag, 'package_id': force_package, 'bump': bump,
               'releases': releases, 'manifest_changed': before != json.dumps(manifest, sort_keys=True),
               'metadata_changed': bool(package_updates)}
    (output / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=Path('.'))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--bump', choices=['patch', 'minor', 'major'], default='patch')
    parser.add_argument('--package-id', '--force-package', dest='package_id', default='', help='Select one package. An unchanged patch is skipped.')
    parser.add_argument('--force', action='store_true', help='Explicitly publish unchanged content as a new version.')
    parser.add_argument('--release-notes', default='')
    args = parser.parse_args()
    print(json.dumps(build(args.repo_root, args.output_dir, args.repository, args.tag, args.bump, args.package_id, args.release_notes, force=args.force)))

