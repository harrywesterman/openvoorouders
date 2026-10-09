import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openvoorouders.lifecycle import Lifecycle
from openvoorouders.manifest import validate, ReleaseError
from openvoorouders.storage import atomic, lock
from openvoorouders.runtime import environment
from openvoorouders.integrity import managed_checksums

ROOT = Path(__file__).resolve().parents[1]


def release(version='0.1.0', previous=None):
    data = json.loads((ROOT / 'releases/candidate.json').read_text())
    data.update(version=version, status='stable', upgrade_from=previous or [])
    data['images'] = {name: 'example.org/' + name + '@sha256:' + 'a' * 64 for name in ['webtrees','agent','database']}
    data['host'] = {'url':'https://example.org/host.tar.gz','sha256':'b'*64}
    return data


class Runtime:
    def __init__(self):
        self.events = []
        self.active = False
        self.extras = []
        self.fail = None
        self.migrate = lambda: None
    def action(self, event):
        self.events.append(event)
        if self.fail == event: raise RuntimeError('injected ' + event)
    def pull(self, target): self.action('pull')
    def busy(self): self.action('busy'); return self.active
    def inventory(self): self.action('inventory'); return self.extras
    def stop(self): self.action('stop')
    def start(self): self.action('start'); self.migrate()
    def verify(self): self.action('verify')


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for path in ['data/database','data/webtrees','data/research/public/dossiers','data/opencode','data/agent-config','data/modules/extra','secrets','control','host/bin','host/openvoorouders']:
            (self.root/path).mkdir(parents=True)
        self.original = {'data/database/schema':'schema-before', 'data/webtrees/scan.jpg':'scan',
                         'data/research/public/dossiers/I1.md':'uncertainty + sources', 'data/opencode/conversation':'conversation',
                         'data/agent-config/settings':'custom endpoint', 'data/modules/extra/module.php':'extra-plugin',
                         'secrets/agent':'private-key', 'host/bin/openvoorouders':'old-updater', 'host/openvoorouders/cli.py':'old-code'}
        for name, value in self.original.items(): (self.root/name).write_text(value)
        (self.root/'data/modules/openvoorouders').symlink_to('/opt/managed-modules/openvoorouders')
        os.chmod(self.root/'secrets/agent',0o440)
        (self.root/'compose.yaml').write_text('old-compose')
        self.config = {'bind':'127.0.0.1','port':8080,'url':'http://localhost:8080','managed_files':managed_checksums(self.root)}
        atomic(self.root/'installation.json',self.config)
        self.old = release()
        self.new = release('0.2.0',['0.1.0'])
        atomic(self.root/'current.json',self.old,0o644)
        environment(self.root,self.old,self.config)
        self.runtime = Runtime()
        self.life = Lifecycle(self.root,self.runtime)
        self.life.maintenance(False)
        self.staged = self.root/'staged/content'
        self.staged.mkdir(parents=True)
        (self.staged/'compose.yaml').write_text('new-compose')
        self.patch = patch('openvoorouders.lifecycle.prepare_host',return_value=self.staged)
        self.patch.start(); self.addCleanup(self.patch.stop)

    def test_success_preserves_data_downloads_first(self):
        self.life.update(self.new)
        self.assertEqual(self.life.read('current.json')['version'],'0.2.0')
        for name, value in self.original.items():
            if not name.startswith('host/'): self.assertEqual((self.root/name).read_text(),value)
        self.assertLess(self.runtime.events.index('pull'),self.runtime.events.index('stop'))
        self.assertFalse(self.life.pending())
        self.assertFalse(self.life.read('control/maintenance.json')['enabled'])
        self.assertTrue(Path(self.life.read('update.json')['backup']).exists())
        self.assertEqual((self.root/'compose.yaml').read_text(),'new-compose')

    def test_opencode_cache_is_not_restored_but_settings_and_lock_are(self):
        import tarfile
        cache=self.root/'data/agent-config/node_modules/.bin'
        cache.mkdir(parents=True)
        (cache/'tool').symlink_to('../package/tool.js')
        (self.root/'data/agent-config/package-lock.json').write_text('pinned plugin dependencies')
        self.life.update(self.new)
        backup=Path(self.life.read('update.json')['backup'])
        with tarfile.open(backup/'state.tar') as archive:
            names=archive.getnames()
        self.assertFalse(any(n.startswith('data/agent-config/node_modules') for n in names))
        self.assertIn('data/agent-config/package-lock.json',names)
        self.life.restore()
        self.assertEqual((self.root/'data/agent-config/package-lock.json').read_text(),'pinned plugin dependencies')
        self.assertEqual((self.root/'data/agent-config/settings').read_text(),'custom endpoint')
        self.assertFalse((self.root/'data/agent-config/node_modules').exists())

    def test_full_restore_includes_schema_secrets_host_and_modules(self):
        self.runtime.migrate = lambda: (self.root/'data/database/schema').write_text('schema-after')
        self.runtime.fail = 'verify'
        with self.assertRaises(RuntimeError): self.life.update(self.new)
        self.assertTrue(self.life.pending())
        self.assertTrue(self.life.read('control/maintenance.json')['enabled'])
        self.runtime.migrate = lambda: None
        self.runtime.fail = None
        self.life.restore()
        for name,value in self.original.items(): self.assertEqual((self.root/name).read_text(),value)
        self.assertEqual((self.root/'secrets/agent').stat().st_mode & 0o777,0o440)
        self.assertEqual(self.life.read('current.json')['version'],'0.1.0')
        self.assertEqual((self.root/'compose.yaml').read_text(),'old-compose')
        self.assertTrue(list(self.root.glob('failed-state-*/data')))
        self.assertFalse(self.life.pending())

    def test_restore_can_resume_after_power_loss_during_file_moves(self):
        self.runtime.fail = 'verify'
        with self.assertRaises(RuntimeError): self.life.update(self.new)
        self.runtime.fail = None
        real = os.replace
        def interrupted(source,target):
            if str(source).endswith('restore-staging/secrets'): raise OSError('power failure')
            return real(source,target)
        with patch('openvoorouders.lifecycle.os.replace',side_effect=interrupted):
            with self.assertRaises(OSError): self.life.restore()
        self.assertTrue(self.life.pending())
        Lifecycle(self.root,self.runtime).restore()
        for name,value in self.original.items(): self.assertEqual((self.root/name).read_text(),value)

    def test_unknown_upgrade_does_not_touch_running_app(self):
        self.new['upgrade_from']=[]
        with self.assertRaises(ReleaseError): self.life.update(self.new)
        self.assertEqual(self.runtime.events,[])

    def test_enabled_unknown_extra_blocks(self):
        self.runtime.extras=[{'name':'extra','version':'unknown','enabled':True}]
        with self.assertRaisesRegex(RuntimeError,'aanvullende modules'): self.life.update(self.new)
        self.assertNotIn('pull',self.runtime.events)

    def test_disabled_extra_preserved(self):
        self.runtime.extras=[{'name':'extra','version':'unknown','enabled':False}]
        self.life.update(self.new)
        self.assertEqual((self.root/'data/modules/extra/module.php').read_text(),'extra-plugin')

    def test_active_job_does_not_stop(self):
        self.runtime.active=True
        with self.assertRaisesRegex(RuntimeError,'loopt onderzoek'): self.life.update(self.new)
        self.assertNotIn('stop',self.runtime.events)

    def test_job_start_race_cancels_maintenance(self):
        with patch.object(self.runtime,'busy',side_effect=[False,True]):
            with self.assertRaisesRegex(RuntimeError,'zojuist'): self.life.update(self.new)
        self.assertNotIn('stop',self.runtime.events)
        self.assertFalse(self.life.read('control/maintenance.json')['enabled'])

    def test_failed_download_leaves_app_available(self):
        self.runtime.fail='pull'
        with self.assertRaises(RuntimeError): self.life.update(self.new)
        self.assertNotIn('stop',self.runtime.events)
        self.assertFalse(self.life.read('control/maintenance.json')['enabled'])
        self.assertFalse(self.life.pending())

    def test_low_disk_blocks_before_download(self):
        with patch('openvoorouders.lifecycle.shutil.disk_usage') as usage:
            usage.return_value.free=1
            with self.assertRaisesRegex(RuntimeError,'vrije ruimte'): self.life.update(self.new)
        self.assertNotIn('pull',self.runtime.events)

    def test_modified_compose_blocks(self):
        (self.root/'compose.yaml').write_text('locally modified')
        with self.assertRaisesRegex(RuntimeError,'lokaal gewijzigd'): self.life.update(self.new)
        self.assertEqual(self.runtime.events,[])

    def test_modified_host_code_blocks(self):
        (self.root/'host/openvoorouders/cli.py').write_text('locally changed updater')
        with self.assertRaisesRegex(RuntimeError,'lokaal gewijzigd'): self.life.update(self.new)
        self.assertEqual(self.runtime.events,[])

    def test_incomplete_backup_never_begins_migration(self):
        with patch.object(self.life,'snapshot',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.life.update(self.new)
        self.assertNotIn('start',self.runtime.events)
        self.assertTrue(self.life.pending())
        self.life.cancel()
        self.assertFalse(self.life.pending())
        self.assertEqual(self.life.read('current.json')['version'],'0.1.0')

    def test_failed_schema_migration_requires_full_restore(self):
        self.runtime.fail='start'
        with self.assertRaises(RuntimeError): self.life.update(self.new)
        with self.assertRaisesRegex(RuntimeError,'volledig herstel'): self.life.cancel()

    def test_corrupt_backup_never_replaces_live_data(self):
        self.life.update(self.new)
        backup=Path(self.life.read('update.json')['backup'])
        (backup/'state.tar').write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError,'beschadigd'): self.life.restore()
        self.assertEqual(self.life.read('current.json')['version'],'0.2.0')

    def test_pending_transaction_blocks_next_update_after_restart(self):
        self.runtime.fail='stop'
        with self.assertRaises(RuntimeError): self.life.update(self.new)
        with self.assertRaisesRegex(RuntimeError,'eerdere update'): Lifecycle(self.root,self.runtime).update(self.new)

    def test_daily_backup_covers_every_state_directory(self):
        backup=Path(self.life.backup())
        self.assertTrue((backup/'receipt.json').exists())
        self.assertFalse(self.life.pending())
        self.assertFalse(self.life.read('control/maintenance.json')['enabled'])

    def test_backup_health_failure_keeps_maintenance(self):
        self.runtime.fail='verify'
        with self.assertRaises(RuntimeError): self.life.backup()
        self.assertTrue(self.life.pending())
        self.assertTrue(self.life.read('control/maintenance.json')['enabled'])

    def test_backup_refuses_unmanaged_symlink(self):
        (self.root/'data/research/leak').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(RuntimeError,'link'): self.life.backup()

    def test_lock_prevents_two_updaters(self):
        with lock(self.root):
            with self.assertRaisesRegex(RuntimeError,'loopt al'): self.life.update(self.new)


class ManifestTests(unittest.TestCase):
    def test_candidate_cannot_be_installed(self):
        with self.assertRaisesRegex(ReleaseError,'kandidaat'): validate(json.loads((ROOT/'releases/candidate.json').read_text()))
    def test_moving_image_rejected(self):
        r=release();r['images']['agent']='example.org/agent:latest'
        with self.assertRaises(ReleaseError): validate(r)
    def test_missing_checksum_rejected(self):
        r=release();r['components']['faces']['sha256']=''
        with self.assertRaises(ReleaseError): validate(r)
    def test_malicious_module_path_rejected(self):
        r=release();r['components']['faces']['folder']='../../evil'
        with self.assertRaises(ReleaseError): validate(r)
    def test_full_snapshot_mandatory(self):
        r=release();r['migration']['recovery']='images-only'
        with self.assertRaises(ReleaseError): validate(r)

if __name__=='__main__': unittest.main()
