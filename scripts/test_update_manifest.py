import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from update_manifest import main, read_package, build_manifest_entry


class ReleaseImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / 'assets'
        self.assets.mkdir()
        self.manifest = self.root / 'manifest.json'
        self.package = {
            'schemaVersion': 1, 'id': 'rck.ecatalog.sensor', 'name': 'Sensor', 'type': 'ecatalog',
            'version': '1.0.0', 'description': 'Sensor component', 'restartRequired': False, 'vcVersions': ['5.1'],
            'files': [{'source': 'Sensor.vcmx', 'destination': 'ecatalog/rck.ecatalog.sensor/Sensor.vcmx'}],
        }

    def write_zip(self):
        asset = self.assets / f"{self.package['id']}-{self.package['version']}.zip"
        with zipfile.ZipFile(asset, 'w') as zip:
            zip.writestr('package.json', json.dumps(self.package))
            zip.writestr('Sensor.vcmx', b'component')
        return asset

    def run_import(self):
        args = ['update_manifest.py', '--assets-dir', str(self.assets), '--manifest', str(self.manifest),
                '--repository', 'owner/repo', '--tag', 'test-release']
        with patch.object(sys, 'argv', args), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)
        return json.loads(self.manifest.read_text())['packages'][0]

    def test_release_import_preserves_documentation_and_developer(self):
        self.package.update(developer='Lee Junyong', documentationDestination='ecatalog/AddonManager/guide.pdf',
                            documentationUrl='https://example.com/guide.pdf')
        self.package['files'].append({'source': 'guide.pdf', 'destination': 'ecatalog/AddonManager/guide.pdf'})
        asset = self.write_zip()
        with zipfile.ZipFile(asset, 'a') as archive:
            archive.writestr('guide.pdf', b'%PDF-1.4 guide')
        package = read_package(asset)
        entry = build_manifest_entry(package, asset, 'owner/repo', 'test-release', '')
        for field in ('developer', 'documentationDestination', 'documentationUrl'):
            self.assertEqual(entry[field], self.package[field])
        self.assertEqual(len(entry['contentFiles']), 2)
        self.assertFalse(entry['restartRequired'])

    def test_ecatalog_zip_must_only_target_ecatalog(self):
        self.package['files'][0]['destination'] = 'vcRoot/Plugin.Other.dll'
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            read_package(self.write_zip())

    def test_same_content_preserves_auto_publish_fingerprint(self):
        old = dict(self.package, contentSha256='fingerprint', contentFiles=[{
            'destination': self.package['files'][0]['destination'],
            'sha256': hashlib.sha256(b'component').hexdigest().upper(),
        }])
        self.manifest.write_text(json.dumps({'schemaVersion': 1, 'packages': [old]}))
        asset = self.write_zip()
        updated = self.run_import()
        self.assertEqual(updated['contentSha256'], 'fingerprint')
        self.assertEqual(updated['version'], '1.0.0')
        self.assertEqual(updated['sha256'], hashlib.sha256(asset.read_bytes()).hexdigest().upper())

    def test_old_release_cannot_downgrade_current_manifest(self):
        old = dict(self.package, version='2.0.0', downloadUrl='current-release', contentSha256='fingerprint')
        self.manifest.write_text(json.dumps({'schemaVersion': 1, 'packages': [old]}))
        self.write_zip()
        self.assertEqual(self.run_import(), old)


if __name__ == '__main__':
    unittest.main()
