import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.status import classify_host_status, format_status_table


class TestStatusClassification(unittest.TestCase):
    def test_enrolled_host_probe(self):
        line = 'pve1 | CHANGED | rc=0 | (stdout) CA_ENROLLED'
        status, badge, detail = classify_host_status(line, is_managed=True)
        self.assertEqual(status, "ENROLLED")
        self.assertEqual(badge, "●")
        self.assertIn("CA Trust Active", detail)

    def test_key_only_host(self):
        line = 'distrubted | CHANGED | rc=0 | (stdout) KEY_ONLY'
        status, badge, detail = classify_host_status(line, is_managed=True)
        self.assertEqual(status, "KEY_ONLY")
        self.assertEqual(badge, "◐")
        self.assertIn("PKI not installed", detail)

    def test_no_sudo_host(self):
        line = 'server02 | CHANGED | rc=0 | (stdout) NO_SUDO'
        status, badge, detail = classify_host_status(line, is_managed=True)
        self.assertEqual(status, "NO_SUDO")
        self.assertEqual(badge, "▲")
        self.assertIn("passwordless sudo", detail)

    def test_enrolled_host_legacy_ping(self):
        line = 'pve1 | SUCCESS => {"changed": false, "ping": "pong"}'
        status, badge, detail = classify_host_status(line, is_managed=True)
        self.assertEqual(status, "ENROLLED")
        self.assertIn("Verified", detail)

    def test_paused_host(self):
        # Enrolled via SSH but toggled OFF in Orangutan
        line = 'truenas | SUCCESS => {"changed": false, "ping": "pong"}'
        status, badge, detail = classify_host_status(line, is_managed=False)
        self.assertEqual(status, "PAUSED")
        self.assertIn("toggled OFF", detail)

    def test_auth_error_key_only(self):
        line = "truenas | UNREACHABLE!: Task failed: Failed to connect to the host via ssh: ansible@10.0.0.15: Permission denied (publickey)."
        status, badge, detail = classify_host_status(line, is_managed=True)
        self.assertEqual(status, "AUTH_ERROR")
        self.assertIn("Password auth disabled", detail)

    def test_auth_error_password_prompt(self):
        line = "server01 | UNREACHABLE!: Task failed: Failed to connect to the host via ssh: ansible@10.0.0.20: Permission denied (publickey,password)."
        status, badge, detail = classify_host_status(line, is_managed=True)
        self.assertEqual(status, "AUTH_ERROR")
        self.assertIn("Password invalid or missing", detail)

    def test_offline_host(self):
        line = "switch01 | UNREACHABLE!: Task failed: Failed to connect to the host via ssh: connect to address 10.0.0.2 port 22: Connection refused"
        status, badge, detail = classify_host_status(line, is_managed=True)
        self.assertEqual(status, "OFFLINE")
        self.assertIn("Port 22 closed", detail)

    def test_timeout_host(self):
        line = "camera01 | UNREACHABLE!: Task failed: Failed to connect to the host via ssh: connect to address 10.0.0.50 port 22: Operation timed out"
        status, badge, detail = classify_host_status(line, is_managed=True)
        self.assertEqual(status, "OFFLINE")
        self.assertIn("timed out", detail)


if __name__ == "__main__":
    unittest.main()
