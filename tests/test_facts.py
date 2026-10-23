import unittest
from unittest.mock import patch
import json
import urllib.request
import io


class TestOrangutanFacts(unittest.TestCase):
    def test_post_facts_format(self):
        """Verify the payload structure sent to LAN-Orangutan /api/devices/{mac}/facts."""
        mac = "aa:bb:cc:dd:ee:ff"
        token = "test-token-12345"
        base_url = "http://10.0.0.1:291"
        payload = {
            "os": "Ubuntu",
            "os_version": "24.04.1 LTS",
            "os_family": "Linux",
        }

        req = urllib.request.Request(
            f"{base_url}/api/devices/{mac}/facts",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.full_url, "http://10.0.0.1:291/api/devices/aa:bb:cc:dd:ee:ff/facts")
        self.assertEqual(req.get_header("Authorization"), "Bearer test-token-12345")
        self.assertEqual(req.get_header("Content-type"), "application/json")
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["os"], "Ubuntu")
        self.assertEqual(body["os_version"], "24.04.1 LTS")
        self.assertEqual(body["os_family"], "Linux")


if __name__ == "__main__":
    unittest.main()
