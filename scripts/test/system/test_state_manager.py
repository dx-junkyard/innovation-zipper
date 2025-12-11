import unittest
import sys
from pathlib import Path
from copy import deepcopy

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[3]))

from app.api.state_manager import StateManager

class TestStateManager(unittest.TestCase):

    def test_deep_merge(self):
        default = {"a": 1, "b": {"c": 2, "d": 3}}
        updates = {"b": {"c": 4}, "e": 5}
        expected = {"a": 1, "b": {"c": 4, "d": 3}, "e": 5}

        result = StateManager.deep_merge(default, updates)
        self.assertEqual(result, expected)
        print("Verified: deep_merge works correctly.")

    def test_get_state_with_defaults(self):
        stored_state = {
            "resident_profile": {"basic": {"age": 30}},
            "service_needs": {"explicit_needs": {"goals": ["health"]}}
        }

        state = StateManager.get_state_with_defaults(stored_state)

        self.assertEqual(state["resident_profile"]["basic"]["age"], 30)
        self.assertIsNone(state["resident_profile"]["basic"]["gender"]) # Default
        self.assertEqual(state["service_needs"]["explicit_needs"]["goals"], ["health"])
        print("Verified: get_state_with_defaults merges with defaults.")

    def test_normalize_analysis_valid(self):
        analysis = {
            "resident_profile": {"basic": {"age": 25}},
            "service_needs": {"explicit_needs": {"goals": ["job"]}},
            "next_question": "How are you?"
        }

        normalized = StateManager.normalize_analysis(analysis)

        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["resident_profile"]["basic"]["age"], 25)
        self.assertIsNone(normalized["resident_profile"]["basic"]["gender"]) # Default
        self.assertEqual(normalized["next_question"], "How are you?")
        print("Verified: normalize_analysis handles valid input.")

    def test_normalize_analysis_invalid(self):
        analysis = {"foo": "bar"}
        normalized = StateManager.normalize_analysis(analysis)
        self.assertIsNone(normalized)
        print("Verified: normalize_analysis returns None for invalid input.")

if __name__ == "__main__":
    unittest.main()
