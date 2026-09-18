from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


MAX_HISTORY_ITEMS = 20
MAX_HISTORY_QUESTION_CHARS = 100
REPORTS_DIR = Path(__file__).resolve().parent / "reports"


@dataclass(frozen=True)
class AnalysisRecord:
    target_type: str
    target_value: str
    question: str
    answer: str
    created_at: datetime


def add_history_record(
    history: list[AnalysisRecord],
    record: AnalysisRecord,
) -> None:
    history.append(record)

    if len(history) > MAX_HISTORY_ITEMS:
        del history[:-MAX_HISTORY_ITEMS]


def format_history(history: list[AnalysisRecord]) -> str:
    if not history:
        return "当前运行期间还没有成功的分析记录。"

    lines = ["当前运行期间的分析记录："]

    for index, record in enumerate(history, start=1):
        question = " ".join(record.question.split())

        if len(question) > MAX_HISTORY_QUESTION_CHARS:
            question = question[:MAX_HISTORY_QUESTION_CHARS] + "..."

        created_at = record.created_at.astimezone().strftime("%H:%M:%S")
        lines.append(f"{index}. [{created_at}] {question}")

    return "\n".join(lines)


def export_report(
    record: AnalysisRecord,
    reports_dir: Path = REPORTS_DIR,
) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = record.created_at.astimezone().strftime("%Y%m%d-%H%M%S")
    report_path = reports_dir / f"repopilot-report-{timestamp}.md"
    suffix = 2

    while report_path.exists():
        report_path = reports_dir / f"repopilot-report-{timestamp}-{suffix}.md"
        suffix += 1

    target_label = "本地项目" if record.target_type == "local" else "GitHub 仓库"
    created_at = record.created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    content = (
        "# RepoPilot 分析报告\n\n"
        f"- 生成时间：{created_at}\n"
        f"- 目标类型：{target_label}\n"
        f"- 分析目标：{record.target_value}\n\n"
        "## 用户问题\n\n"
        f"{record.question}\n\n"
        "## 分析结果\n\n"
        f"{record.answer}\n"
    )
    report_path.write_text(content, encoding="utf-8")
    return report_path
