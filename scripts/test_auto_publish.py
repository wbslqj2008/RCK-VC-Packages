import hashlib
import json
import tempfile
import subprocess
import sys
import unittest
import zipfile
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
from auto_publish import build
from apply_publish import apply


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

    def test_declared_main_dll_allows_display_name_with_dependencies(self):
        path = self.root / 'packages/Studio/package.json'
        metadata = json.loads(path.read_text())
        metadata['name'] = 'Rendering Tools for Engineers'
        metadata['mainDll'] = 'Plugin.Studio.dll'
        metadata['files'].append({'source': 'payload/Helper.dll', 'destination': 'vcRoot/Helper.dll'})
        (path.parent / 'payload/Helper.dll').write_bytes(b'dependency')
        path.write_text(json.dumps(metadata))
        _, manifest, _ = self.run_build('explicit-main')
        studio = next(p for p in manifest['packages'] if p['id'] == 'rck.studio')
        self.assertEqual(studio['mainDll'], 'Plugin.Studio.dll')
        metadata['mainDll'] = 'Missing.dll'
        path.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.run_build('missing-main')

    def test_ecatalog_with_pdf_and_developer_survives_publication(self):
        folder = self.root / 'packages/RenderingOptimization'
        folder.mkdir()
        (folder / 'Rendering Optimization.vcmx').write_bytes(b'original component bytes')
        (folder / 'guide.pdf').write_bytes(b'%PDF-1.4 guide')
        package = {'id': 'rck.ecatalog.rendering-optimization', 'name': 'Rendering Optimization',
                   'type': 'ecatalog', 'version': '1.0.0', 'description': 'Two rendering modes',
                   'developer': 'Lee Junyong', 'restartRequired': False, 'vcVersions': ['5.1'],
                   'documentationDestination': 'ecatalog/AddonManager/guide.pdf',
                   'documentationUrl': 'https://example.com/guide.pdf',
                   'files': [{'source': name, 'destination': 'ecatalog/AddonManager/' + name}
                             for name in ('Rendering Optimization.vcmx', 'guide.pdf')]}
        (folder / 'package.json').write_text(json.dumps(package))
        _, manifest, output = self.run_build('ecatalog')
        entry = next(p for p in manifest['packages'] if p['id'] == package['id'])
        self.assertFalse(entry['restartRequired'])
        for field in ('developer', 'documentationDestination', 'documentationUrl'):
            self.assertEqual(entry[field], package[field])
        self.assertEqual(len(entry['contentFiles']), 2)
        with zipfile.ZipFile(output / (package['id'] + '-1.0.0.zip')) as archive:
            self.assertEqual(archive.read('Rendering Optimization.vcmx'), b'original component bytes')
            self.assertEqual(archive.read('guide.pdf'), b'%PDF-1.4 guide')
        self.save(manifest)
        unchanged, _, _ = self.run_build('ecatalog-unchanged')
        self.assertEqual(unchanged['count'], 0)

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

    def test_release_notes_override_manifest_and_package_metadata(self):
        _, manifest, _ = self.run_build('initial')
        self.save(manifest)
        note = 'Ctrl+wheel editor zoom fix'
        summary, updated, output = self.run_build(
            'release-notes', force_package='rck.studio', release_notes=note, force=True)
        self.assertEqual(summary['changed'], ['rck.studio-0.0.11.zip'])
        studio = next(package for package in updated['packages'] if package['id'] == 'rck.studio')
        self.assertEqual(studio['releaseNotes'], [note])
        with zipfile.ZipFile(output / 'rck.studio-0.0.11.zip') as archive:
            metadata = json.loads(archive.read('package.json'))
            self.assertEqual(metadata['releaseNotes'], [note])

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

    def test_manual_minor_does_not_bump_other_changed_package(self):
        _, manifest, _ = self.run_build('initial')
        self.save(manifest)
        (self.root / 'packages/CodeLens/payload/Plugin.CodeLens.dll').write_bytes(b'unrelated pending upload')
        summary, updated, _ = self.run_build('targeted', bump='minor', force_package='rck.studio')
        self.assertEqual(summary['changed'], ['rck.studio-0.1.0.zip'])
        codelens = next(p for p in updated['packages'] if p['id'] == 'rck.codelens')
        self.assertEqual(codelens['version'], '0.0.10')

    def test_studio_shorthand_and_patch(self):
        path = self.root / 'packages/Studio/package.json'
        package = json.loads(path.read_text())
        package['id'] = 'rck.rckstudio'
        path.write_text(json.dumps(package))
        for p in self.manifest['packages']:
            if p['id'] == 'rck.studio':
                p['id'] = 'rck.rckstudio'
        self.save(self.manifest)
        _, manifest, _ = self.run_build('initial')
        self.save(manifest)
        summary, _, _ = self.run_build('short-id', force_package='rck.studio', bump='patch', force=True)
        self.assertEqual(summary['changed'], ['rck.rckstudio-0.0.11.zip'])
        self.assertEqual(summary['package_id'], 'rck.rckstudio')

    def test_minor_major_require_explicit_package(self):
        with self.assertRaises(ValueError):
            self.run_build('ambiguous', bump='major')

    def test_inconsistent_manifest_is_repaired_with_a_new_valid_package(self):
        _, manifest, _ = self.run_build('initial')
        studio = next(p for p in manifest['packages'] if p['id'] == 'rck.studio')
        studio['version'] = '3.1.7'  # URL and ZIP still contain 0.0.10.
        self.save(manifest)
        summary, updated, output = self.run_build('repair')
        self.assertEqual(summary['changed'], ['rck.studio-3.1.8.zip'])
        package = next(p for p in updated['packages'] if p['id'] == 'rck.studio')
        self.assertTrue(package['downloadUrl'].endswith('rck.studio-3.1.8.zip'))
        with zipfile.ZipFile(output / 'rck.studio-3.1.8.zip') as archive:
            self.assertEqual(json.loads(archive.read('package.json'))['version'], package['version'])

    def test_ecatalog_is_published_and_cannot_write_vc_dlls(self):
        folder = self.root / 'packages/Conveyor'
        folder.mkdir()
        (folder / 'Conveyor.vcmx').write_bytes(b'VCMX component')
        metadata = {'id': 'rck.ecatalog.conveyor', 'name': 'Conveyor', 'type': 'ecatalog', 'version': '1.0.0',
                    'description': 'Sensor conveyor', 'restartRequired': False, 'vcVersions': ['5.1'],
                    'files': [{'source': 'Conveyor.vcmx', 'destination': 'ecatalog/rck.ecatalog.conveyor/Conveyor.vcmx'}]}
        (folder / 'package.json').write_text(json.dumps(metadata))
        _, manifest, _ = self.run_build('catalog')
        package = next(p for p in manifest['packages'] if p['id'] == metadata['id'])
        self.assertFalse(package['restartRequired'])
        self.assertEqual(package['contentFiles'][0]['destination'], metadata['files'][0]['destination'])
        metadata['files'][0]['destination'] = 'vcRoot/Plugin.Other.dll'
        (folder / 'package.json').write_text(json.dumps(metadata))
        with self.assertRaises(ValueError):
            self.run_build('bad-catalog')

    def test_manual_patch_after_automatic_release_does_not_bump_twice(self):
        _, manifest, output = self.run_build('automatic')
        apply(self.root, output)
        summary, updated, _ = self.run_build('manual-patch', force_package='rck.studio')
        self.assertEqual(summary['count'], 0)
        self.assertEqual(updated, manifest)

    def test_applied_package_version_matches_manifest_and_zip(self):
        _, manifest, output = self.run_build('automatic')
        original = json.loads((self.root / 'packages/Studio/package.json').read_text())
        self.assertEqual(original['version'], '0.0.9')  # Build does not alter sources before release upload.
        apply(self.root, output)
        source = json.loads((self.root / 'packages/Studio/package.json').read_text())
        entry = next(p for p in manifest['packages'] if p['id'] == source['id'])
        with zipfile.ZipFile(output / f"{entry['id']}-{entry['version']}.zip") as archive:
            metadata = json.loads(archive.read('package.json'))
        self.assertEqual(source['version'], entry['version'])
        self.assertEqual(source['version'], metadata['version'])
        self.assertEqual(self.run_build('unchanged')[0]['count'], 0)

    def test_previous_release_hashes_are_retained(self):
        _, manifest, output = self.run_build('first')
        apply(self.root, output)
        previous = next(p for p in manifest['packages'] if p['id'] == 'rck.studio')
        (self.root / 'packages/Studio/payload/Plugin.Studio.dll').write_bytes(b'newer DLL')
        _, updated, _ = self.run_build('second')
        package = next(p for p in updated['packages'] if p['id'] == 'rck.studio')
        snapshot = package['versions'][0]
        self.assertEqual(snapshot['version'], previous['version'])
        self.assertEqual(snapshot['mainDllSha256'], previous['mainDllSha256'])
        self.assertEqual(snapshot['contentFiles'], previous['contentFiles'])

    def test_apply_rejects_mismatched_version_before_modifying_sources(self):
        _, _, output = self.run_build('first')
        before = (self.root / 'manifest.json').read_bytes()
        updates = json.loads((output / 'package-updates.json').read_text())
        updates[0]['version'] = '99.0.0'
        (output / 'package-updates.json').write_text(json.dumps(updates))
        with self.assertRaises(ValueError):
            apply(self.root, output)
        self.assertEqual((self.root / 'manifest.json').read_bytes(), before)

    def test_apply_cli_accepts_default_relative_repo_root(self):
        _, manifest, output = self.run_build('cli')
        script = Path(__file__).with_name('apply_publish.py').resolve()
        result = subprocess.run([sys.executable, str(script), '--output-dir', str(output)], cwd=self.root,
                                check=True, capture_output=True, text=True)
        self.assertEqual(len(json.loads(result.stdout)), 2)
        applied = json.loads((self.root / 'manifest.json').read_text())
        self.assertEqual(applied, manifest)
        metadata = json.loads((self.root / 'packages/Studio/package.json').read_text())
        self.assertEqual(metadata['version'], '0.0.10')

    def test_existing_git_history_is_added_without_a_patch_bump(self):
        _, initial, output = self.run_build('initial')
        apply(self.root, output)
        old = next(p for p in initial['packages'] if p['id'] == 'rck.studio')
        old = dict(old, version='0.0.8', downloadUrl='https://github.com/owner/repo/releases/download/older/rck.studio-0.0.8.zip')
        old['mainDllSha256'] = 'A' * 64
        old['contentFiles'] = [{'destination': 'vcRoot/Plugin.Studio.dll', 'sha256': 'A' * 64}]
        (self.root / '.git').mkdir()
        history = json.dumps({'packages': [old]})
        with patch('auto_publish.subprocess.run', side_effect=[
            SimpleNamespace(stdout=('a' * 40) + '\n'), SimpleNamespace(stdout=history)
        ]):
            summary, updated, _ = self.run_build('history-backfill')
        self.assertEqual(summary['count'], 0)
        self.assertTrue(summary['manifest_changed'])
        current = next(p for p in updated['packages'] if p['id'] == 'rck.studio')
        self.assertEqual(current['version'], '0.0.10')
        self.assertTrue(any(p['version'] == '0.0.8' and p['mainDllSha256'] == 'A' * 64 for p in current['versions']))

    def test_stale_source_version_is_synchronized_without_new_release(self):
        _, initial, output = self.run_build('initial')
        self.save(initial)
        summary, unchanged, repaired = self.run_build('metadata-only')
        self.assertEqual(summary['count'], 0)
        self.assertTrue(summary['metadata_changed'])
        self.assertEqual(unchanged, initial)
        apply(self.root, repaired)
        metadata = json.loads((self.root / 'packages/Studio/package.json').read_text())
        self.assertEqual(metadata['version'], '0.0.10')
        after, _, _ = self.run_build('already-synced')
        self.assertEqual(after['count'], 0)
        self.assertFalse(after['metadata_changed'])

    def test_editing_only_source_version_does_not_raise_release_version(self):
        _, _, output = self.run_build('initial')
        apply(self.root, output)
        path = self.root / 'packages/Studio/package.json'
        metadata = json.loads(path.read_text())
        metadata['version'] = '99.0.0'
        path.write_text(json.dumps(metadata))
        summary, updated, repair = self.run_build('version-only')
        self.assertEqual(summary['count'], 0)
        self.assertTrue(summary['metadata_changed'])
        self.assertEqual(next(p for p in updated['packages'] if p['id'] == 'rck.studio')['version'], '0.0.10')
        apply(self.root, repair)
        self.assertEqual(json.loads(path.read_text())['version'], '0.0.10')


if __name__ == '__main__':
    unittest.main()

