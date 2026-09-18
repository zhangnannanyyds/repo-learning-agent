import os
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from main import (
    build_prompt,
    build_zhipu_model_settings,
    classify_project_target,
    extract_retry_wait,
)


class MainTests(unittest.TestCase):
    def test_extract_retry_wait(self) -> None:
        error = Exception("Please try again in 9h34m7.68s.")

        self.assertEqual("9h34m7.68s", extract_retry_wait(error))

    def test_extract_retry_wait_when_missing(self) -> None:
        error = Exception("rate limit reached")

        self.assertIsNone(extract_retry_wait(error))

    def test_classify_public_github_repo(self) -> None:
        target, error = classify_project_target(
            "https://github.com/openai/openai-python.git"
        )

        self.assertIsNone(error)
        self.assertEqual(
            ("github", "https://github.com/openai/openai-python"),
            target,
        )

    def test_classify_local_project(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            target, error = classify_project_target(temporary_directory)

            self.assertIsNone(error)
            self.assertEqual("local", target[0])
            self.assertEqual(
                str(Path(temporary_directory).resolve()),
                target[1],
            )

    def test_classify_rejects_missing_target(self) -> None:
        target, error = classify_project_target("Z:/missing-repopilot-project")

        self.assertIsNone(target)
        self.assertIn("路径不存在", error)

    def test_build_prompt_identifies_github_target(self) -> None:
        prompt = build_prompt(
            "github",
            "https://github.com/example/demo",
            "分析这个项目",
        )

        self.assertIn("公开 GitHub 仓库", prompt)
        self.assertIn("https://github.com/example/demo", prompt)

    def test_zhipu_glm45_disables_thinking_by_default(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("ZHIPU_THINKING", None)
            os.environ["ZHIPU_MODEL"] = "glm-4.5"
            settings = build_zhipu_model_settings()

        self.assertIsNotNone(settings)
        self.assertEqual(
            {"thinking": {"type": "disabled"}},
            settings.extra_body,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
