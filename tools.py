import json
import os
from fnmatch import fnmatch
from pathlib import Path

from agents.decorators import tool


MAX_LISTED_FILES = 120
MAX_FILE_CHARS = 8_000
MAX_SEARCH_RESULTS = 40
MAX_SEARCH_FILE_BYTES = 1_000_000
MAX_SEARCH_KEYWORD_CHARS = 200
MAX_MATCH_LINE_CHARS = 300
MAX_CONFIG_CHARS = 64_000
MAX_PACKAGE_FILE_CHARS = 200_000
MAX_NPM_SCRIPTS = 20

SKIP_DIRS = {
    ".aws",
    ".azure",
    ".git",
    ".gnupg",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ssh",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "venv",
}

TEXT_EXTENSIONS = {
    ".css",
    ".ets",
    ".html",
    ".java",
    ".js",
    ".json",
    ".json5",
    ".kt",
    ".md",
    ".py",
    ".sql",
    ".toml",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

SENSITIVE_NAMES = {
    ".git-credentials",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
    "service-account.json",
    "service_account.json",
    "token.json",
}

SENSITIVE_EXTENSIONS = {
    ".key",
    ".keystore",
    ".jks",
    ".p12",
    ".pem",
    ".pfx",
}

BLOCKLIST_FILE = ".repopilotignore"
POLICY_FILES = {BLOCKLIST_FILE}
ACCESS_POLICY_DIR = Path(__file__).resolve().parent


def _get_project_root(project_path: str) -> tuple[Path | None, str | None]:
    root = Path(project_path).expanduser()

    if not root.exists():
        return None, f"项目路径不存在：{project_path}"

    if not root.is_dir():
        return None, f"这个路径不是目录：{project_path}"

    return root.resolve(), None


def _is_sensitive_file(file_path: Path) -> bool:
    name = file_path.name.lower()

    if name == ".env" or name.startswith(".env."):
        return True

    return name in SENSITIVE_NAMES or file_path.suffix.lower() in SENSITIVE_EXTENSIONS


def _is_text_file(file_path: Path) -> bool:
    return file_path.suffix.lower() in TEXT_EXTENSIONS


def _read_patterns(file_path: Path) -> tuple[list[str], str | None]:
    try:
        with file_path.open(encoding="utf-8", errors="replace") as file:
            content = file.read(MAX_CONFIG_CHARS + 1)
    except OSError as error:
        return [], f"无法读取访问规则 {file_path.name}：{error}"

    if len(content) > MAX_CONFIG_CHARS:
        return [], f"访问规则 {file_path.name} 过大，最多允许 {MAX_CONFIG_CHARS} 个字符。"

    patterns: list[str] = []

    for raw_line in content.splitlines():
        pattern = raw_line.strip().replace("\\", "/")

        if not pattern or pattern.startswith("#"):
            continue

        if (
            len(pattern) >= 2
            and pattern[0] == pattern[-1]
            and pattern[0] in {'"', "'"}
        ):
            pattern = pattern[1:-1].strip()

        while pattern.startswith("./"):
            pattern = pattern[2:]

        if pattern:
            patterns.append(pattern)

    return patterns, None


def _load_access_policy() -> tuple[list[str], str | None]:
    blocklist_path = ACCESS_POLICY_DIR / BLOCKLIST_FILE
    block_patterns: list[str] = []

    if blocklist_path.is_file():
        block_patterns, error = _read_patterns(blocklist_path)

        if error:
            return [], error

    return block_patterns, None


def _matches_path_text(path_text: str, pattern: str) -> bool:
    if pattern.endswith("/"):
        directory = pattern.rstrip("/")
        normalized_path = os.path.normcase(path_text)
        normalized_directory = os.path.normcase(directory)
        return (
            normalized_path == normalized_directory
            or normalized_path.startswith(f"{normalized_directory}{os.sep}")
            or normalized_path.startswith(f"{normalized_directory}/")
        )

    return fnmatch(path_text, pattern)


def _matches_pattern(root: Path, file_path: Path, pattern: str) -> bool:
    if Path(pattern).is_absolute():
        return _matches_path_text(file_path.resolve().as_posix(), pattern)

    relative_path = file_path.relative_to(root)
    path_text = relative_path.as_posix()

    if pattern.endswith("/"):
        return _matches_path_text(path_text, pattern)

    if "/" not in pattern:
        return any(fnmatch(part, pattern) for part in relative_path.parts)

    return _matches_path_text(path_text, pattern)


def _check_file_access(
    root: Path,
    file_path: Path,
    policy: tuple[list[str], str | None],
) -> tuple[bool, str | None]:
    block_patterns, policy_error = policy

    if policy_error:
        return False, policy_error

    if file_path.name.lower() in POLICY_FILES:
        return False, "访问控制配置文件不会提供给 Agent。"

    if _is_sensitive_file(file_path):
        return False, "该文件属于内置敏感文件类型。"

    try:
        file_path.resolve().relative_to(root)
        relative_path = file_path.relative_to(root)
    except (OSError, ValueError):
        return False, "该文件不在项目目录中。"

    if any(
        _matches_pattern(root, file_path, pattern)
        for pattern in block_patterns
    ):
        return False, f"文件被 {BLOCKLIST_FILE} 黑名单阻止。"

    return True, None


def _walk_project_files(
    root: Path,
    policy: tuple[list[str], str | None],
):
    for current_path, directories, filenames in os.walk(root):
        visible_directories: list[str] = []

        for directory in sorted(directories):
            if directory.lower() in SKIP_DIRS:
                continue

            directory_path = Path(current_path) / directory
            allowed, _ = _check_file_access(root, directory_path, policy)

            if allowed:
                visible_directories.append(directory)

        directories[:] = visible_directories

        for filename in sorted(filenames):
            yield Path(current_path) / filename


def _resolves_inside_root(root: Path, file_path: Path) -> bool:
    try:
        file_path.resolve().relative_to(root)
        return True
    except (OSError, ValueError):
        return False


@tool
def list_project_files(project_path: str) -> str:
    """扫描本地项目并返回文件列表。只读，忽略依赖、缓存和敏感文件。"""
    return list_project_files_local(project_path)


def list_project_files_local(
    project_path: str,
    extension: str | None = None,
) -> str:
    """本地列出项目文件，可按扩展名筛选，不调用 OpenAI API。"""
    root, error = _get_project_root(project_path)

    if error:
        return error

    files: list[str] = []
    truncated = False
    policy = _load_access_policy()

    if policy[1]:
        return policy[1]

    normalized_extension: str | None = None

    if extension:
        normalized_extension = extension.strip().lower()

        if normalized_extension.startswith("*"):
            normalized_extension = normalized_extension[1:]

        if not normalized_extension.startswith("."):
            normalized_extension = f".{normalized_extension}"

    for file_path in _walk_project_files(root, policy):
        allowed, _ = _check_file_access(root, file_path, policy)

        if not allowed:
            continue

        if (
            normalized_extension
            and file_path.suffix.lower() != normalized_extension
        ):
            continue

        files.append(str(file_path.relative_to(root)))

        if len(files) >= MAX_LISTED_FILES:
            truncated = True
            break

    if not files:
        return "项目目录中没有找到可显示的文件。"

    result = "\n".join(files)

    if truncated:
        result += f"\n\n文件数量较多，只显示前 {MAX_LISTED_FILES} 个文件。"

    return result


@tool
def read_project_file(project_path: str, relative_path: str) -> str:
    """读取项目中的一个文本文件并返回带行号的内容。拒绝越界和敏感文件。"""
    root, error = _get_project_root(project_path)

    if error:
        return error

    requested_path = Path(relative_path)

    if requested_path.is_absolute():
        return "请提供相对于项目根目录的文件路径。"

    file_path = (root / requested_path).resolve()

    try:
        file_path.relative_to(root)
    except ValueError:
        return "拒绝读取项目目录之外的文件。"

    if not file_path.exists():
        return f"文件不存在：{relative_path}"

    if not file_path.is_file():
        return f"这不是文件：{relative_path}"

    policy = _load_access_policy()
    allowed, reason = _check_file_access(root, file_path, policy)

    if not allowed:
        return f"拒绝读取文件：{relative_path}。原因：{reason}"

    if not _is_text_file(file_path):
        return f"暂不读取这种文件类型：{file_path.suffix or '无扩展名'}"

    try:
        with file_path.open(encoding="utf-8", errors="replace") as file:
            raw_content = file.read(MAX_FILE_CHARS + 1)
    except OSError as read_error:
        return f"读取文件失败：{read_error}"

    truncated = len(raw_content) > MAX_FILE_CHARS
    raw_content = raw_content[:MAX_FILE_CHARS]
    numbered_lines = [
        f"{line_number}: {line}"
        for line_number, line in enumerate(raw_content.splitlines(), start=1)
    ]
    content = "\n".join(numbered_lines)

    if truncated:
        content += f"\n\n文件内容过长，只读取前 {MAX_FILE_CHARS} 个字符。"

    return content or "文件是空的。"


@tool
def search_project(project_path: str, keyword: str) -> str:
    """在项目文本文件中搜索关键词，返回文件名、行号和匹配内容。"""
    root, error = _get_project_root(project_path)

    if error:
        return error

    keyword = keyword.strip()

    if not keyword:
        return "搜索关键词不能为空。"

    if len(keyword) > MAX_SEARCH_KEYWORD_CHARS:
        return f"搜索关键词过长，最多允许 {MAX_SEARCH_KEYWORD_CHARS} 个字符。"

    matches: list[str] = []
    keyword_lower = keyword.lower()
    policy = _load_access_policy()

    if policy[1]:
        return policy[1]

    for file_path in _walk_project_files(root, policy):
        allowed, _ = _check_file_access(root, file_path, policy)

        if (
            not _resolves_inside_root(root, file_path)
            or not allowed
            or not _is_text_file(file_path)
        ):
            continue

        try:
            if file_path.stat().st_size > MAX_SEARCH_FILE_BYTES:
                continue

            with file_path.open(encoding="utf-8", errors="replace") as file:
                for line_number, line in enumerate(file, start=1):
                    if keyword_lower not in line.lower():
                        continue

                    relative_path = file_path.relative_to(root)
                    matched_line = line.strip()

                    if len(matched_line) > MAX_MATCH_LINE_CHARS:
                        matched_line = matched_line[:MAX_MATCH_LINE_CHARS] + "..."

                    matches.append(
                        f"{relative_path}:{line_number}: {matched_line}"
                    )

                    if len(matches) >= MAX_SEARCH_RESULTS:
                        return (
                            "\n".join(matches)
                            + f"\n\n匹配结果过多，只显示前 {MAX_SEARCH_RESULTS} 条。"
                        )
        except OSError:
            continue

    if not matches:
        return f"没有找到关键词：{keyword}"

    return "\n".join(matches)


@tool
def analyze_project(project_path: str) -> str:
    """分析项目类型、配置文件和可能的入口文件。只读，不修改项目。"""
    root, error = _get_project_root(project_path)

    if error:
        return error

    policy = _load_access_policy()

    if policy[1]:
        return policy[1]

    project_files = {
        file_path.name
        for file_path in root.iterdir()
        if file_path.is_file()
        and _check_file_access(root, file_path, policy)[0]
    }
    project_types: list[str] = []
    evidence: list[str] = []
    entry_files: list[str] = []
    has_root_python = any(
        file_path.suffix.lower() == ".py"
        and _check_file_access(root, file_path, policy)[0]
        for file_path in root.iterdir()
        if file_path.is_file()
    )

    if (
        "requirements.txt" in project_files
        or "pyproject.toml" in project_files
        or has_root_python
    ):
        project_types.append("Python")

        if "requirements.txt" in project_files:
            evidence.append("requirements.txt")
        if "pyproject.toml" in project_files:
            evidence.append("pyproject.toml")
        if has_root_python and not evidence:
            evidence.append("根目录中的 .py 文件")

    if "package.json" in project_files:
        project_types.append("JavaScript/TypeScript")
        evidence.append("package.json")

    if "pom.xml" in project_files:
        project_types.append("Java Maven")
        evidence.append("pom.xml")

    if "build.gradle" in project_files or "build.gradle.kts" in project_files:
        project_types.append("Java/Gradle")
        evidence.append("Gradle 配置文件")

    if "hvigorfile.ts" in project_files or "oh-package.json5" in project_files:
        project_types.append("HarmonyOS ArkTS")
        evidence.append("鸿蒙项目配置文件")

    possible_entries = (
        "main.py",
        "app.py",
        "run.py",
        "manage.py",
        "package.json",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "hvigorfile.ts",
    )

    for file_name in possible_entries:
        if file_name in project_files:
            entry_files.append(file_name)

    if not project_types:
        project_types.append("暂时无法判断")

    result = [
        f"项目路径：{root}",
        f"项目类型：{', '.join(project_types)}",
    ]

    if evidence:
        result.append(f"判断依据：{', '.join(evidence)}")

    if entry_files:
        result.append(f"可能的入口或配置文件：{', '.join(entry_files)}")
    else:
        result.append("暂未发现常见入口文件。")

    return "\n".join(result)


def _read_small_text(file_path: Path) -> str:
    try:
        with file_path.open(encoding="utf-8", errors="replace") as file:
            return file.read(MAX_PACKAGE_FILE_CHARS)
    except OSError:
        return ""


@tool
def get_run_candidates(project_path: str) -> str:
    """根据项目配置生成候选安装与运行命令。只分析，不执行命令。"""
    root, error = _get_project_root(project_path)

    if error:
        return error

    policy = _load_access_policy()

    if policy[1]:
        return policy[1]

    files = {
        file_path.name
        for file_path in root.iterdir()
        if file_path.is_file()
        and _check_file_access(root, file_path, policy)[0]
    }
    commands: list[str] = []
    evidence: list[str] = []

    if "requirements.txt" in files:
        evidence.append("requirements.txt")
        commands.append("python -m pip install -r requirements.txt")

    if "pyproject.toml" in files:
        evidence.append("pyproject.toml")
        commands.append("python -m pip install -e .")

    for entry_file in ("main.py", "app.py", "run.py", "manage.py"):
        if entry_file not in files:
            continue

        evidence.append(entry_file)
        command = "python manage.py runserver" if entry_file == "manage.py" else f"python {entry_file}"
        commands.append(command)

    if "package.json" in files:
        evidence.append("package.json")
        commands.append("npm install")

        try:
            package_data = json.loads(_read_small_text(root / "package.json"))
            scripts = package_data.get("scripts", {}) if isinstance(package_data, dict) else {}

            if isinstance(scripts, dict):
                for script_name in list(scripts)[:MAX_NPM_SCRIPTS]:
                    commands.append(f"npm run {script_name}")
        except json.JSONDecodeError:
            pass

    if "pom.xml" in files:
        evidence.append("pom.xml")
        pom_content = _read_small_text(root / "pom.xml")
        maven_command = (
            "mvn spring-boot:run"
            if "spring-boot-maven-plugin" in pom_content
            else "mvn package"
        )
        commands.append(maven_command)

    gradle_name = "build.gradle.kts" if "build.gradle.kts" in files else "build.gradle"

    if gradle_name in files:
        evidence.append(gradle_name)
        gradle_content = _read_small_text(root / gradle_name)
        gradle_command = (
            "gradle bootRun"
            if "org.springframework.boot" in gradle_content
            else "gradle build"
        )
        commands.append(gradle_command)

    commands = list(dict.fromkeys(commands))
    evidence = list(dict.fromkeys(evidence))

    if not commands:
        return "没有根据常见配置文件找到可靠的候选命令。"

    result = [
        "以下是根据项目文件推断出的候选命令：",
        *[f"- {command}" for command in commands],
        "",
        f"判断依据：{', '.join(evidence)}",
        "",
        "这些命令只是候选命令，工具没有执行它们。",
    ]

    return "\n".join(result)


def get_blocklist_status() -> str:
    """返回集中式黑名单状态，不返回具体隐私规则。"""
    blocklist_path = ACCESS_POLICY_DIR / BLOCKLIST_FILE
    patterns, error = _load_access_policy()

    if error:
        return error

    if not blocklist_path.is_file():
        return f"黑名单文件不存在：{blocklist_path}"

    return (
        f"黑名单文件：{blocklist_path}\n"
        f"当前有效规则数量：{len(patterns)}"
    )


def check_project_path_access(project_path: str, requested_path: str) -> str:
    """本地检查文件或目录是否允许访问，不读取文件内容。"""
    root, error = _get_project_root(project_path)

    if error:
        return error

    raw_path = Path(requested_path.strip().strip('"').strip("'"))
    candidate = raw_path.resolve() if raw_path.is_absolute() else (root / raw_path).resolve()

    if not candidate.exists():
        return f"路径不存在：{requested_path}"

    policy = _load_access_policy()
    allowed, reason = _check_file_access(root, candidate, policy)

    if not allowed:
        return f"访问状态：拒绝\n原因：{reason}"

    if candidate.is_file() and not _is_text_file(candidate):
        return "访问状态：不读取\n原因：当前版本不支持这种文件类型。"

    return "访问状态：允许"
