import unittest
from unittest.mock import patch

from fuzztoolbox.tools.random_port.generator import (
    MAX_PORT,
    MIN_PORT,
    PORT_COUNT,
    generate_random_port,
)


class RandomPortGeneratorTests(unittest.TestCase):
    def test_generated_ports_stay_in_non_privileged_range(self):
        for _ in range(1000):
            self.assertLessEqual(MIN_PORT, generate_random_port())
            self.assertLessEqual(generate_random_port(), MAX_PORT)

    def test_range_includes_both_boundaries(self):
        with patch(
            "fuzztoolbox.tools.random_port.generator.secrets.randbelow",
            side_effect=(0, PORT_COUNT - 1),
        ):
            self.assertEqual(generate_random_port(), MIN_PORT)
            self.assertEqual(generate_random_port(), MAX_PORT)

    def test_refresh_avoids_immediately_repeating_previous_port(self):
        with patch(
            "fuzztoolbox.tools.random_port.generator.secrets.randbelow",
            side_effect=(0, 1),
        ):
            self.assertEqual(generate_random_port(MIN_PORT), MIN_PORT + 1)


if __name__ == "__main__":
    unittest.main()
