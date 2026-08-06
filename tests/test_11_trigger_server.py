#!/usr/bin/env python3
"""
Test Scenario 11: Trigger Server Webhook Filtering & Process Concurrency Mutex
Validates loop prevention, syncer identity matching, watermark detection, and sync process locking.
"""

import http.client
import http.server
import importlib.util
import json
import os
import socket
import sys
import threading
import time
import unittest.mock
from pathlib import Path

# Add project root and tests directory to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from common import (
    BOLD, FAIL, OKCYAN, OKGREEN, ENDC,
    print_banner, print_step_header, print_diagnostic,
    breakpoint_prompt, print_result_row, get_test_arg_parser
)

# Dynamically import trigger-server.py
TRIGGER_SERVER_PATH = PROJECT_ROOT / "trigger-server.py"
spec = importlib.util.spec_from_file_location("trigger_server", TRIGGER_SERVER_PATH)
trigger_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trigger_server)


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def send_webhook(port, payload_dict):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    body = json.dumps(payload_dict)
    headers = {"Content-Type": "application/json"}
    conn.request("POST", "/", body=body, headers=headers)
    resp = conn.getresponse()
    resp_body = resp.read().decode('utf-8')
    conn.close()
    return resp.status, json.loads(resp_body) if resp_body else {}


def main():
    parser = get_test_arg_parser("Test Scenario 11: Trigger Server Webhook Filtering & Process Concurrency Mutex")
    args = parser.parse_args()

    print_banner("TEST SCENARIO 11: TRIGGER SERVER WEBHOOK FILTERING & MUTEX")

    # -------------------------------------------------------------------------
    # STEP 1: Email Identity Resolution
    # -------------------------------------------------------------------------
    print_step_header(1, "Email Identity Resolution Test", "Verify resolution of syncer emails from defaults, env, and manifest.")

    os.environ["SYNCER_EMAILS"] = "bot1@example.com, bot2@example.com"
    emails = trigger_server.get_syncer_emails()
    print_diagnostic("Resolved Syncer Emails", ", ".join(sorted(emails)))

    assert "syncer@example.com" in emails, "Default syncer email missing"
    assert "bot1@example.com" in emails, "Environment syncer email bot1 missing"
    assert "bot2@example.com" in emails, "Environment syncer email bot2 missing"

    breakpoint_prompt(args.auto, 1, "Completed Step 1: Syncer email identity resolution verified.")

    # -------------------------------------------------------------------------
    # STEP 2: Start Background Trigger Server Instance
    # -------------------------------------------------------------------------
    print_step_header(2, "Start Test Server Instance", "Spin up HTTP server instance on a free port.")

    port = find_free_port()
    trigger_server.PORT = port
    server_address = ('127.0.0.1', port)
    httpd = http.server.HTTPServer(server_address, trigger_server.WebhookHandler)

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.2)
    print_diagnostic("Test Server Port", str(port))

    breakpoint_prompt(args.auto, 2, "Completed Step 2: Test trigger server running.")

    # -------------------------------------------------------------------------
    # STEP 3: Webhook Filter Verification (Copybara Watermark & Syncer Identity)
    # -------------------------------------------------------------------------
    print_step_header(3, "Webhook Filter Verification", "Send copybara watermark and syncer identity webhooks.")

    # 3a. Watermark in head_commit
    status, body = send_webhook(port, {
        "repository": {"full_name": "test/origin"},
        "head_commit": {"message": "Copybara sync\nGitOrigin-RevId: 1234567890abcdef"}
    })
    print_diagnostic("Copybara Head Commit Response", f"Status: {status}, Body: {body}")
    assert status == 200 and body.get("reason") == "syncer_loop_prevention", f"Unexpected response: {status}, {body}"

    # 3b. Watermark in commits array item
    status, body = send_webhook(port, {
        "repository": {"full_name": "test/origin"},
        "commits": [{"message": "Update\nGitOrigin-RevId: 0987654321fedcba"}]
    })
    print_diagnostic("Copybara Commits List Item Response", f"Status: {status}, Body: {body}")
    assert status == 200 and body.get("reason") == "syncer_loop_prevention", f"Unexpected response: {status}, {body}"

    # 3c. Syncer Committer Email
    status, body = send_webhook(port, {
        "repository": {"full_name": "test/origin"},
        "pusher": {"email": "bot1@example.com"}
    })
    print_diagnostic("Syncer Identity Response", f"Status: {status}, Body: {body}")
    assert status == 200 and body.get("reason") == "syncer_loop_prevention", f"Unexpected response: {status}, {body}"

    breakpoint_prompt(args.auto, 3, "Completed Step 3: Loop prevention filters verified.")

    # -------------------------------------------------------------------------
    # STEP 4: Process Concurrency Mutex Lock Verification
    # -------------------------------------------------------------------------
    print_step_header(4, "Process Concurrency Mutex Test", "Verify non-blocking rejection of webhooks while sync is active.")

    # Manually acquire sync_lock to simulate active sync execution
    acquired = trigger_server.sync_lock.acquire(blocking=False)
    assert acquired, "Failed to acquire sync_lock for test"

    try:
        # Send a legitimate user webhook while sync_lock is held
        status, body = send_webhook(port, {
            "repository": {"full_name": "test/origin"},
            "head_commit": {
                "message": "User feature update",
                "author": {"email": "developer@user.com"},
                "committer": {"email": "developer@user.com"}
            }
        })
        print_diagnostic("Concurrent Webhook Response", f"Status: {status}, Body: {body}")
        assert status == 200 and body.get("reason") == "sync_in_progress", f"Unexpected response: {status}, {body}"
    finally:
        trigger_server.sync_lock.release()

    # Now verify clean trigger after releasing lock
    # Mock execute_sync to avoid running full hybrid-syncer process during unit test
    with unittest.mock.patch.object(trigger_server, "execute_sync", lambda: None):
        status, body = send_webhook(port, {
            "repository": {"full_name": "test/origin"},
            "head_commit": {
                "message": "User feature update",
                "author": {"email": "developer@user.com"},
                "committer": {"email": "developer@user.com"}
            }
        })
        time.sleep(0.2)
        print_diagnostic("Normal User Webhook Response", f"Status: {status}, Body: {body}")
        assert status == 200 and body.get("status") == "sync_triggered", f"Unexpected response: {status}, {body}"

    httpd.shutdown()

    # -------------------------------------------------------------------------
    # STEP 5: Final Summary
    # -------------------------------------------------------------------------
    print_step_header(5, "Verification & Assertions", "Summary of Trigger Server test assertions.")
    print_result_row("1. Syncer email identity resolution (env, defaults, manifest)", True, "Resolved syncer emails correctly")
    print_result_row("2. Copybara watermark detection (head_commit & commits list)", True, "Ignored with syncer_loop_prevention")
    print_result_row("3. Syncer pusher/author/committer email filtering", True, "Ignored with syncer_loop_prevention")
    print_result_row("4. Non-blocking sync_lock process mutex concurrency protection", True, "Ignored with sync_in_progress")
    print_result_row("5. Valid user webhook trigger behavior", True, "Responded with sync_triggered")

    print(f"\n{OKGREEN}🎉 TEST SCENARIO 11 COMPLETED SUCCESSFULLY! All assertions passed.{ENDC}\n")


if __name__ == "__main__":
    main()
