import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from reporting import (
    MAX_HISTORY_ITEMS,
    AnalysisRecord,
    add_history_record,
    export_report,
    format_history,
)


class ReportingTests(unittest.TestCase):
    def make_record(self, question: str = "分析项目") -> AnalysisRecord:
        return AnalysisRecord(
            target_type="local",
            target_value="D:/GitHub/demo",
            question=question,
            answer="这是分析结果。",
            created_at=datetime(2026, 9, 18, 8, 30, tzinfo=timezone.utc),
        )

    def test_empty_history(self) -> None:
        self.assertIn("还没有", format_history([]))

    def test_history_keeps_latest_items(self) -> None:
        history: list[AnalysisRecord] = []

        for index in range(MAX_HISTORY_ITEMS + 3):
            add_history_record(history, self.make_record(f"问题 {index}"))

        self.assertEqual(MAX_HISTORY_ITEMS, len(history))
        self.assertEqual("问题 3", history[0].question)

    def test_history_truncates_long_question(self) -> None:
        result = format_history([self.make_record("x" * 200)])

        self.assertIn("...", result)
        self.assertLess(len(result), 180)

    def test_export_report_writes_markdown(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            report_path = export_report(
                self.make_record(),
                Path(temporary_directory),
            )
            content = report_path.read_text(encoding="utf-8")

        self.assertIn("# RepoPilot 分析报告", content)
        self.assertIn("D:/GitHub/demo", content)
        self.assertIn("这是分析结果", content)

    def test_export_report_does_not_overwrite_existing_file(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            reports_dir = Path(temporary_directory)
            first_path = export_report(self.make_record(), reports_dir)
            second_path = export_report(self.make_record(), reports_dir)

        self.assertNotEqual(first_path, second_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
