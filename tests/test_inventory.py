import unittest
from unittest.mock import patch
import sys
import os

# Add parent directory to path so inventory can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from inventory.orangutan import (
    build_inventory,
    find_devices_by_target,
    get_completion_targets,
)


class TestInventoryIPMapping(unittest.TestCase):
    @patch("inventory.orangutan.get_openbao_secrets")
    @patch("inventory.orangutan.fetch_orangutan_devices")
    def test_duplicate_hostname_handling(self, mock_fetch, mock_secrets):
        mock_secrets.return_value = {}
        mock_fetch.return_value = {
            "10.0.0.82": {
                "ansible_managed": True,
                "hostname": "truenas",
                "vendor": "Debian",
            },
            "192.168.1.50": {
                "ansible_managed": True,
                "hostname": "truenas",
                "vendor": "FreeBSD",
            },
        }

        inv = build_inventory(only_managed=True)

        # Base name 'truenas' should be a group containing both disambiguated hosts
        self.assertIn("truenas", inv)
        self.assertIn("truenas-10-0-0-82", inv["truenas"]["hosts"])
        self.assertIn("truenas-192-168-1-50", inv["truenas"]["hosts"])

        # Each hostvars entry should map to the correct IP
        self.assertEqual(inv["_meta"]["hostvars"]["truenas-10-0-0-82"]["ansible_host"], "10.0.0.82")
        self.assertEqual(inv["_meta"]["hostvars"]["truenas-192-168-1-50"]["ansible_host"], "192.168.1.50")

        # IP groups should map directly
        self.assertEqual(inv["10.0.0.82"]["hosts"], ["truenas-10-0-0-82"])
        self.assertEqual(inv["192.168.1.50"]["hosts"], ["truenas-192-168-1-50"])

    @patch("inventory.orangutan.get_openbao_secrets")
    @patch("inventory.orangutan.fetch_orangutan_devices")
    def test_find_devices_by_target(self, mock_fetch, mock_secrets):
        mock_secrets.return_value = {}
        mock_fetch.return_value = {
            "10.0.0.82": {
                "ansible_managed": True,
                "hostname": "truenas",
                "vendor": "Debian",
            },
            "192.168.1.50": {
                "ansible_managed": True,
                "hostname": "truenas",
                "vendor": "FreeBSD",
            },
            "10.0.0.99": {
                "ansible_managed": True,
                "hostname": "docker01",
                "vendor": "Ubuntu",
            },
        }

        matches = find_devices_by_target("truenas")
        self.assertEqual(len(matches), 2)
        ips = [m["ip"] for m in matches]
        self.assertIn("10.0.0.82", ips)
        self.assertIn("192.168.1.50", ips)

        # Single match by IP
        matches_ip = find_devices_by_target("10.0.0.82")
        self.assertEqual(len(matches_ip), 1)
        self.assertEqual(matches_ip[0]["ip"], "10.0.0.82")

        # Zero matches
        self.assertEqual(len(find_devices_by_target("nonexistent")), 0)

    @patch("inventory.orangutan.get_openbao_secrets")
    @patch("inventory.orangutan.fetch_orangutan_devices")
    def test_get_completion_targets(self, mock_fetch, mock_secrets):
        mock_secrets.return_value = {}
        mock_fetch.return_value = {
            "10.0.0.82": {
                "ansible_managed": True,
                "hostname": "truenas.int.spoutin.org",
                "vendor": "Debian",
            },
        }

        # Clear cache file if present
        if os.path.exists("/tmp/.fleet_targets_cache"):
            os.remove("/tmp/.fleet_targets_cache")

        targets = get_completion_targets()
        self.assertIn("hypervisors", targets)
        self.assertIn("managed_hosts", targets)
        self.assertIn("debian", targets)
        self.assertIn("truenas.int.spoutin.org", targets)
        self.assertIn("10.0.0.82", targets)

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
