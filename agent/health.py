import json
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:4080/internal/health", timeout=8) as response:
    assert json.load(response)["ok"]
