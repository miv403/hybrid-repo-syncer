#!/usr/bin/env python3
import http.server
import json
import subprocess
import sys
import threading

PORT = 8000
DEFAULT_SYNCER_EMAIL = "syncer@example.com"
SYNCER_EMAIL = DEFAULT_SYNCER_EMAIL
syncer_email = SYNCER_EMAIL

def execute_sync():
    print("[TRIGGER] Starting hybrid-syncer process in background...")
    res = subprocess.run(
        ["python3", "/app/hybrid-syncer.py", "-v", "sync"],
        capture_output=True,
        text=True
    )
    if res.stdout:
        print(res.stdout)
    if res.returncode != 0:
        print(f"[ERROR] Sync failed:\n{res.stderr}", file=sys.stderr)
    else:
        print("[TRIGGER] Hybrid sync completed successfully.")

class WebhookHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b""
        
        try:
            payload = json.loads(post_data.decode('utf-8')) if post_data else {}
            repo_name = payload.get('repository', {}).get('full_name', 'unknown')
            
            # Extract pusher, sender, author, committer, and message to prevent self-trigger loops
            pusher_email = payload.get('pusher', {}).get('email', '')
            sender_email = payload.get('sender', {}).get('email', '')
            head_commit_author = payload.get('head_commit', {}).get('author', {}).get('email', '')
            head_commit_committer = payload.get('head_commit', {}).get('committer', {}).get('email', '')
            head_commit_msg = payload.get('head_commit', {}).get('message', '')

            emails_to_check = {syncer_email, DEFAULT_SYNCER_EMAIL}

            # Check committer email across all pushed commits in the payload
            committers_in_payload = {
                c.get('committer', {}).get('email', '')
                for c in payload.get('commits', [])
                if isinstance(c, dict)
            }

            is_syncer_committer = (
                head_commit_committer in emails_to_check or
                bool(committers_in_payload & emails_to_check)
            )
            is_syncer_email = any(e and e in emails_to_check for e in (pusher_email, sender_email, head_commit_author))
            is_copybara_commit = "GitOrigin-RevId:" in head_commit_msg

            if is_syncer_committer or is_syncer_email or is_copybara_commit:
                print(f"[IGNORE] Skipping webhook for {repo_name} triggered by syncer/Copybara commit.")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "ignored", "reason": "syncer_loop_prevention"}')
                return

            print(f"[TRIGGER] Received webhook for repository: {repo_name}")
            
            # Respond immediately to Gitea to prevent timeout and BrokenPipeError
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
