import re
import unittest
import uuid
from unittest.mock import patch

from fuzztoolbox.tools.uuid_generator.generator import (
    UUID7Generator,
    UUIDFormat,
    format_uuid,
    generate_uuids,
    resolve_namespace,
)


class UUIDGeneratorTests(unittest.TestCase):
    def test_v4_batch_is_unique_and_rfc_compliant(self):
        values = generate_uuids(4, 100)
        parsed = [uuid.UUID(value) for value in values]
        self.assertEqual(len(set(values)), 100)
        self.assertTrue(all(value.version == 4 for value in parsed))
        self.assertTrue(all(value.variant == uuid.RFC_4122 for value in parsed))

    def test_time_based_batches_are_unique(self):
        for version in (1, 7):
            values = generate_uuids(version, 100)
            self.assertEqual(len(set(values)), 100)
            self.assertTrue(all(uuid.UUID(value).version == version for value in values))

    def test_named_versions_are_deterministic(self):
        for version in (3, 5):
            first = generate_uuids(version, 1, namespace="dns", name="example.com")
            second = generate_uuids(version, 1, namespace="dns", name="example.com")
            self.assertEqual(first, second)
            self.assertEqual(uuid.UUID(first[0]).version, version)

    def test_named_version_batches_repeat_the_standard_deterministic_value(self):
        for version in (3, 5):
            values = generate_uuids(version, 20, namespace="dns", name="device")
            self.assertEqual(len(set(values)), 1)
            self.assertEqual(
                values[0], generate_uuids(version, 1, namespace="dns", name="device")[0]
            )
            self.assertTrue(all(uuid.UUID(value).version == version for value in values))

    def test_custom_namespace_is_supported(self):
        custom = "12345678-1234-5678-9234-567812345678"
        self.assertEqual(resolve_namespace(custom), uuid.UUID(custom))

    def test_v7_is_monotonic_within_same_millisecond(self):
        generator = UUID7Generator()
        with patch("fuzztoolbox.tools.uuid_generator.generator.secrets.randbits", return_value=10):
            values = [generator.generate(1_700_000_000_000) for _ in range(20)]
        self.assertEqual(values, sorted(values))
        self.assertEqual(len(set(values)), 20)
        self.assertTrue(all(value.version == 7 for value in values))
        self.assertTrue(all(value.variant == uuid.RFC_4122 for value in values))
        self.assertTrue(all((value.int >> 80) == 1_700_000_000_000 for value in values))

    def test_v7_handles_clock_rollback_without_reordering(self):
        generator = UUID7Generator()
        with patch("fuzztoolbox.tools.uuid_generator.generator.secrets.randbits", return_value=50):
            first = generator.generate(2_000)
            second = generator.generate(1_000)
        self.assertLess(first, second)
        self.assertEqual(second.int >> 80, 2_000)

    def test_output_format_options(self):
        value = uuid.UUID("12345678-1234-4678-9234-567812345678")
        rendered = format_uuid(
            value, UUIDFormat(uppercase=True, hyphens=False, braces=True)
        )
        self.assertEqual(rendered, "{12345678123446789234567812345678}")
        self.assertRegex(rendered, re.compile(r"^\{[0-9A-F]{32}\}$"))

    def test_invalid_generation_parameters_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "名称"):
            generate_uuids(5, namespace="dns", name="")
        with self.assertRaisesRegex(ValueError, "命名空间"):
            generate_uuids(3, namespace="invalid", name="value")
        with self.assertRaisesRegex(ValueError, "数量"):
            generate_uuids(4, 0)


if __name__ == "__main__":
    unittest.main()
