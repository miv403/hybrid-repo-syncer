#!/usr/bin/env python3
import http.server
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
import yaml

PORT = 8000
DEFAULT_SYNCER_EMAIL = "syncer@example.com"
SYNCER_EMAIL = DEFAULT_SYNCER_EMAIL

sync_lock = threading.Lock()

def get_syncer_emails() -> set[str]:
    """Collect all known syncer email addresses from environment, defaults, and sync-manifest.yaml."""
    emails = {DEFAULT_SYNCER_EMAIL.lower()}
    
    env_email = os.environ.get("SYNCER_EMAIL")
    if env_email:
        emails.add(env_email.strip().lower())

    env_emails = os.environ.get("SYNCER_EMAILS")
    if env_emails:
        for e in env_emails.split(","):
            if e.strip():
                emails.add(e.strip().lower())

    manifest_paths = [Path("/app/sync-manifest.yaml"), Path("sync-manifest.yaml")]
    for mp in manifest_paths:
        if mp.exists():
            try:
                with open(mp, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    m_email = data.get("authoring", {}).get("default_email")
                    if m_email and isinstance(m_email, str):
                        emails.add(m_email.strip().lower())
            except Exception:
                pass
    return emails

def execute_sync():
    print("[TRIGGER] Starting hybrid-syncer process in background...")
    try:
        manifest_paths = [Path("/app/sync-manifest.yaml"), Path("sync-manifest.yaml")]
        targets = []
        for mp in manifest_paths:
            if mp.exists():
                try:
                    with open(mp, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                        t_data = data.get("targets", {})
                        if isinstance(t_data, dict):
                            targets = list(t_data.keys())
                            break
                except Exception:
                    pass

        syncer_py = "/app/hybrid-syncer.py" if Path("/app/hybrid-syncer.py").exists() else "hybrid-syncer.py"
        if not targets:
            print("[ERROR] No targets found to sync.", file=sys.stderr)
            return

        for target in targets:
            res = subprocess.run(
                ["python3", syncer_py, "-v", "push", "-t", target],
                capture_output=True,
                text=True
            )
            if res.stdout:
                print(res.stdout)
            if res.returncode != 0:
                print(f"[ERROR] Push for target '{target}' failed:\n{res.stderr}", file=sys.stderr)
            else:
                print(f"[TRIGGER] Hybrid push for target '{target}' completed successfully.")
    finally:
        sync_lock.release()

class WebhookHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b""
        
        try:
            payload = json.loads(post_data.decode('utf-8')) if post_data else {}
            repo_name = payload.get('repository', {}).get('full_name', 'unknown')
            
            commits = payload.get('commits', [])
            if not isinstance(commits, list):
                commits = []

            # Check for GitOrigin-RevId watermark across head_commit and all commits
            all_messages = []
            head_commit_msg = payload.get('head_commit', {}).get('message', '')
            if head_commit_msg:
                all_messages.append(head_commit_msg)
            for c in commits:
                if isinstance(c, dict) and c.get('message'):
                    all_messages.append(c.get('message'))

            is_copybara_commit = any("GitOrigin-RevId:" in msg for msg in all_messages)

            # Collect all author, committer, pusher, and sender emails in payload
            payload_emails = set()
            for key in ('pusher', 'sender'):
                e = payload.get(key, {}).get('email', '')
                if e and isinstance(e, str):
                    payload_emails.add(e.strip().lower())

            head_author = payload.get('head_commit', {}).get('author', {}).get('email', '')
            if head_author and isinstance(head_author, str):
                payload_emails.add(head_author.strip().lower())

            head_committer = payload.get('head_commit', {}).get('committer', {}).get('email', '')
            if head_committer and isinstance(head_committer, str):
                payload_emails.add(head_committer.strip().lower())

            for c in commits:
                if isinstance(c, dict):
                    a_e = c.get('author', {}).get('email', '')
                    if a_e and isinstance(a_e, str):
                        payload_emails.add(a_e.strip().lower())
                    c_e = c.get('committer', {}).get('email', '')
                    if c_e and isinstance(c_e, str):
                        payload_emails.add(c_e.strip().lower())

            syncer_emails = get_syncer_emails()
            is_syncer_email = bool(payload_emails & syncer_emails)

            if is_syncer_email or is_copybara_commit:
                print(f"[IGNORE] Skipping webhook for {repo_name} triggered by syncer/Copybara commit.")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "ignored", "reason": "syncer_loop_prevention"}')
                return

            # Non-blocking lock check to prevent concurrent sync executions
            if not sync_lock.acquire(blocking=False):
                print(f"[IGNORE] Skipping webhook for {repo_name}: sync process already running.")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "ignored", "reason": "sync_in_progress"}')
                return

            print(f"[TRIGGER] Received webhook for repository: {repo_name}")
            
            # Respond immediately to Gitea to prevent timeout
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "sync_triggered"}')

            # Spawn sync execution in a background thread
            threading.Thread(target=execute_sync, daemon=True).start()

        except Exception as e:
            print(f"[ERROR] Webhook processing failed: {e}", file=sys.stderr)
            try:
                self.send_response(500)
                self.end_headers()
            except Exception:
                pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

def run():
    server_address = ('', PORT)
    httpd = http.server.HTTPServer(server_address, WebhookHandler)
    print(f"[*] Syncer trigger server running on port {PORT}...")
    httpd.serve_forever()

if __name__ == "__main__":
    run()
