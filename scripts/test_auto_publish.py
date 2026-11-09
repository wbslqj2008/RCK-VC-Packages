import hashlib
import json
import shutil
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

    def test_explicit_version_plan_corrects_versions_and_preserves_individual_notes_once(self):
        _, _, initial = self.run_build('initial-plan-source')
        apply(self.root, initial)
        for name in ('Studio', 'CodeLens'):
            path = self.root / 'packages' / name / 'package.json'
            metadata = json.loads(path.read_text())
            metadata['releaseNotes'] = [name + ' specific changes']
            path.write_text(json.dumps(metadata))
        plan = self.root / 'release-plan.json'
        plan.write_text(json.dumps({'schemaVersion': 1, 'id': 'reviewed-baseline',
                                    'versions': {'rck.studio': '0.0.1', 'rck.codelens': '2.1.2'}}))
        summary, corrected, output = self.run_build('corrected', release_plan=plan, release_notes='generic commit title')
        self.assertEqual(summary['count'], 2)
        self.assertEqual(summary['release_plan_id'], 'reviewed-baseline')
        self.assertEqual(corrected['appliedReleasePlans'], ['reviewed-baseline'])
        for package in corrected['packages']:
            expected = '0.0.1' if package['id'] == 'rck.studio' else '2.1.2'
            self.assertEqual(package['version'], expected)
            self.assertEqual(package['releaseNotes'], [package['name'] + ' specific changes'])
            with zipfile.ZipFile(output / f"{package['id']}-{expected}.zip") as archive:
                metadata = json.loads(archive.read('package.json'))
                self.assertEqual(metadata['version'], expected)
                self.assertEqual(metadata['releaseNotes'], package['releaseNotes'])
        apply(self.root, output)
        unchanged, same, _ = self.run_build('plan-rerun', release_plan=plan)
        self.assertEqual(unchanged['count'], 0)
        self.assertEqual(same, corrected)
        (self.root / 'packages/Studio/payload/Plugin.Studio.dll').write_bytes(b'next real update')
        next_summary, next_manifest, _ = self.run_build('patch-after-plan', release_plan=plan)
        self.assertEqual(next_summary['changed'], ['rck.studio-0.0.2.zip'])
        self.assertEqual(next_manifest['appliedReleasePlans'], ['reviewed-baseline'])

    def test_version_plan_rejects_invalid_targets_and_ambiguous_manual_bumps(self):
        plan = self.root / 'release-plan.json'
        original = (self.root / 'manifest.json').read_bytes()
        for versions in ({'missing': '1.0.0'}, {'rck.studio': 'bad'}, {}):
            plan.write_text(json.dumps({'schemaVersion': 1, 'id': 'invalid-plan', 'versions': versions}))
            with self.assertRaises(ValueError):
                self.run_build('invalid-plan', release_plan=plan)
            self.assertEqual((self.root / 'manifest.json').read_bytes(), original)
        plan.write_text(json.dumps({'schemaVersion': 1, 'id': 'pending-plan', 'versions': {'rck.studio': '1.0.0'}}))
        with self.assertRaisesRegex(ValueError, 'pending release plan'):
            self.run_build('ambiguous-plan', release_plan=plan, bump='major', force_package='rck.studio')

    def run_build(self, tag, **kwargs):
        output = self.root / tag
        summary = build(self.root, output, 'owner/repo', tag, **kwargs)
        manifest = json.loads((output / 'manifest.next.json').read_text(encoding='utf-8'))
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

    def test_commit_notes_are_synchronized_and_do_not_cause_another_release(self):
        note = '설치 목록 분리 및 개수 표시'
        _, manifest, output = self.run_build('notes-sync', release_notes=note)
        source_path = self.root / 'packages/Studio/package.json'
        original = json.loads(source_path.read_text())
        self.assertNotIn('releaseNotes', original)
        apply(self.root, output)
        source = json.loads(source_path.read_text(encoding='utf-8'))
        studio = next(p for p in manifest['packages'] if p['id'] == source['id'])
        with zipfile.ZipFile(output / f"{source['id']}-{source['version']}.zip") as archive:
            packaged = json.loads(archive.read('package.json'))
        self.assertEqual(source['releaseNotes'], [note])
        self.assertEqual(source['releaseNotes'], studio['releaseNotes'])
        self.assertEqual(source['releaseNotes'], packaged['releaseNotes'])
        self.assertEqual(source['description'], original['description'])
        summary, unchanged, _ = self.run_build('notes-rerun', release_notes='automation commit')
        self.assertEqual(summary['count'], 0)
        self.assertFalse(summary['metadata_changed'])
        self.assertEqual(unchanged, manifest)
        source['releaseNotes'] = ['Manually edited release notes']
        source_path.write_text(json.dumps(source))
        changed, updated, _ = self.run_build('authored-notes')
        self.assertEqual(changed['changed'], ['rck.studio-0.0.11.zip'])
        self.assertEqual(next(p for p in updated['packages'] if p['id'] == source['id'])['releaseNotes'], source['releaseNotes'])

    def test_legacy_stale_notes_are_repaired_without_a_release_or_followup_bump(self):
        source_path = self.root / 'packages/Studio/package.json'
        source = json.loads(source_path.read_text())
        source['releaseNotes'] = ['Previous release notes']
        source_path.write_text(json.dumps(source))
        _, manifest, initial_output = self.run_build('legacy-notes', release_notes='Current published notes')
        apply(self.root, initial_output)
        studio = next(p for p in manifest['packages'] if p['id'] == source['id'])
        payload = source_path.parent / source['files'][0]['source']
        identity = {k: v for k, v in source.items() if k != 'version'}
        identity['content'] = [(source['files'][0]['source'], source['files'][0]['destination'],
                                hashlib.sha256(payload.read_bytes()).hexdigest().upper())]
        studio['contentSha256'] = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest().upper()
        source['version'] = studio['version']
        source_path.write_text(json.dumps(source))
        self.save(manifest)
        summary, repaired_manifest, output = self.run_build('repair-legacy')
        self.assertEqual(summary['count'], 0)
        self.assertTrue(summary['metadata_changed'])
        self.assertTrue(summary['manifest_changed'])
        self.assertEqual(list(output.glob('*.zip')), [])
        apply(self.root, output)
        synced = json.loads(source_path.read_text())
        self.assertEqual(synced['version'], studio['version'])
        self.assertEqual(synced['releaseNotes'], ['Current published notes'])
        second, unchanged, _ = self.run_build('repair-rerun')
        self.assertEqual(second['count'], 0)
        self.assertFalse(second['metadata_changed'])
        self.assertEqual(unchanged, repaired_manifest)

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

    def write_request(self, name, **request):
        path = self.root / 'packages' / name / 'package.json'
        package = json.loads(path.read_text(encoding='utf-8'))
        package['publishRequest'] = request
        path.write_text(json.dumps(package), encoding='utf-8')

    def publish_initial(self):
        summary, manifest, output = self.run_build('initial')
        apply(self.root, output)  # manifest and sources now at 0.0.10
        return summary, manifest, output

    def test_publish_request_minor_creates_one_release_and_is_removed(self):
        self.publish_initial()
        self.write_request('Studio', bump='minor', notes='새 기능', requestedBy='dev1')
        summary, manifest, output = self.run_build('request-minor', release_notes='commit title')
        entry = next(p for p in manifest['packages'] if p['id'] == 'rck.studio')
        self.assertEqual(summary['releases'], [{'id': 'rck.studio', 'from': '0.0.10', 'to': '0.1.0'}])
        self.assertEqual(entry['releaseNotes'], ['새 기능'])
        with zipfile.ZipFile(output / 'rck.studio-0.1.0.zip') as archive:
            self.assertNotIn('publishRequest', json.loads(archive.read('package.json')))
        apply(self.root, output)
        source = json.loads((self.root / 'packages/Studio/package.json').read_text(encoding='utf-8'))
        self.assertNotIn('publishRequest', source)
        self.assertEqual(source['version'], '0.1.0')

    def test_publish_request_does_not_change_fingerprint(self):
        _, manifest, _ = self.publish_initial()
        before = next(p for p in manifest['packages'] if p['id'] == 'rck.studio')['contentSha256']
        self.write_request('Studio', bump='patch', notes='x', requestedBy='dev1')
        summary, manifest, output = self.run_build('patch-unchanged')
        self.assertEqual(summary['count'], 0)
        self.assertEqual(next(p for p in manifest['packages'] if p['id'] == 'rck.studio')['contentSha256'], before)
        apply(self.root, output)
        source = json.loads((self.root / 'packages/Studio/package.json').read_text(encoding='utf-8'))
        self.assertNotIn('publishRequest', source)

    def test_publish_request_patch_with_changed_file_uses_request_notes(self):
        self.publish_initial()
        (self.root / 'packages/Studio/payload/Plugin.Studio.dll').write_bytes(b'changed')
        self.write_request('Studio', bump='patch', notes='버그 수정', requestedBy='dev1')
        summary, manifest, output = self.run_build('patch-changed', release_notes='commit title')
        self.assertEqual(summary['releases'][0]['to'], '0.0.11')
        entry = next(p for p in manifest['packages'] if p['id'] == 'rck.studio')
        self.assertEqual(entry['releaseNotes'], ['버그 수정'])
        with zipfile.ZipFile(output / 'rck.studio-0.0.11.zip') as archive:
            self.assertNotIn('publishRequest', json.loads(archive.read('package.json')))

    def test_publish_request_new_package_starts_at_source_version(self):
        folder = self.root / 'packages' / 'NewTool'
        (folder / 'payload').mkdir(parents=True)
        (folder / 'payload' / 'Plugin.NewTool.dll').write_bytes(b'new')
        package = {'id': 'rck.newtool', 'name': 'NewTool', 'type': 'addon', 'version': '1.0.0', 'description': 'd',
                   'restartRequired': True, 'vcVersions': ['5.1'], 'mainDll': 'Plugin.NewTool.dll',
                   'files': [{'source': 'payload/Plugin.NewTool.dll', 'destination': 'vcRoot/Plugin.NewTool.dll'}],
                   'publishRequest': {'bump': 'patch', 'notes': '최초 등록', 'requestedBy': 'dev1'}}
        (folder / 'package.json').write_text(json.dumps(package), encoding='utf-8')
        summary, _, _ = self.run_build('new-package')
        self.assertIn({'id': 'rck.newtool', 'from': None, 'to': '1.0.0'}, summary['releases'])

    def test_publish_request_rejects_unknown_bump(self):
        self.write_request('Studio', bump='huge', notes='x', requestedBy='dev1')
        with self.assertRaises(ValueError):
            self.run_build('bad-bump')

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


    def request_removal(self, *ids):
        (self.root / 'removal-requests.json').write_text(json.dumps({'schemaVersion': 1, 'ids': list(ids)}))

    def removal_requests(self):
        return json.loads((self.root / 'removal-requests.json').read_text(encoding='utf-8'))['ids']

    def test_requested_removal_leaves_manifest_without_a_release_and_clears_the_request(self):
        _, _, output = self.run_build('initial')
        apply(self.root, output)
        shutil.rmtree(self.root / 'packages' / 'CodeLens')
        self.request_removal('rck.codelens')
        summary, manifest, removal = self.run_build('removal')
        self.assertEqual(summary['removed'], ['rck.codelens'])
        self.assertEqual(summary['removal_pending'], [])
        self.assertTrue(summary['requests_changed'])
        self.assertEqual(summary['count'], 0)
        self.assertEqual(summary['releases'], [])
        self.assertTrue(summary['manifest_changed'])
        self.assertEqual([p['id'] for p in manifest['packages']], ['rck.studio'])
        self.assertEqual(list(removal.glob('*.zip')), [])
        apply(self.root, removal)
        self.assertEqual(self.removal_requests(), [])
        again, _, _ = self.run_build('after-removal')
        self.assertEqual(again['removed'], [])
        self.assertFalse(again['manifest_changed'])
        self.assertFalse(again['requests_changed'])

    def test_missing_folder_without_request_fails_and_changes_nothing(self):
        _, _, output = self.run_build('initial')
        apply(self.root, output)
        original = (self.root / 'manifest.json').read_bytes()
        # e.g. an edited package.json id: the old id has no folder any more
        path = self.root / 'packages/CodeLens/package.json'
        metadata = json.loads(path.read_text())
        metadata['id'] = 'rck.renamed'
        path.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, "패키지 폴더가 없습니다: rck.codelens. 삭제하려면 Addon Manager의 '저장소에서 삭제'를 사용하십시오."):
            self.run_build('unrequested')
        self.assertEqual((self.root / 'manifest.json').read_bytes(), original)
        self.assertFalse((self.root / 'unrequested' / 'manifest.next.json').exists())
        # A request for a different package does not cover it.
        self.request_removal('rck.studio')
        with self.assertRaisesRegex(ValueError, 'rck.codelens'):
            self.run_build('other-request')

    def test_empty_packages_folder_fails(self):
        _, _, output = self.run_build('initial')
        apply(self.root, output)
        original = (self.root / 'manifest.json').read_bytes()
        for name in ('Studio', 'CodeLens'):
            shutil.rmtree(self.root / 'packages' / name)
        self.request_removal('rck.studio', 'rck.codelens')
        with self.assertRaisesRegex(ValueError, 'package.json을 하나도 찾지 못했습니다'):
            self.run_build('empty')
        self.assertEqual((self.root / 'manifest.json').read_bytes(), original)

    def test_system_packages_cannot_be_removed(self):
        manifest = json.loads((self.root / 'manifest.json').read_text())
        manifest['packages'].append({'id': 'rck.addon-manager', 'name': 'RCK Addon Manager', 'type': 'addon', 'version': '2.0.6'})
        manifest['packages'].append({'id': 'rck.core', 'name': 'Core', 'type': 'addon', 'version': '1.0.0', 'systemPackage': True})
        self.save(manifest)
        original = (self.root / 'manifest.json').read_bytes()
        for package_id in ('rck.addon-manager', 'rck.core'):
            self.request_removal(package_id)
            with self.assertRaisesRegex(ValueError, '시스템 패키지는 삭제할 수 없습니다: ' + package_id):
                self.run_build('system-' + package_id)
            self.assertEqual((self.root / 'manifest.json').read_bytes(), original)

    def test_requested_package_with_folder_stays_published_and_requested(self):
        _, _, output = self.run_build('initial')
        apply(self.root, output)
        before = json.loads((self.root / 'manifest.json').read_text(encoding='utf-8'))
        self.request_removal('rck.studio', 'rck.gone')
        summary, manifest, pending = self.run_build('pending-removal')
        self.assertEqual(summary['removed'], [])
        self.assertEqual(summary['removal_pending'], ['rck.studio'])
        self.assertTrue(summary['requests_changed'])  # rck.gone was already absent: it is cleared
        self.assertEqual(manifest, before)
        apply(self.root, pending)
        self.assertEqual(self.removal_requests(), ['rck.studio'])

    def test_present_packages_are_not_removed(self):
        _, _, output = self.run_build('initial')
        apply(self.root, output)
        before = json.loads((self.root / 'manifest.json').read_text(encoding='utf-8'))
        summary, manifest, untouched = self.run_build('no-removal')
        self.assertEqual(summary['removed'], [])
        self.assertFalse(summary['manifest_changed'])
        self.assertFalse(summary['requests_changed'])
        self.assertEqual(manifest, before)
        self.assertFalse((untouched / 'removal-requests.next.json').exists())
        apply(self.root, untouched)
        self.assertFalse((self.root / 'removal-requests.json').exists())

    def test_invalid_removal_requests_file_fails(self):
        for text in ('{broken', json.dumps({'schemaVersion': 2, 'ids': []}), json.dumps({'schemaVersion': 1, 'ids': ['../x']})):
            (self.root / 'removal-requests.json').write_text(text)
            with self.assertRaisesRegex(ValueError, 'removal-requests.json'):
                self.run_build('invalid-requests')

    def test_applied_release_plan_may_name_a_removed_package(self):
        _, _, output = self.run_build('initial')
        apply(self.root, output)
        plan = self.root / 'release-plan.json'
        plan.write_text(json.dumps({'schemaVersion': 1, 'id': 'old-plan',
                                    'versions': {'rck.studio': '0.0.10', 'rck.codelens': '0.0.10'}}))
        manifest = json.loads((self.root / 'manifest.json').read_text(encoding='utf-8'))
        manifest['appliedReleasePlans'] = ['old-plan']
        self.save(manifest)
        shutil.rmtree(self.root / 'packages' / 'CodeLens')
        self.request_removal('rck.codelens')
        summary, updated, _ = self.run_build('removal-with-plan', release_plan=plan)
        self.assertEqual(summary['removed'], ['rck.codelens'])
        self.assertIsNone(summary['release_plan_id'])
        self.assertEqual(updated['appliedReleasePlans'], ['old-plan'])
        # A plan that is about to be applied still rejects the unknown package.
        manifest['appliedReleasePlans'] = []
        self.save(manifest)
        with self.assertRaisesRegex(ValueError, 'Unknown release plan package'):
            self.run_build('pending-plan-removed', release_plan=plan)

class AutoPublishWorkflowTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parent.parent / '.github' / 'workflows' / 'auto-publish.yml'
        self.text = path.read_text(encoding='utf-8')

    def test_publish_job_uses_protected_environment(self):
        self.assertIn('\n    environment: publish-bot\n', self.text)
        self.assertNotIn('HAS_PUBLISH_APP', self.text)
        self.assertIn('echo "has_app=${{ secrets.PUBLISH_APP_ID != \'\' }}" >> "$GITHUB_OUTPUT"', self.text)
        self.assertIn("if: steps.publish-app.outputs.has_app == 'true'", self.text)
        self.assertIn('${{ steps.app-token.outputs.token || github.token }}', self.text)

    def test_bot_commit_does_not_retrigger_publish_job(self):
        guard = ("if: \"github.event_name != 'push' || "
                 "!startsWith(github.event.head_commit.message, 'chore: auto-publish addon packages')\"")
        self.assertIn(guard, self.text)
        self.assertIn('git commit -m "chore: auto-publish addon packages $TAG"', self.text)

    def test_bot_commit_run_does_not_share_the_deploy_concurrency_group(self):
        # A skipped bot run in the shared group would cancel a pending deploy run.
        group = ("group: \"${{ (github.event_name == 'push' && "
                 "startsWith(github.event.head_commit.message, 'chore: auto-publish addon packages')) "
                 "&& format('rck-bot-{0}', github.run_id) || 'rck-manifest-update' }}\"")
        self.assertIn(group, self.text)
        self.assertIn('  cancel-in-progress: false', self.text)
        self.assertNotIn('\n  group: rck-manifest-update\n', self.text)

    def test_workflow_is_valid_yaml(self):
        # A plain (unquoted) YAML scalar may not contain ': ' — GitHub would reject the file.
        in_block = None
        for number, line in enumerate(self.text.splitlines(), 1):
            indent = len(line) - len(line.lstrip(' '))
            if in_block is not None and (not line.strip() or indent > in_block):
                continue
            in_block = None
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            body = stripped[2:] if stripped.startswith('- ') else stripped
            key, sep, value = body.partition(': ')
            value = value.strip()
            if not sep or not value:
                continue
            if value in ('|', '>') or value.startswith(('|', '>')):
                in_block = indent
                continue
            if value[0] in '"\'[{':
                continue
            self.assertNotIn(': ', value, f'line {number}: quote this value')
        try:
            import yaml
        except ImportError:
            return
        yaml.safe_load(self.text)

    def test_summary_lists_removed_packages(self):
        self.assertIn("for package_id in result.get('removed', []):", self.text)
        self.assertIn("print(f'- {package_id}: 삭제')", self.text)

    def test_push_retry_resolves_only_the_removal_requests_conflict(self):
        self.assertIn("\n      - 'scripts/resolve_removal_requests.py'\n", self.text)
        self.assertIn('if ! git pull --rebase origin main; then', self.text)
        self.assertIn('python scripts/resolve_removal_requests.py --repo-root . --summary .auto-release/summary.json', self.text)
        self.assertIn('git -c core.editor=true rebase --continue || { git rebase --abort; exit 1; }', self.text)
        self.assertIn('                git rebase --abort\n                exit 1\n', self.text)

    def test_removal_requests_trigger_the_run_and_are_committed(self):
        self.assertIn("\n      - 'removal-requests.json'\n", self.text)
        self.assertIn("steps.packages.outputs.requests_changed == 'true'", self.text)
        self.assertIn('if [ -f removal-requests.json ]; then git add removal-requests.json; fi', self.text)
        self.assertIn("result.get('removal_pending', [])", self.text)


if __name__ == '__main__':
    unittest.main()

