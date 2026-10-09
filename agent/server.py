#!/usr/bin/env python3
"""Interne adapter naar de vastgezette OpenCode HTTP API; nooit publiek publiceren."""
import base64
import contextlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA = Path(os.environ.get("OVO_DATA", "/workspace"))
CONTROL = Path(os.environ.get("OVO_CONTROL", "/opt/ovo-control"))
KEY = os.environ.get("OVO_AGENT_KEY") or (Path("/run/secrets/agent").read_text().strip() if Path("/run/secrets/agent").exists() else "")
ENGINE = os.environ.get("OVO_OPENCODE_URL", "http://127.0.0.1:4096")
MUTEX = threading.RLock()
PROCESS = None
STARTING = False


@contextlib.contextmanager
def database():
    con = sqlite3.connect(DATA / "jobs.sqlite", timeout=15)
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()


def init():
    if len(KEY) < 32:
        raise RuntimeError("Interne agentsleutel ontbreekt.")
    DATA.mkdir(parents=True, exist_ok=True)
    with database() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, session TEXT NOT NULL,
            provider TEXT NOT NULL, model TEXT NOT NULL, private INTEGER NOT NULL,
            state TEXT NOT NULL, prompt TEXT NOT NULL, created INTEGER NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS one_active ON jobs((1)) WHERE state IN ('starting','running','stopping');
        CREATE TABLE IF NOT EXISTS consent(provider TEXT PRIMARY KEY, enabled INTEGER NOT NULL);
        """)
        # OpenCode is a child process; no job can still run after adapter restart.
        con.execute("UPDATE jobs SET state='interrupted' WHERE state IN ('starting','running','stopping')")
    for profile in ("public", "private"):
        (DATA / profile / "dossiers").mkdir(parents=True, exist_ok=True)


def maintenance():
    file = CONTROL / "maintenance.json"
    return file.exists() and json.loads(file.read_text()).get("enabled", True)


def busy():
    if STARTING:
        return True
    with database() as con:
        return con.execute("SELECT 1 FROM jobs WHERE state IN ('starting','running','stopping')").fetchone() is not None


@contextlib.contextmanager
def preparing_research():
    global STARTING
    STARTING = True
    try:
        yield
    finally:
        STARTING = False


def engine(method, path, body=None, directory=None, timeout=30):
    if directory:
        path += ("&" if "?" in path else "?") + urllib.parse.urlencode({"directory": str(directory)})
    headers = {"Authorization": "Basic " + base64.b64encode(("opencode:" + KEY).encode()).decode(),
               "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(ENGINE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        # Provider responses may contain credentials/request payloads; don't forward raw errors.
        raise ValueError(f"OpenCode kon deze actie niet uitvoeren (HTTP {exc.code}). Controleer je provider en instellingen.") from None


def start_engine(profile="public", token=""):
    global PROCESS
    if os.environ.get("OVO_OPENCODE_URL"):
        return  # Dependency injection for offline contract tests.
    if PROCESS and PROCESS.poll() is None:
        PROCESS.terminate()
        try:
            PROCESS.wait(timeout=15)
        except subprocess.TimeoutExpired:
            PROCESS.kill()
            PROCESS.wait()
    work = DATA / profile
    allowed = str(work) + "/**"
    writable = str(work / 'dossiers') + '/**'
    config = {
        "$schema": "https://opencode.ai/config.json", "share": "disabled",
        "instructions": ["/opt/skills/nederlands-onderzoek/SKILL.md"],
        "permission": {"*": "deny", "read": {"*": "deny", allowed: "allow", '/opt/skills/nederlands-onderzoek/**': 'allow'},
                       "edit": {"*": "deny", writable: "allow", '**/opencode.json': 'deny', '**/opencode.jsonc': 'deny', '**/.opencode/**': 'deny'}, "glob": "allow", "grep": "allow",
                       "list": "allow", "skill": "allow", "external_directory": {'*': 'deny', '/opt/skills/nederlands-onderzoek/**': 'allow'},
                       "webtrees*": "allow", "archiefakte*": "allow", "openarchieven*": "allow", "newspapers*": "allow"},
        "mcp": {
            "webtrees": {"type": "local", "command": ["node", "/opt/tools/webtrees-bin/webtrees-mcp.mjs"],
                         "enabled": bool(token), "environment": {"TOKEN": token,
                         "WEBTREES_MCP_URL": os.environ.get("WEBTREES_MCP_URL", "http://webtrees/mcp"),
                         "WEBTREES_UPLOAD_ROOTS": str(work)}},
            "openarchieven": {"type": "remote", "url": "https://mcp.openarchieven.nl/", "enabled": True},
            "archiefakte": {"type": "local", "command": ["uv", "--directory", "/opt/tools/archiefakte", "run", "--frozen", "--no-sync", "geldersarchief-mcp"],
                           "environment": {"GA_DATA_DIR": str(work / "scans"), "GA_USER_AGENT": "Openvoorouders/" + os.environ.get('OVO_RELEASE', 'development')}},
            "newspapers": {"type": "local", "command": ["node", "/opt/tools/delpher/build/index.js"]}
        }
    }
    config_path = DATA / "engine-config.json"
    config_path.write_text(json.dumps(config))
    os.chmod(config_path, 0o600)
    env = dict(os.environ, OPENCODE_SERVER_PASSWORD=KEY, OPENCODE_CONFIG=str(config_path))
    PROCESS = subprocess.Popen(["opencode", "serve", "--hostname", "127.0.0.1", "--port", "4096"],
                               cwd=work, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        if PROCESS.poll() is not None:
            raise RuntimeError("OpenCode is gestopt tijdens het opstarten.")
        try:
            if engine("GET", "/global/health").get("healthy"):
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError("OpenCode start niet op tijd.")


def model_capabilities(provider, model):
    catalogue = engine("GET", "/provider")
    selected = next((p for p in catalogue["all"] if p["id"] == provider), None)
    if not selected or model not in selected["models"]:
        raise ValueError("Kies een beschikbaar model bij je provider.")
    entry = selected["models"][model]
    if not entry.get("capabilities", {}).get("toolcall", entry.get("tool_call", False)):
        raise ValueError("Dit model biedt geen bevestigd toolgebruik voor archiefonderzoek.")
    return entry


def clean_export(value):
    secrets_to_remove = {KEY}
    secret_names = {'key', 'apikey', 'access', 'refresh', 'token', 'secret', 'password', 'authorization', 'webtreestoken', 'accesstoken', 'refreshtoken', 'clientsecret'}
    def sensitive(name):
        return re.sub('[^a-z]', '', name.lower()) in secret_names
    def collect(item):
        if isinstance(item, dict):
            for k, v in item.items():
                if sensitive(k) and isinstance(v, str) and v: secrets_to_remove.add(v)
                else: collect(v)
        elif isinstance(item, list):
            for v in item: collect(v)
    for file in [Path.home() / '.local/share/opencode/auth.json', Path.home() / '.config/opencode/opencode.json', DATA / 'engine-config.json']:
        if file.exists(): collect(json.loads(file.read_text()))
    def scrub(item):
        if isinstance(item, dict): return {k: '[sleutel verwijderd]' if sensitive(k) else scrub(v) for k, v in item.items()}
        if isinstance(item, list): return [scrub(v) for v in item]
        if isinstance(item, str):
            for secret in sorted(secrets_to_remove, key=len, reverse=True): item = item.replace(secret, '[sleutel verwijderd]')
            return re.sub(r'([?&](?:token|api_key|key|access_token|signature|sig)=)[^&\s]+', r'\1[verwijderd]', item, flags=re.I)
        return item
    return scrub(value)


def visible_progress(row, messages):
    visible = []
    for message in messages:
        info = message.get('info', {})
        parts = []
        for part in message.get('parts', []):
            if part.get('type') == 'text':
                parts.append({'type': 'text', 'text': part.get('text', '')})
            elif part.get('type') == 'tool':
                state = part.get('state', {})
                parts.append({'type': 'tool', 'tool': part.get('tool', ''),
                              'state': {k: state[k] for k in ('status', 'input', 'output', 'error') if k in state}})
        visible.append({'info': {'role': info.get('role', ''), **({'error': True} if info.get('error') else {})}, 'parts': parts})
    return clean_export({'job': {k: v for k, v in dict(row).items() if k != 'session'}, 'messages': visible})


def monitor(job_id, session, directory):
    failures = 0
    while True:
        time.sleep(1)
        try:
            status = engine("GET", "/session/status", directory=directory)
            failures = 0
            if status.get(session, {}).get("type", "idle") == "idle":
                messages = engine('GET', f'/session/{session}/message', directory=directory)
                failed = any(m.get('info', {}).get('error') for m in messages[-1:])
                with database() as con:
                    con.execute("UPDATE jobs SET state=CASE WHEN state='stopping' THEN 'stopped' ELSE ? END WHERE id=? AND state IN ('running','stopping')", ('failed' if failed else 'complete', job_id))
                return
        except (ValueError, OSError):
            failures += 1
            if failures >= 10:
                with database() as con:
                    con.execute("UPDATE jobs SET state='failed' WHERE id=? AND state IN ('running','stopping')", (job_id,))
                return


def research(body):
    with MUTEX:
        if maintenance() or busy():
            raise ValueError("Er loopt onderzoek of onderhoud. Probeer het straks opnieuw.")
        provider, model = body.get("provider", ""), body.get("model", "")
        private = bool(body.get("private", False))
        with database() as con:
            consent = con.execute("SELECT enabled FROM consent WHERE provider=?", (provider,)).fetchone()
        if private and (not consent or not consent["enabled"]):
            raise ValueError("Geef eerst expliciet toestemming voor privégegevens bij deze provider.")
        prompt = body.get("prompt", "").strip()
        if not prompt or len(prompt) > 20000:
            raise ValueError("Geef een onderzoeksvraag van maximaal 20.000 tekens.")
        # The PHP boundary supplies a freshly minted, scoped token. Never accept it from chat text.
        token = body.get("webtrees_token", "")
        if not token:
            raise ValueError("De webtrees-koppeling ontbreekt.")
        with preparing_research():
            start_engine("private" if private else "public", token)
            model_capabilities(provider, model)
            directory = DATA / ("private" if private else "public")
            previous = body.get('continue', '')
            if previous:
                if not re.fullmatch('[a-f0-9]{32}', previous):
                    raise ValueError('Ongeldig vervolgonderzoek.')
                with database() as con:
                    row = con.execute('SELECT * FROM jobs WHERE id=?', (previous,)).fetchone()
                if row is None or bool(row['private']) != private:
                    raise ValueError('Vervolgonderzoek moet dezelfde privacykeuze gebruiken.')
                session = row['session']
            else:
                session = engine("POST", "/session", {"title": prompt[:100]}, directory)["id"]
            job_id = secrets.token_hex(16)
            with database() as con:
                con.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)",
                            (job_id, session, provider, model, int(private), "starting", prompt, int(time.time())))
            try:
                engine("POST", f"/session/{session}/prompt_async", {"model": {"providerID": provider, "modelID": model},
                       "parts": [{"type": "text", "text": "Actieve boom: " + body["tree"] + "\n" + prompt}]}, directory)
                with database() as con:
                    con.execute("UPDATE jobs SET state='running' WHERE id=?", (job_id,))
                threading.Thread(target=monitor, args=(job_id, session, directory), daemon=True).start()
            except Exception:
                with database() as con:
                    con.execute("UPDATE jobs SET state='failed' WHERE id=?", (job_id,))
                raise
            return {"id": job_id, "state": "running"}


def dispatch(method, path, body):
    if path == "/internal/status":
        return {"busy": busy(), "maintenance": maintenance()}
    if path == "/internal/health":
        health = engine("GET", "/global/health")
        installed = Path('/opt/agent/release.json')
        expected = json.loads(installed.read_text())['components']['opencode']['version'] if installed.exists() else health.get('version')
        return {"ok": bool(health.get('healthy')) and health.get('version') == expected, 'opencode': health.get('version')}
    if method == "GET" and path == "/providers":
        providers = engine("GET", "/provider")
        config = engine('GET', '/config')
        custom = config.get('provider', {}) if isinstance(config, dict) else {}
        configured = set(custom)
        auth_file = Path.home() / '.local/share/opencode/auth.json'
        if auth_file.exists(): configured.update(json.loads(auth_file.read_text()))
        for provider in providers.get('all', []):
            if any(os.environ.get(name) for name in provider.get('env', [])): configured.add(provider['id'])
        providers['configured'] = sorted(configured)
        providers['configured_models'] = {name: list(settings['models']) for name, settings in custom.items() if settings.get('models')}
        return providers
    if method == "GET" and path == "/auth-methods":
        return engine("GET", "/provider/auth")
    if method == "GET" and path == "/consent":
        with database() as con:
            return {r['provider']: bool(r['enabled']) for r in con.execute('SELECT * FROM consent')}
    if method == "POST" and path == "/research":
        return research(body)
    if method == 'POST' and path == '/providers/custom':
        with MUTEX:
            if busy() or maintenance():
                raise ValueError('Rond onderzoek en onderhoud eerst af.')
            provider = body.get('provider', '')
            name = body.get('name', '').strip()
            url = urllib.parse.urlsplit(body.get('url', ''))
            model = body.get('model', '').strip()
            if not re.fullmatch(r'eigen-[a-z0-9-]{1,40}', provider) or not 1 <= len(name) <= 80 or not model or len(model) > 200:
                raise ValueError('Vul een eigen provider-ID, naam en model-ID in.')
            if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError('Gebruik een HTTP(S)-endpoint zonder toegangssleutel in de URL.')
            context = int(body.get('context', 32768)); output = int(body.get('output', 4096))
            if not 1024 <= output <= context <= 2000000:
                raise ValueError('Controleer de context- en uitvoerlimiet van je model.')
            config_path = Path.home() / '.config/opencode/opencode.json'
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config = json.loads(config_path.read_text()) if config_path.exists() else {}
            custom = {'npm': '@ai-sdk/openai-compatible', 'name': name, 'options': {'baseURL': body['url']},
                      'models': {model: {'name': model, 'tool_call': bool(body.get('tools')), 'limit': {'context': context, 'output': output},
                                        'modalities': {'input': ['text', 'image'] if body.get('image') else ['text'], 'output': ['text']}}}}
            if body.get('key'): custom['options']['apiKey'] = body['key']
            config.setdefault('provider', {})[provider] = custom
            temp = config_path.with_suffix('.temporary')
            temp.write_text(json.dumps(config)); os.chmod(temp, 0o600); os.replace(temp, config_path)
            start_engine()
            return {'saved': True}
    if method == "GET" and path == "/jobs":
        with database() as con:
            return [dict(r) for r in con.execute("SELECT id,provider,model,private,state,prompt,created FROM jobs ORDER BY created DESC LIMIT 100")]
    if method == 'GET' and path == '/export':
        if busy():
            raise ValueError('Rond het onderzoek af voordat je gesprekken exporteert.')
        with database() as con:
            jobs = [dict(r) for r in con.execute('SELECT * FROM jobs ORDER BY created')]
        output = []
        for job in jobs:
            directory = DATA / ('private' if job['private'] else 'public')
            messages = engine('GET', f"/session/{job['session']}/message", directory=directory)
            output.append({k: v for k, v in job.items() if k != 'session'} | {'messages': [
                {'role': m.get('info', {}).get('role'), 'text': '\n'.join(p.get('text', '') for p in m.get('parts', []) if p.get('type') == 'text')}
                for m in messages]})
        # Explicit text allow-list excludes auth stores, tool arguments and engine configuration.
        dossiers = {}
        for profile in ('public', 'private'):
            base = DATA / profile / 'dossiers'
            for file in base.rglob('*.md'):
                if not file.is_symlink() and file.is_file() and file.stat().st_size < 1024**2 and file.resolve().is_relative_to(base.resolve()):
                    dossiers[profile + '/' + str(file.relative_to(base))] = file.read_text()
        return clean_export({'conversations': output, 'dossiers': dossiers})
    match = re.fullmatch(r"/jobs/([a-f0-9]{32})(/stop|/progress)?", path)
    if match:
        with MUTEX, database() as con:
            row = con.execute("SELECT * FROM jobs WHERE id=?", (match[1],)).fetchone()
            if row is None:
                raise ValueError("Onderzoek bestaat niet.")
            directory = DATA / ("private" if row["private"] else "public")
            if match[2] == "/stop" and method == "POST":
                if row['state'] not in ('starting', 'running', 'stopping'):
                    raise ValueError('Dit onderzoek is al afgerond.')
                engine("POST", f"/session/{row['session']}/abort", {}, directory)
                status = engine('GET', '/session/status', directory=directory)
                state = 'stopped' if status.get(row['session'], {}).get('type', 'idle') == 'idle' else 'stopping'
                con.execute("UPDATE jobs SET state=? WHERE id=?", (state, row["id"]))
                return {"state": state}
            if match[2] in (None, '/progress') and method == "GET":
                messages = engine("GET", f"/session/{row['session']}/message", directory=directory)
                return visible_progress(row, messages) if match[2] else {"job": dict(row), "messages": messages}
    if method == "POST" and path == "/consent":
        with MUTEX, database() as con:
            if busy() or maintenance():
                raise ValueError("Wijzig toestemming nadat onderzoek en onderhoud zijn afgerond.")
            if not body.get("provider") or not isinstance(body.get("enabled"), bool):
                raise ValueError("Provider en expliciete toestemming zijn verplicht.")
            con.execute("INSERT INTO consent VALUES(?,?) ON CONFLICT(provider) DO UPDATE SET enabled=excluded.enabled",
                        (body["provider"], int(body["enabled"])))
            start_engine()  # revoke the member-scoped engine environment as well
        return {"saved": True}
    # Restricted pass-through for OpenCode provider authentication; no arbitrary engine proxy.
    match = re.fullmatch(r"/providers/([a-zA-Z0-9_.-]+)/(key|oauth|callback)", path)
    if method == "POST" and match:
        with MUTEX:
            if busy() or maintenance():
                raise ValueError("Wacht tot onderzoek en onderhoud zijn afgerond.")
            provider, action = match.groups()
            if action == "key":
                return engine("PUT", f"/auth/{provider}", {"type": "api", "key": body["key"]})
            return engine("POST", f"/provider/{provider}/oauth/" + ("authorize" if action == "oauth" else "callback"), body)
    raise ValueError("Onbekende actie.")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log prompts, cookies or credentials.

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        local_probe = self.client_address[0] == "127.0.0.1" and self.path in ("/internal/status", "/internal/health")
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if not local_probe and not hmac.compare_digest(supplied, KEY):
            self.respond(401, {"error": "Geen toegang."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= 100000:
                raise ValueError("Aanvraag te groot.")
            body = json.loads(self.rfile.read(size)) if size else {}
            if self.command != "GET" and maintenance():
                raise ValueError("Openvoorouders wordt bijgewerkt.")
            self.respond(200, dispatch(self.command, self.path, body))
        except (ValueError, KeyError, OSError, sqlite3.Error) as error:
            self.respond(400, {"error": str(error) if isinstance(error, ValueError) else "De actie is mislukt. Probeer opnieuw of controleer de koppeling."})

    def respond(self, code, body):
        raw = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    init()
    start_engine()
    ThreadingHTTPServer(("0.0.0.0", 4080), Handler).serve_forever()
