#!/usr/bin/env python3
import http.server
import json
import subprocess
import sys
import threading

PORT = 8000
SYNCER_EMAIL = "syncer@example.com"

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
            
            # Extract pusher, sender, and head commit author emails to prevent self-trigger loops
            pusher_email = payload.get('pusher', {}).get('email', '')
            sender_email = payload.get('sender', {}).get('email', '')
            head_commit_email = payload.get('head_commit', {}).get('author', {}).get('email', '')

            if SYNCER_EMAIL in (pusher_email, sender_email, head_commit_email):
                print(f"[IGNORE] Skipping webhook for {repo_name} triggered by syncer ({SYNCER_EMAIL}).")
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
