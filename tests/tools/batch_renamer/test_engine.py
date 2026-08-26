import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fuzztoolbox.tools.batch_renamer.engine import (
    RenameError,
    RenameRule,
    RuleKind,
    build_plan,
    execute_plan,
    transform_name,
    undo_receipt,
)


class BatchRenamerEngineTests(unittest.TestCase):
    def test_rule_chain_preserves_extension_and_order(self):
        rules = (
            RenameRule(RuleKind.REPLACE, "draft", "release"),
            RenameRule(RuleKind.PREFIX, "project_"),
            RenameRule(RuleKind.NUMBER, "7", "3"),
        )

        self.assertEqual(
            transform_name("draft.txt", rules, 2),
            "project_release_009.txt",
        )

    def test_plan_rejects_case_insensitive_duplicate_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.txt"
            second = root / "b.txt"
            first.touch()
            second.touch()
            rules = (RenameRule(RuleKind.REGEX, r".*", "same"),)

            plan = build_plan([first, second], rules)

            self.assertTrue(plan.errors)

    def test_two_phase_execution_supports_name_swaps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.txt"
            second = root / "b.txt"
            first.write_text("A", encoding="utf-8")
            second.write_text("B", encoding="utf-8")
            rules = (RenameRule(RuleKind.REGEX, r"([ab])", lambda_match()),)
            with patch(
                "fuzztoolbox.tools.batch_renamer.engine.re.sub",
                side_effect=lambda _p, _r, value: "b" if value == "a" else "a",
            ):
                plan = build_plan([first, second], rules)
            receipt = execute_plan(plan)

            self.assertEqual(first.read_text(encoding="utf-8"), "B")
            self.assertEqual(second.read_text(encoding="utf-8"), "A")

            undo_receipt(receipt)
            self.assertEqual(first.read_text(encoding="utf-8"), "A")
            self.assertEqual(second.read_text(encoding="utf-8"), "B")

    def test_execute_revalidates_external_target_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "old.txt"
            source.touch()
            plan = build_plan(
                [source],
                (RenameRule(RuleKind.REPLACE, "old", "new"),),
            )
            (root / "new.txt").touch()

            with self.assertRaises(RenameError):
                execute_plan(plan)

    def test_numbering_does_not_leave_gaps_for_excluded_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = [root / name for name in ("a.txt", "b.txt", "c.txt")]
            for source in sources:
                source.touch()

            plan = build_plan(
                sources,
                (RenameRule(RuleKind.NUMBER, "1", "2"),),
                selected={sources[0], sources[2]},
            )

            self.assertEqual(plan.items[0].target.name, "a_01.txt")
            self.assertEqual(plan.items[2].target.name, "c_02.txt")

    def test_second_phase_failure_restores_every_original_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.txt"
            second = root / "b.txt"
            first.write_text("A", encoding="utf-8")
            second.write_text("B", encoding="utf-8")
            plan = build_plan(
                [first, second],
                (RenameRule(RuleKind.PREFIX, "new_"),),
            )
            original_replace = Path.replace
            calls = 0

            def fail_during_second_phase(path, target):
                nonlocal calls
                calls += 1
                if calls == 4:
                    raise OSError("simulated failure")
                return original_replace(path, target)

            with patch.object(
                Path, "replace", new=fail_during_second_phase
            ), self.assertRaises(RenameError):
                execute_plan(plan)

            self.assertEqual(first.read_text(encoding="utf-8"), "A")
            self.assertEqual(second.read_text(encoding="utf-8"), "B")
            self.assertFalse((root / "new_a.txt").exists())


def lambda_match():
    return "unused"


if __name__ == "__main__":
    unittest.main()
