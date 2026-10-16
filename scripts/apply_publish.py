"""Synchronize source package versions, release notes, and the published manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath

from auto_publish import safe_path, version_tuple


def apply(root: Path, output: Path) -> list[str]:
    root = root.resolve()
    output = output.resolve()
    manifest_text = (output / 'manifest.next.json').read_text(encoding='utf-8-sig')
    manifest = json.loads(manifest_text)
    entries = {p['id']: p for p in manifest['packages']}
    updates = json.loads((output / 'package-updates.json').read_text(encoding='utf-8-sig'))
    planned = []
    seen = set()
    # Validate every write before changing any source metadata.
    for update in updates:
        relative = PurePosixPath(update['path'])
        if len(relative.parts) != 3 or relative.parts[0] != 'packages' or relative.name != 'package.json':
            raise ValueError(f'Unexpected metadata path: {relative}')
        path = safe_path(root, update['path'])
        if path in seen:
            raise ValueError(f'Duplicate metadata path: {path}')
        seen.add(path)
        metadata = json.loads(path.read_text(encoding='utf-8-sig'))
        entry = entries.get(update['id'])
        version_tuple(update['version'])
        if metadata['id'] != update['id'] or entry is None or entry['version'] != update['version']:
            raise ValueError(f'Package/manifest mismatch: {update["id"]}')
        metadata['version'] = update['version']
        metadata['releaseNotes'] = entry.get('releaseNotes', [])
        planned.append((path, json.dumps(metadata, ensure_ascii=False, indent=2) + '\n'))
    for path, text in planned:
        path.write_text(text, encoding='utf-8')
    (root / 'manifest.json').write_text(manifest_text, encoding='utf-8')
    return [str(path.relative_to(root)) for path, _ in planned]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=Path('.'))
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(apply(args.repo_root, args.output_dir)))
