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

    @patch("inventory.orangutan.get_openbao_secrets")
    @patch("inventory.orangutan.fetch_orangutan_devices")
    def test_inventory_populates_orangutan_token(self, mock_fetch, mock_secrets):
        """Verify build_inventory includes orangutan_url and orangutan_api_token in all.vars and hostvars."""
        from inventory.orangutan import build_inventory
        mock_secrets.return_value = {
            "orangutan_url": "http://10.0.0.1:291",
            "orangutan_api_token": "secret-token-xyz",
        }
        mock_fetch.return_value = {
            "10.0.0.50": {
                "ansible_managed": True,
                "hostname": "host1",
                "mac": "aa:bb:cc:dd:ee:01",
            }
        }

        inv = build_inventory(only_managed=True)
        self.assertEqual(inv["all"]["vars"]["orangutan_api_token"], "secret-token-xyz")
        self.assertEqual(inv["_meta"]["hostvars"]["host1"]["orangutan_api_token"], "secret-token-xyz")
        self.assertEqual(inv["_meta"]["hostvars"]["host1"]["orangutan_mac"], "aa:bb:cc:dd:ee:01")


if __name__ == "__main__":
    unittest.main()
