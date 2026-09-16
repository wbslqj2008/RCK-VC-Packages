import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from auto_publish import build


class AutoPublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.manifest = {'schemaVersion': 1, 'packages': []}
        for name in ('Studio', 'CodeLens'):
            folder = self.root / 'packages' / name
            (folder / 'payload').mkdir(parents=True)
            (folder / 'payload' / f'Plugin.{name}.dll').write_bytes(b'original DLL without version info')
            package = {'id': 'rck.' + name.lower(), 'name': name, 'type': 'addon', 'version': '0.0.9',
                       'description': name, 'restartRequired': True, 'vcVersions': ['5.1'],
                       'files': [{'source': f'payload/Plugin.{name}.dll', 'destination': f'vcRoot/Plugin.{name}.dll'}]}
            (folder / 'package.json').write_text(json.dumps(package))
            self.manifest['packages'].append({'id': package['id'], 'name': name, 'type': 'addon', 'version': '0.0.9'})
        self.save(self.manifest)

    def save(self, manifest):
        (self.root / 'manifest.json').write_text(json.dumps(manifest))

    def run_build(self, tag, **kwargs):
        output = self.root / tag
        summary = build(self.root, output, 'owner/repo', tag, **kwargs)
        manifest = json.loads((output / 'manifest.next.json').read_text())
        return summary, manifest, output

    def test_bootstrap_and_no_change(self):
        summary, manifest, output = self.run_build('bootstrap')
        self.assertEqual(summary['count'], 2)
        self.assertEqual([p['version'] for p in manifest['packages']], ['0.0.10', '0.0.10'])
        for package in manifest['packages']:
            asset = output / f"{package['id']}-{package['version']}.zip"
            self.assertEqual(package['sha256'], hashlib.sha256(asset.read_bytes()).hexdigest().upper())
            with zipfile.ZipFile(asset) as archive:
                metadata = json.loads(archive.read('package.json'))
                self.assertEqual(metadata['version'], package['version'])
                for file in metadata['files']:
                    expected = next(f for f in package['contentFiles'] if f['destination'] == file['destination'])
                    self.assertEqual(expected['sha256'], hashlib.sha256(archive.read(file['source'])).hexdigest().upper())
        self.save(manifest)
        second, second_manifest, _ = self.run_build('unchanged')
        self.assertEqual(second['count'], 0)
        self.assertEqual(second_manifest, manifest)

    def test_changed_package_only_and_two_uploaders(self):
        _, manifest, _ = self.run_build('initial')
        self.save(manifest)
        studio = self.root / 'packages/Studio/payload/Plugin.Studio.dll'
        studio.write_bytes(b'changed but still no assembly version')
        summary, manifest, _ = self.run_build('person-one')
        self.assertEqual(summary['changed'], ['rck.studio-0.0.11.zip'])
        self.save(manifest)
        (self.root / 'packages/CodeLens/payload/Plugin.CodeLens.dll').write_bytes(b'person two change')
        summary, _, _ = self.run_build('person-two')
        self.assertEqual(summary['changed'], ['rck.codelens-0.0.11.zip'])

    def test_minor_major_and_force(self):
        _, manifest, _ = self.run_build('initial')
        self.save(manifest)
        summary, minor, _ = self.run_build('minor', bump='minor', force_package='rck.studio')
        self.assertEqual(summary['changed'], ['rck.studio-0.1.0.zip'])
        self.save(minor)
        summary, _, _ = self.run_build('major', bump='major', force_package='rck.studio')
        self.assertEqual(summary['changed'], ['rck.studio-1.0.0.zip'])

    def test_two_changes_before_job_starts_are_both_published(self):
        _, manifest, _ = self.run_build('initial')
        self.save(manifest)
        for name in ('Studio', 'CodeLens'):
            (self.root / f'packages/{name}/payload/Plugin.{name}.dll').write_bytes(name.encode())
        summary, updated, _ = self.run_build('coalesced')
        self.assertEqual(summary['count'], 2)
        self.assertEqual([p['version'] for p in updated['packages']], ['0.0.11', '0.0.11'])

    def test_missing_payload_and_unknown_force_do_not_modify_source(self):
        before = (self.root / 'manifest.json').read_bytes()
        (self.root / 'packages/Studio/payload/Plugin.Studio.dll').unlink()
        with self.assertRaises(FileNotFoundError):
            self.run_build('missing')
        self.assertEqual(before, (self.root / 'manifest.json').read_bytes())
        (self.root / 'packages/Studio/payload/Plugin.Studio.dll').write_bytes(b'restored payload')
        with self.assertRaises(ValueError):
            self.run_build('invalid-force', force_package='missing')

    def test_unsafe_destination_is_rejected(self):
        path = self.root / 'packages/Studio/package.json'
        package = json.loads(path.read_text())
        package['files'][0]['destination'] = 'vcRoot/../../outside.dll'
        path.write_text(json.dumps(package))
        with self.assertRaises(ValueError):
            self.run_build('unsafe')


if __name__ == '__main__':
    unittest.main()
