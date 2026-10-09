import importlib.util
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('ovo_agent',Path(__file__).resolve().parents[1]/'agent/server.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        a.DATA=Path(self.temp.name)/'data';a.CONTROL=Path(self.temp.name)/'control';a.CONTROL.mkdir()
        a.KEY='test-only-key-'+'a'*40
        self.home=Path(self.temp.name)/'home'
        homepatch=patch.object(a.Path,'home',return_value=self.home);homepatch.start();self.addCleanup(homepatch.stop)
        a.init()
        self.calls=[]
        self.status={'s_test':{'type':'busy'}}
        def engine(method,path,body=None,directory=None,timeout=30):
            self.calls.append((method,path,body,directory))
            if path=='/provider': return {'all':[{'id':'local','models':{'good':{'capabilities':{'toolcall':True}},'no-tools':{'capabilities':{'toolcall':False}}}}]}
            if path=='/session' and method=='POST': return {'id':'s_test'}
            if path=='/session/status': return self.status
            if path.endswith('/message'): return []
            if path=='/global/health': return {'healthy':True}
            return True
        self.patch=patch.object(a,'engine',side_effect=engine);self.patch.start();self.addCleanup(self.patch.stop)
        self.launch=patch.object(a,'start_engine');self.launch.start();self.addCleanup(self.launch.stop)
        self.threads=patch.object(a.threading.Thread,'start');self.threads.start();self.addCleanup(self.threads.stop)
        self.body={'provider':'local','model':'good','private':False,'prompt':'Onderzoek I1 met bronnen','tree':'stamboom','webtrees_token':'scoped-token'}

    def test_default_research_uses_public_directory_and_exact_model(self):
        job=a.research(self.body)
        self.assertTrue(a.busy())
        call=next(c for c in self.calls if c[1].endswith('/prompt_async'))
        self.assertEqual(call[2]['model'],{'providerID':'local','modelID':'good'})
        self.assertEqual(call[3],a.DATA/'public')
        self.assertEqual(job['state'],'running')

    def test_private_requires_consent_before_launch(self):
        with self.assertRaisesRegex(ValueError,'toestemming'): a.research(self.body|{'private':True})
        a.start_engine.assert_not_called()

    def test_consent_is_specific_to_provider(self):
        a.dispatch('POST','/consent',{'provider':'other','enabled':True})
        a.start_engine.reset_mock()
        with self.assertRaises(ValueError): a.research(self.body|{'private':True})
        a.start_engine.assert_not_called()

    def test_private_consent_allows_only_private_workspace(self):
        a.dispatch('POST','/consent',{'provider':'local','enabled':True})
        a.research(self.body|{'private':True})
        a.start_engine.assert_called_with('private','scoped-token')
        call=next(c for c in self.calls if c[1].endswith('/prompt_async'))
        self.assertEqual(call[3],a.DATA/'private')

    def test_no_fallback_on_unknown_model(self):
        with self.assertRaisesRegex(ValueError,'beschikbaar model'): a.research(self.body|{'model':'absent'})
        self.assertFalse(a.busy())
        self.assertFalse(any(c[1].endswith('prompt_async') for c in self.calls))

    def test_model_without_tools_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'toolgebruik'): a.research(self.body|{'model':'no-tools'})
        self.assertFalse(a.busy())

    def test_one_job_at_a_time(self):
        a.research(self.body)
        with self.assertRaisesRegex(ValueError,'loopt onderzoek'): a.research(self.body)
        self.assertEqual(sum(c[1]=='/session' for c in self.calls),1)

    def test_update_sees_busy_before_engine_start_and_failed_start_releases_it(self):
        def launch(*args):
            self.assertTrue(a.dispatch('GET','/internal/status',{})['busy'])
            raise RuntimeError('injected startup failure')
        a.start_engine.side_effect=launch
        with self.assertRaisesRegex(RuntimeError,'startup failure'):
            a.research(self.body)
        self.assertFalse(a.busy())

    def test_maintenance_rejects_new_research(self):
        (a.CONTROL/'maintenance.json').write_text('{"enabled":true}')
        with self.assertRaisesRegex(ValueError,'onderhoud'): a.research(self.body)
        a.start_engine.assert_not_called()

    def test_no_webtrees_token_cannot_start(self):
        with self.assertRaisesRegex(ValueError,'koppeling'): a.research(self.body|{'webtrees_token':''})
        self.assertFalse(a.busy())

    def test_stop_waits_for_engine_to_stop(self):
        job=a.research(self.body)
        result=a.dispatch('POST','/jobs/'+job['id']+'/stop',{})
        self.assertEqual(result['state'],'stopping')
        self.assertTrue(a.busy())
        self.status={}
        result=a.dispatch('POST','/jobs/'+job['id']+'/stop',{})
        self.assertEqual(result['state'],'stopped')
        self.assertFalse(a.busy())

    def test_restart_marks_lost_job_interrupted_not_successful(self):
        job=a.research(self.body);a.init()
        self.assertFalse(a.busy())
        row=a.dispatch('GET','/jobs',{})[0]
        self.assertEqual(row['id'],job['id']);self.assertEqual(row['state'],'interrupted')

    def test_can_continue_existing_conversation(self):
        job=a.research(self.body)
        self.status={};a.dispatch('POST','/jobs/'+job['id']+'/stop',{})
        self.calls=[]
        a.research(self.body|{'continue':job['id'],'prompt':'Onderzoek nu zijn ouders'})
        self.assertFalse(any(c[1]=='/session' for c in self.calls))
        self.assertTrue(any(c[1]=='/session/s_test/prompt_async' for c in self.calls))

    def test_cannot_continue_private_session_as_public(self):
        a.dispatch('POST','/consent',{'provider':'local','enabled':True})
        job=a.research(self.body|{'private':True})
        self.status={};a.dispatch('POST','/jobs/'+job['id']+'/stop',{})
        with self.assertRaisesRegex(ValueError,'privacykeuze'): a.research(self.body|{'continue':job['id']})

    def test_revoke_does_not_interrupt_running_job(self):
        a.dispatch('POST','/consent',{'provider':'local','enabled':True})
        a.research(self.body|{'private':True})
        with self.assertRaisesRegex(ValueError,'afgerond'): a.dispatch('POST','/consent',{'provider':'local','enabled':False})

    def test_native_oauth_prompts_are_forwarded(self):
        body={'method':1,'inputs':{'deploymentType':'enterprise','enterpriseUrl':'https://example.org'}}
        a.dispatch('POST','/providers/github-copilot/oauth',body)
        self.assertIn(('POST','/provider/github-copilot/oauth/authorize',body,None),self.calls)

    def test_does_not_offer_arbitrary_proxy(self):
        with self.assertRaisesRegex(ValueError,'Onbekende actie'): a.dispatch('POST','/session/something/delete',{})

    def test_custom_endpoint_persists_without_overriding_security_config(self):
        body={'provider':'eigen-test','name':'Lokaal','url':'http://host.docker.internal:11434/v1','model':'test-model', 'tools':True}
        a.dispatch('POST','/providers/custom',body)
        config=json.loads((self.home/'.config/opencode/opencode.json').read_text())
        self.assertEqual(config['provider']['eigen-test']['options']['baseURL'],body['url'])
        self.assertTrue(config['provider']['eigen-test']['models']['test-model']['tool_call'])
        self.assertNotIn('permission',config)

    def test_custom_endpoint_refuses_key_in_url_or_builtin_override(self):
        body={'provider':'eigen-test','name':'Lokaal','url':'https://example.org/v1?key=secret','model':'test-model'}
        with self.assertRaises(ValueError): a.dispatch('POST','/providers/custom',body)
        with self.assertRaises(ValueError): a.dispatch('POST','/providers/custom',body|{'provider':'openai','url':'https://example.org/v1'})

    def test_export_excludes_tokens_and_tool_payloads(self):
        key='provider-test-key-12345678'
        a.dispatch('POST','/providers/custom',{'provider':'eigen-test','name':'Lokaal','url':'http://host.docker.internal:11434/v1','model':'test','key':key})
        (a.DATA/'public/dossiers/I1.md').write_text('Bron https://archive.example/?token=temporary-token en '+key)
        output=a.dispatch('GET','/export',{})
        text=json.dumps(output)
        self.assertNotIn(key,text);self.assertNotIn('temporary-token',text);self.assertNotIn(a.KEY,text)
        self.assertIn('sleutel verwijderd',text)

    def test_adapter_requires_secret_for_browser_access(self):
        # Restore real threading start just for the HTTP server.
        self.threads.stop()
        server=a.ThreadingHTTPServer(('127.0.0.1',0),a.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            url='http://127.0.0.1:'+str(server.server_port)
            with self.assertRaises(urllib.error.HTTPError) as e: urllib.request.urlopen(url+'/providers')
            self.assertEqual(e.exception.code,401)
            e.exception.close()
            with urllib.request.urlopen(url+'/internal/status') as r: self.assertFalse(json.load(r)['busy'])
            request=urllib.request.Request(url+'/providers',headers={'Authorization':'Bearer '+a.KEY})
            with urllib.request.urlopen(request) as r: self.assertEqual(json.load(r)['all'][0]['id'],'local')
        finally: server.shutdown();server.server_close();worker.join()

if __name__=='__main__':unittest.main()
