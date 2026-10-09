import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from openvoorouders.catalogue import refresh,upgrade_path
from openvoorouders.storage import atomic
from test_lifecycle import release


class CatalogueTests(unittest.TestCase):
    def test_skipped_versions_require_explicit_chain(self):
        entries=[{'manifest':release('0.3.0',['0.2.0'])},{'manifest':release('0.2.0',['0.1.0'])}]
        self.assertEqual([m['version'] for m in upgrade_path('0.1.0',entries)],['0.2.0','0.3.0'])
    def test_unknown_path_refused(self):
        with self.assertRaisesRegex(RuntimeError,'Geen getest'): upgrade_path('0.1.0',[{'manifest':release('0.3.0',['0.2.0'])}])
    def test_semantic_version_order(self):
        entries=[{'manifest':release('0.9.0',['0.1.0'])},{'manifest':release('0.10.0',['0.1.0'])}]
        self.assertEqual(upgrade_path('0.1.0',entries)[0]['version'],'0.10.0')
    def test_no_downgrade(self):
        self.assertEqual(upgrade_path('0.3.0',[{'manifest':release('0.2.0',['0.1.0'])}]),[])
    def test_network_failure_keeps_previous_catalogue_with_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            atomic(root/'control/releases.json',{'checked':'before','releases':[{'manifest':release()}]})
            with patch('openvoorouders.catalogue.fetch',side_effect=OSError('offline')): result=refresh(root)
            self.assertTrue(result['error']);self.assertEqual(result['checked'],'before');self.assertEqual(len(result['releases']),1)
    def test_drafts_and_prereleases_never_offered(self):
        with tempfile.TemporaryDirectory() as directory,patch('openvoorouders.catalogue.fetch',return_value=[{'draft':True,'prerelease':False},{'draft':False,'prerelease':True}]):
            self.assertEqual(refresh(Path(directory))['releases'],[])

if __name__=='__main__':unittest.main()
