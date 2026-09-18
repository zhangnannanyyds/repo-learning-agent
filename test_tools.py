import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tools
from tools import (
    analyze_project,
    check_project_path_access,
    get_blocklist_status,
    get_github_repo_info,
    get_public_github_repo_info,
    get_run_candidates,
    list_github_repo_files,
    list_project_files,
    list_project_files_local,
    list_public_github_repo_files,
    parse_github_repo_url,
    read_github_repo_file,
    read_github_repo_file_compat,
    read_project_file,
    read_public_github_repo_file,
    search_project,
)


class ToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.policy_directory_patcher = patch(
            "tools.ACCESS_POLICY_DIR",
            self.root,
        )
        self.policy_directory_patcher.start()
        (self.root / "main.py").write_text(
            "from agents import Runner\n\nprint('demo')\n",
            encoding="utf-8",
        )
        (self.root / "requirements.txt").write_text(
            "openai-agents==0.22.2\n",
            encoding="utf-8",
        )
        (self.root / "README.md").write_text("# Demo\n", encoding="utf-8")
        (self.root / ".env").write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")
        hidden_directory = self.root / ".venv"
        hidden_directory.mkdir()
        (hidden_directory / "ignored.py").write_text("ignored\n", encoding="utf-8")
        uppercase_hidden_directory = self.root / "NODE_MODULES"
        uppercase_hidden_directory.mkdir()
        (uppercase_hidden_directory / "also-ignored.py").write_text(
            "ignored\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.policy_directory_patcher.stop()
        self.temporary_directory.cleanup()

    def test_analyze_python_project(self) -> None:
        result = analyze_project.__wrapped__(str(self.root))
        self.assertIn("项目类型：Python", result)
        self.assertIn("main.py", result)

    def test_parse_github_repo_url(self) -> None:
        self.assertEqual(
            parse_github_repo_url(
                "https://github.com/openai/openai-python"
            ),
            ("openai", "openai-python"),
        )

        self.assertEqual(
            parse_github_repo_url(
                "https://github.com/openai/openai-python.git"
            ),
            ("openai", "openai-python"),
        )

        self.assertIsNone(
            parse_github_repo_url("D:\\GitHub\\repo-learning-agent")
        )

        self.assertIsNone(
            parse_github_repo_url("https://github.com/openai")
        )

        self.assertIsNone(
            parse_github_repo_url(
                "https://github.com/openai/openai-python/blob/main/README.md"
            )
        )

    def test_get_public_github_repo_info(self) -> None:
        fake_payload = {
            "full_name": "openai/openai-python",
            "description": "OpenAI Python SDK",
            "default_branch": "main",
            "language": "Python",
            "updated_at": "2026-09-18T00:00:00Z",
            "html_url": "https://github.com/openai/openai-python",
        }

        with patch("tools.urlopen") as mock_urlopen:
            fake_response = mock_urlopen.return_value.__enter__.return_value
            fake_response.read.return_value = json.dumps(
                fake_payload
            ).encode("utf-8")

            result = get_public_github_repo_info(
                "https://github.com/openai/openai-python"
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["full_name"], "openai/openai-python")
        self.assertEqual(result["language"], "Python")

    def test_github_request_uses_optional_token(self) -> None:
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}):
            request = tools._github_request(
                "https://api.github.com/repos/example/demo",
                "application/vnd.github+json",
            )

        self.assertEqual("Bearer test-token", request.get_header("Authorization"))
        self.assertEqual("2022-11-28", request.get_header("X-github-api-version"))

    def test_get_github_repo_info_formats_result(self) -> None:
        fake_result = {
            "ok": True,
            "owner": "openai",
            "repo": "openai-python",
            "full_name": "openai/openai-python",
            "description": "OpenAI Python SDK",
            "default_branch": "main",
            "language": "Python",
            "updated_at": "2026-09-18T00:00:00Z",
            "html_url": "https://github.com/openai/openai-python",
        }

        with patch(
            "tools.get_public_github_repo_info",
            return_value=fake_result,
        ):
            result = get_github_repo_info.__wrapped__(
                "https://github.com/openai/openai-python"
            )

        self.assertIn("openai/openai-python", result)
        self.assertIn("外部数据", result)
        self.assertIn("主要语言：Python", result)

    def test_get_public_github_repo_info_rejects_invalid_url(self) -> None:
        with patch("tools.urlopen") as mock_urlopen:
            result = get_public_github_repo_info("D:\\GitHub\\demo")

        self.assertFalse(result["ok"])
        mock_urlopen.assert_not_called()

    def test_get_public_github_repo_info_handles_null_language(self) -> None:
        fake_payload = {
            "full_name": "example/docs",
            "description": None,
            "default_branch": "main",
            "language": None,
            "updated_at": "2026-09-18T00:00:00Z",
            "html_url": "https://github.com/example/docs",
        }

        with patch("tools.urlopen") as mock_urlopen:
            fake_response = mock_urlopen.return_value.__enter__.return_value
            fake_response.read.return_value = json.dumps(fake_payload).encode("utf-8")
            result = get_public_github_repo_info(
                "https://github.com/example/docs"
            )

        self.assertEqual("", result["description"])
        self.assertEqual("", result["language"])

    def test_list_public_github_repo_files_filters_sensitive_paths(self) -> None:
        fake_info = {
            "ok": True,
            "owner": "example",
            "repo": "demo",
            "default_branch": "main",
        }
        fake_tree = {
            "tree": [
                {"type": "blob", "path": "README.md"},
                {"type": "blob", "path": "src/main.py"},
                {"type": "blob", "path": ".env"},
                {"type": "blob", "path": "keys/server.pem"},
                {"type": "blob", "path": "node_modules/pkg/index.js"},
                {"type": "tree", "path": "src"},
            ],
            "truncated": False,
        }

        with patch(
            "tools.get_public_github_repo_info",
            return_value=fake_info,
        ), patch("tools._github_api_json", return_value=(fake_tree, None)):
            result = list_public_github_repo_files(
                "https://github.com/example/demo"
            )

        self.assertIn("README.md", result)
        self.assertIn("src/main.py", result)
        self.assertNotIn(".env", result)
        self.assertNotIn("server.pem", result)
        self.assertNotIn("node_modules", result)

    def test_list_github_repo_files_tool_uses_public_reader(self) -> None:
        with patch(
            "tools.list_public_github_repo_files",
            return_value="README.md\nsrc/main.py",
        ):
            result = list_github_repo_files.__wrapped__(
                "https://github.com/example/demo"
            )

        self.assertIn("README.md", result)

    def test_read_public_github_repo_file_returns_line_numbers(self) -> None:
        with patch(
            "tools._github_api_raw",
            return_value=(b"first line\nsecond line\n", None),
        ):
            result = read_public_github_repo_file(
                "https://github.com/example/demo",
                "README.md",
            )

        self.assertIn("GitHub 外部文件", result)
        self.assertIn("1: first line", result)
        self.assertIn("2: second line", result)

    def test_read_github_repo_file_tool_uses_public_reader(self) -> None:
        with patch(
            "tools.read_public_github_repo_file",
            return_value="1: demo",
        ):
            result = read_github_repo_file.__wrapped__(
                "https://github.com/example/demo",
                "README.md",
            )

        self.assertEqual("1: demo", result)

    def test_read_github_repo_file_compatibility_alias(self) -> None:
        with patch(
            "tools.read_public_github_repo_file",
            return_value="1: demo",
        ):
            result = read_github_repo_file_compat.__wrapped__(
                "https://github.com/example/demo",
                "README.md",
            )

        self.assertEqual("1: demo", result)
        self.assertEqual("read_github_repoFile", read_github_repo_file_compat.name)

    def test_read_public_github_repo_file_rejects_traversal(self) -> None:
        with patch("tools._github_api_raw") as mock_raw:
            result = read_public_github_repo_file(
                "https://github.com/example/demo",
                "../secret.txt",
            )

        self.assertIn("拒绝读取", result)
        mock_raw.assert_not_called()

    def test_read_public_github_repo_file_rejects_sensitive_file(self) -> None:
        with patch("tools._github_api_raw") as mock_raw:
            result = read_public_github_repo_file(
                "https://github.com/example/demo",
                ".env",
            )

        self.assertIn("敏感文件", result)
        mock_raw.assert_not_called()

    def test_remote_file_respects_central_blocklist(self) -> None:
        (self.root / ".repopilotignore").write_text(
            "private/\n",
            encoding="utf-8",
        )

        with patch("tools._github_api_raw") as mock_raw:
            result = read_public_github_repo_file(
                "https://github.com/example/demo",
                "private/profile.txt",
            )

        self.assertIn("黑名单", result)
        mock_raw.assert_not_called()

    def test_list_skips_sensitive_and_dependency_files(self) -> None:
        result = list_project_files.__wrapped__(str(self.root))
        self.assertIn("main.py", result)
        self.assertNotIn(".env", result)
        self.assertNotIn("ignored.py", result)
        self.assertNotIn("also-ignored.py", result)

    def test_read_file_returns_line_numbers(self) -> None:
        result = read_project_file.__wrapped__(str(self.root), "main.py")
        self.assertIn("1: from agents import Runner", result)
        self.assertIn("3: print('demo')", result)

    def test_read_refuses_path_traversal(self) -> None:
        result = read_project_file.__wrapped__(str(self.root), "../outside.txt")
        self.assertIn("拒绝读取", result)

    def test_read_refuses_sensitive_file(self) -> None:
        result = read_project_file.__wrapped__(str(self.root), ".env")
        self.assertIn("敏感文件", result)

    def test_common_credential_file_is_sensitive(self) -> None:
        (self.root / ".npmrc").write_text("token=secret\n", encoding="utf-8")

        files = list_project_files.__wrapped__(str(self.root))
        result = read_project_file.__wrapped__(str(self.root), ".npmrc")

        self.assertNotIn(".npmrc", files)
        self.assertIn("敏感文件", result)

    def test_search_returns_file_and_line(self) -> None:
        result = search_project.__wrapped__(str(self.root), "Runner")
        self.assertIn("main.py:1", result)

    def test_search_rejects_empty_keyword(self) -> None:
        result = search_project.__wrapped__(str(self.root), "   ")
        self.assertEqual("搜索关键词不能为空。", result)

    def test_search_rejects_excessive_keyword(self) -> None:
        result = search_project.__wrapped__(str(self.root), "x" * 201)

        self.assertIn("搜索关键词过长", result)

    def test_search_truncates_very_long_matching_line(self) -> None:
        long_file = self.root / "minified.js"
        long_file.write_text("needle" + "x" * 10_000, encoding="utf-8")

        result = search_project.__wrapped__(str(self.root), "needle")

        self.assertLess(len(result), 500)
        self.assertTrue(result.endswith("..."))

    def test_python_run_candidates(self) -> None:
        result = get_run_candidates.__wrapped__(str(self.root))
        self.assertIn("python -m pip install -r requirements.txt", result)
        self.assertIn("python main.py", result)
        self.assertIn("没有执行", result)

    def test_node_run_candidates(self) -> None:
        node_root = self.root / "node-demo"
        node_root.mkdir()
        package_data = {"scripts": {"dev": "vite", "test": "vitest"}}
        (node_root / "package.json").write_text(
            json.dumps(package_data),
            encoding="utf-8",
        )

        result = get_run_candidates.__wrapped__(str(node_root))
        self.assertIn("npm install", result)
        self.assertIn("npm run dev", result)
        self.assertIn("npm run test", result)

    def test_unusual_package_json_does_not_crash(self) -> None:
        node_root = self.root / "unusual-node-demo"
        node_root.mkdir()
        (node_root / "package.json").write_text("[]", encoding="utf-8")

        result = get_run_candidates.__wrapped__(str(node_root))
        self.assertIn("npm install", result)

    def test_blocklist_hides_and_refuses_private_files(self) -> None:
        private_directory = self.root / "private"
        private_directory.mkdir()
        (private_directory / "profile.txt").write_text(
            "身份证号码：example\n",
            encoding="utf-8",
        )
        (self.root / ".repopilotignore").write_text(
            "# 个人隐私目录\nprivate/\n",
            encoding="utf-8",
        )

        files = list_project_files.__wrapped__(str(self.root))
        read_result = read_project_file.__wrapped__(
            str(self.root),
            "private/profile.txt",
        )
        search_result = search_project.__wrapped__(str(self.root), "身份证号码")

        self.assertNotIn("profile.txt", files)
        self.assertIn("黑名单", read_result)
        self.assertIn("没有找到关键词", search_result)

    def test_files_are_allowed_by_default_without_blocklist_match(self) -> None:
        (self.root / ".repopilotignore").write_text(
            "private/\n",
            encoding="utf-8",
        )

        files = list_project_files.__wrapped__(str(self.root))
        read_result = read_project_file.__wrapped__(
            str(self.root),
            "requirements.txt",
        )

        self.assertIn("requirements.txt", files)
        self.assertIn("openai-agents", read_result)

    def test_policy_files_cannot_be_read_by_agent(self) -> None:
        (self.root / ".repopilotignore").write_text("private/\n", encoding="utf-8")

        result = read_project_file.__wrapped__(
            str(self.root),
            ".repopilotignore",
        )

        self.assertIn("访问控制配置文件", result)

    def test_central_blocklist_accepts_absolute_file_path(self) -> None:
        target_root = self.root / "external-project"
        target_root.mkdir()
        private_file = target_root / "random-name-123.txt"
        private_file.write_text("personal information\n", encoding="utf-8")
        absolute_rule = private_file.resolve().as_posix()
        (self.root / ".repopilotignore").write_text(
            f"{absolute_rule}\n",
            encoding="utf-8",
        )

        result = read_project_file.__wrapped__(
            str(target_root),
            private_file.name,
        )

        self.assertIn("黑名单", result)

    def test_central_blocklist_accepts_quoted_absolute_path(self) -> None:
        target_root = self.root / "quoted-project"
        target_root.mkdir()
        private_file = target_root / "private note.txt"
        private_file.write_text("personal information\n", encoding="utf-8")
        absolute_rule = private_file.resolve().as_posix()
        (self.root / ".repopilotignore").write_text(
            f'"{absolute_rule}"\n',
            encoding="utf-8",
        )

        result = read_project_file.__wrapped__(
            str(target_root),
            private_file.name,
        )

        self.assertIn("黑名单", result)

    def test_local_extension_filter_uses_blocklist_without_api(self) -> None:
        (self.root / "visible.txt").write_text("visible\n", encoding="utf-8")
        (self.root / "blocked.txt").write_text("blocked\n", encoding="utf-8")
        (self.root / ".repopilotignore").write_text(
            "blocked.txt\n",
            encoding="utf-8",
        )

        result = list_project_files_local(str(self.root), extension="txt")

        self.assertIn("visible.txt", result)
        self.assertNotIn("blocked.txt", result)
        self.assertNotIn("main.py", result)

    def test_local_access_check_does_not_read_content(self) -> None:
        private_file = self.root / "private.txt"
        private_file.write_text("do not expose this value\n", encoding="utf-8")
        (self.root / ".repopilotignore").write_text(
            "private.txt\n",
            encoding="utf-8",
        )

        result = check_project_path_access(str(self.root), "private.txt")

        self.assertIn("访问状态：拒绝", result)
        self.assertNotIn("do not expose this value", result)

    def test_blocklist_status_does_not_reveal_rules(self) -> None:
        secret_rule = "D:/private/location/secret.txt"
        (self.root / ".repopilotignore").write_text(
            f"{secret_rule}\n",
            encoding="utf-8",
        )

        result = get_blocklist_status()

        self.assertIn("当前有效规则数量：1", result)
        self.assertNotIn(secret_rule, result)

    def test_external_file_symlink_is_not_read(self) -> None:
        with tempfile.TemporaryDirectory() as outside_directory:
            outside_file = Path(outside_directory) / "outside.txt"
            outside_file.write_text("outside secret\n", encoding="utf-8")
            link_path = self.root / "linked.txt"

            try:
                os.symlink(outside_file, link_path)
            except OSError as error:
                self.skipTest(f"当前系统不允许创建符号链接：{error}")

            try:
                result = read_project_file.__wrapped__(str(self.root), "linked.txt")
                self.assertIn("项目目录之外", result)
            finally:
                link_path.unlink(missing_ok=True)

    def test_invalid_project_path(self) -> None:
        result = analyze_project.__wrapped__(str(self.root / "missing"))
        self.assertIn("项目路径不存在", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
