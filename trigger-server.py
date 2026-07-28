#!/usr/bin/env python3
import http.server
import json
import subprocess
import sys

PORT = 8000

class WebhookHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b""
        
        try:
            payload = json.loads(post_data.decode('utf-8')) if post_data else {}
            repo_name = payload.get('repository', {}).get('full_name', 'unknown')
            print(f"[TRIGGER] Received webhook for repository: {repo_name}")
            
            # Execute hybrid-syncer in sync mode
            res = subprocess.run(
                ["python3", "/app/hybrid-syncer.py", "sync", "-v"],
                capture_output=True,
                text=True
            )
            
            print(res.stdout)
            if res.returncode != 0:
                print(f"[ERROR] Sync failed:\n{res.stderr}", file=sys.stderr)
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "sync_triggered"}')

        except Exception as e:
            print(f"[ERROR] Webhook processing failed: {e}", file=sys.stderr)
            self.send_response(500)
            self.end_headers()

    def do_GET(self):
        # Health check endpoint
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

def run():
    server_address = ('', PORT)
    httpd = http.server.HTTPServer(server_address, WebhookHandler)
    print(f"[*] Syncer trigger server running on port {PORT}...")
    httpd.serve_forever()

if __name__ == "__main__":
    run()
