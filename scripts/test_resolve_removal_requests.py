import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from resolve_removal_requests import main, resolve


def ids(text):
    return json.loads(text)['ids']


class ResolveTests(unittest.TestCase):
    def test_upstream_list_minus_removed(self):
        upstream = json.dumps({'schemaVersion': 1, 'ids': ['rck.a', 'rck.b', 'rck.c']})
        self.assertEqual(ids(resolve(upstream, ['rck.a'])), ['rck.b', 'rck.c'])
        self.assertEqual(ids(resolve(upstream, [])), ['rck.a', 'rck.b', 'rck.c'])
        self.assertEqual(resolve(json.dumps({'schemaVersion': 1, 'ids': ['rck.a']}), ['rck.a']),
                         '{\n  "schemaVersion": 1,\n  "ids": []\n}\n')

    def test_missing_upstream_file_is_an_empty_list(self):
        self.assertEqual(ids(resolve(None, ['rck.a'])), [])

    def test_invalid_upstream_file_fails(self):
        with self.assertRaises(ValueError):
            resolve(json.dumps({'schemaVersion': 2, 'ids': []}), [])


@unittest.skipUnless(shutil.which('git'), 'git is not installed')
class ResolveInRebaseTests(unittest.TestCase):
    """Two removals close together: the bot clears ["rck.a"] while main gains "rck.b"."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'test')
        self.git('config', 'user.email', 'test@example.com')
        self.git('config', 'core.autocrlf', 'false')
        self.write('removal-requests.json', {'schemaVersion': 1, 'ids': ['rck.a']})
        self.write('manifest.json', {'packages': ['rck.a', 'rck.b']})
        self.git('add', '.')
        self.git('commit', '-q', '-m', 'A removal merged')
        base = self.git('rev-parse', 'HEAD').strip()
        # main moves on: B's removal is merged.
        self.write('removal-requests.json', {'schemaVersion': 1, 'ids': ['rck.a', 'rck.b']})
        self.git('commit', '-q', '-am', 'B removal merged')
        # The bot's commit was made on top of the older main.
        self.git('checkout', '-q', '-b', 'bot', base)
        self.write('removal-requests.json', {'schemaVersion': 1, 'ids': []})
        self.write('manifest.json', {'packages': ['rck.b']})
        self.git('commit', '-q', '-am', 'chore: auto-publish addon packages')
        self.summary = Path(self.temp.name) / 'summary.json'
        self.summary.write_text(json.dumps({'removed': ['rck.a']}))

    def git(self, *args, check=True):
        return subprocess.run(['git', *args], cwd=self.root, check=check, capture_output=True, text=True).stdout

    def write(self, name, data):
        (self.root / name).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')

    def test_request_file_conflict_is_resolved_and_the_rebase_continues(self):
        rebase = subprocess.run(['git', 'rebase', 'main'], cwd=self.root, capture_output=True, text=True)
        self.assertNotEqual(rebase.returncode, 0)
        self.assertEqual(main(self.root, self.summary), 0)
        subprocess.run(['git', '-c', 'core.editor=true', 'rebase', '--continue'], cwd=self.root, check=True, capture_output=True)
        self.assertEqual(ids((self.root / 'removal-requests.json').read_text()), ['rck.b'])
        self.assertEqual(json.loads((self.root / 'manifest.json').read_text())['packages'], ['rck.b'])
        self.assertEqual(self.git('rev-parse', 'HEAD~1').strip(), self.git('rev-parse', 'main').strip())

    def test_any_other_conflict_is_left_for_the_abort(self):
        # main also changed manifest.json: two conflicted paths.
        self.git('checkout', '-q', 'main')
        self.write('manifest.json', {'packages': ['rck.a', 'rck.b', 'rck.c']})
        self.git('commit', '-q', '-am', 'manifest edited on main')
        self.git('checkout', '-q', 'bot')
        subprocess.run(['git', 'rebase', 'main'], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(main(self.root, self.summary), 1)
        self.assertIn('removal-requests.json', self.git('diff', '--name-only', '--diff-filter=U'))
        self.git('rebase', '--abort')


if __name__ == '__main__':
    unittest.main()
