import json
import os
import pathlib
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Webhook(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/disconnect":
            self.close_connection = True
            return
        self.send_response(200 if self.path == "/ok" else 500)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.mark.parametrize("path,warns", [("/ok", False), ("/fail", True), ("/disconnect", True)])
def test_notification_failure_warns_without_failing_rotation(tmp_path, path, warns):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Webhook)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    playbook = tmp_path / "notify.json"
    playbook.write_text(json.dumps([{
        "hosts": "localhost",
        "gather_facts": False,
        "vars": {
            "ansible_python_interpreter": sys.executable,
            "ansible_date_time": {"iso8601": "2026-01-01T00:00:00Z"},
            "ssh_key_rotation_notify_url": f"http://127.0.0.1:{server.server_port}{path}",
            "ssh_key_rotation_owner_email": "ops@example.com",
            "ssh_key_rotation_new_fingerprints": {"results": [{"stdout": "SHA256:example"}]},
        },
        "tasks": [{"ansible.builtin.include_tasks": str(
            ROOT / "roles/ssh_key_rotation/tasks/notify.yml"
        )}],
    }]))
    try:
        result = subprocess.run(
            ["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook)],
            capture_output=True, text=True,
            env=dict(os.environ, ANSIBLE_CONFIG=str(ROOT / "ansible.cfg")),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert ("warning: rotation notification for localhost did not succeed" in output) is warns
