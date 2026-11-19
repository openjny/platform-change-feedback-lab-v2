import json
import unittest
from pathlib import Path

from plan import validate


class PlanTests(unittest.TestCase):
    def setUp(self):
        profile = Path(__file__).resolve().parents[1] / "profiles" / "dev.json"
        self.plan = json.loads(profile.read_text(encoding="utf-8"))

    def test_reference_plan(self):
        profiles = Path(__file__).resolve().parents[1] / "profiles"
        for file in sorted(profiles.glob("*.json")):
            with self.subTest(profile=file.name):
                self.assertEqual(validate(json.loads(file.read_text(encoding="utf-8"))), [])

    def test_production_requires_redundancy(self):
        self.plan["environment"] = "prd"
        self.assertIn("replicas: production requires at least 2.", validate(self.plan))
        self.plan["replicas"] = 2
        self.assertEqual(validate(self.plan), [])

    def test_boolean_is_not_a_replica_count(self):
        self.plan["replicas"] = True
        self.assertIn("replicas: use an integer from 1 to 5.", validate(self.plan))
