import unittest
from unittest.mock import patch
import sys
import os

# Add parent directory to path so inventory can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from inventory.orangutan import build_inventory


class TestInventoryIPMapping(unittest.TestCase):
    @patch("inventory.orangutan.get_openbao_secrets")
    @patch("inventory.orangutan.fetch_orangutan_devices")
    def test_ip_group_mapping_for_managed_devices(self, mock_fetch, mock_secrets):
        mock_secrets.return_value = {}
        mock_fetch.return_value = {
            "10.0.0.82": {
                "ansible_managed": True,
                "hostname": "truenas.int.spoutin.org",
                "vendor": "Debian",
            },
            "10.0.0.99": {
                "ansible_managed": True,
                "vendor": "Ubuntu",
            },
        }

        inv = build_inventory(only_managed=True)

        # Host 10.0.0.82 should have an IP group named '10.0.0.82'
        self.assertIn("10.0.0.82", inv)
        self.assertIn("truenas.int.spoutin.org", inv["10.0.0.82"]["hosts"])

        # Host 10.0.0.99 with no hostname should be named '10.0.0.99' directly
        self.assertIn("10.0.0.99", inv)
        self.assertEqual(inv["10.0.0.99"]["hosts"], ["10.0.0.99"])
        self.assertIn("10.0.0.99", inv["_meta"]["hostvars"])
        self.assertEqual(inv["_meta"]["hostvars"]["10.0.0.99"]["ansible_host"], "10.0.0.99")

        # OS groups should also contain the host names
        self.assertIn("truenas.int.spoutin.org", inv["debian"]["hosts"])
        self.assertIn("10.0.0.99", inv["ubuntu"]["hosts"])
        self.assertIn("managed_hosts", inv["all"]["children"])
        self.assertIn("10.0.0.82", inv["all"]["children"])
        self.assertIn("10.0.0.99", inv["all"]["children"])


if __name__ == "__main__":
    unittest.main()
