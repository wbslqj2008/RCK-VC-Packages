#!/usr/bin/env python3
"""Resolve a push-retry rebase conflict on removal-requests.json.

Two removals merged close together: this run cleared the ids it removed while main gained another request.
The only safe answer is main's list (the rebase upstream) minus the ids this run actually removed.
Any other conflicted path is left alone (exit 1) so the workflow aborts the rebase and fails as before.
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path

REMOVAL_REQUESTS = 'removal-requests.json'


def resolve(upstream_text: str | None, removed: list[str]) -> str:
    """main's request list without the ids this run removed, in the deployment scripts' format."""
    ids: list[str] = []
    if upstream_text:
        data = json.loads(upstream_text.lstrip('\ufeff'))
        if not isinstance(data, dict) or data.get('schemaVersion') != 1 or not isinstance(data.get('ids'), list):
            raise ValueError(f'{REMOVAL_REQUESTS} 형식이 올바르지 않습니다.')
        ids = [i for i in data['ids'] if isinstance(i, str)]
    done = set(removed)
    remaining = [i for i in dict.fromkeys(ids) if i not in done]
    return json.dumps({'schemaVersion': 1, 'ids': remaining}, ensure_ascii=False, indent=2) + '\n'


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(['git', *args], cwd=root, check=check, capture_output=True, text=True, encoding='utf-8')


def main(root: Path, summary: Path) -> int:
    conflicted = [p for p in git(root, 'diff', '--name-only', '--diff-filter=U').stdout.splitlines() if p]
    if conflicted != [REMOVAL_REQUESTS]:
        print(f'다른 충돌이 있어 자동으로 해결하지 않습니다: {", ".join(conflicted) or "(없음)"}', file=sys.stderr)
        return 1
    removed = json.loads(summary.read_text(encoding='utf-8-sig')).get('removed', [])
    # During a rebase stage 2 ("ours") is the upstream side: main as it is now.
    upstream = git(root, 'show', ':2:' + REMOVAL_REQUESTS, check=False)
    text = resolve(upstream.stdout if upstream.returncode == 0 else None, removed)
    (root / REMOVAL_REQUESTS).write_text(text, encoding='utf-8')
    git(root, 'add', REMOVAL_REQUESTS)
    print(f'{REMOVAL_REQUESTS} 충돌을 해결했습니다: main의 목록에서 {", ".join(removed) or "(없음)"} 제외')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=Path('.'))
    parser.add_argument('--summary', type=Path, required=True)
    args = parser.parse_args()
    sys.exit(main(args.repo_root, args.summary))
