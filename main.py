import asyncio
import os
import re
from pathlib import Path

from agents import Agent, Runner, set_tracing_disabled
from agents.exceptions import MaxTurnsExceeded
from openai import APIConnectionError, AuthenticationError, RateLimitError

from tools import (
    analyze_project,
    check_project_path_access,
    get_blocklist_status,
    get_run_candidates,
    list_project_files,
    list_project_files_local,
    read_project_file,
    search_project,
)


TRACING_ENABLED_VALUES = {"1", "true", "yes"}

if os.environ.get("REPOPILOT_ENABLE_TRACING", "").lower() not in TRACING_ENABLED_VALUES:
    set_tracing_disabled(True)


AGENT_INSTRUCTIONS = """
你是 RepoPilot，一个本地项目学习与调试助手。

你的能力边界：
- 只能通过工具读取和分析用户指定的本地项目。
- 不能修改、删除或运行项目文件，也不能声称已经执行或修复。
- 不能读取项目外部文件；不要尝试读取密钥、凭据或环境变量文件。
- 必须尊重 RepoPilot 目录中的集中式 .repopilotignore 黑名单。
- 所有结论必须基于工具实际返回的内容。无法确认时，明确说明是推测。

分析项目时：
1. 先调用 analyze_project 判断项目类型。
2. 调用 list_project_files 查看结构。
3. 按需读取 README.md、requirements.txt、pyproject.toml、package.json、
   pom.xml、build.gradle 或入口源文件，不要无目的读取全部文件。
4. 用户询问运行方式时，必须调用 get_run_candidates。
5. 只能把工具结果称为候选命令，不得声称已经执行。
6. 引用代码位置时，只能使用工具返回的真实文件名和行号。

诊断报错时：
1. 识别错误类型、关键错误信息、相关模块和文件路径。
2. 使用 search_project 搜索相关模块、函数或错误关键词。
3. 使用 read_project_file 检查相关源代码和依赖配置。
4. 回答分为：错误现象、判断依据、最可能的原因、建议的解决步骤。

一般回答分为：项目现状、判断依据、下一步建议。
回答使用简洁中文，给初学者解释必要术语。
""".strip()


agent = Agent(
    name="RepoPilot",
    instructions=AGENT_INSTRUCTIONS,
    tools=[
        analyze_project,
        get_run_candidates,
        list_project_files,
        read_project_file,
        search_project,
    ],
)


def show_help() -> None:
    print(
        "\n可用命令：\n"
        "  help     查看帮助\n"
        "  project  更换要分析的项目\n"
        "  files    本地列出文件，不调用 API，例如 files txt\n"
        "  check    本地检查访问权限，例如 check private/data.txt\n"
        "  policy   查看黑名单状态，不显示具体规则\n"
        "  multi    输入多行问题或完整报错，单独输入 END 结束\n"
        "  exit     退出程序\n"
        "\n普通问题直接输入一行并按回车。"
    )


def read_project_path() -> Path | None:
    while True:
        raw_path = input("\n请输入要分析的项目路径：").strip().strip('"')

        if raw_path.lower() == "exit":
            return None

        if not raw_path:
            print("项目路径不能为空。")
            continue

        project_path = Path(raw_path).expanduser()

        if not project_path.exists():
            print(f"项目路径不存在：{raw_path}")
            continue

        if not project_path.is_dir():
            print(f"这个路径不是目录：{raw_path}")
            continue

        return project_path.resolve()


def read_multiline_question() -> str:
    print("请粘贴多行问题或完整报错，单独输入 END 结束：")
    lines: list[str] = []

    while True:
        line = input()

        if line.strip() == "END":
            break

        lines.append(line)

    return "\n".join(lines).strip()


def build_prompt(project_path: Path, question: str) -> str:
    return (
        f"当前正在分析的项目路径是：{project_path}\n"
        "请始终使用这个项目路径，不要自行猜测其他目录。\n"
        f"用户问题是：\n{question}"
    )


def extract_retry_wait(error: Exception) -> str | None:
    match = re.search(
        r"Please try again in "
        r"([0-9]+(?:\.[0-9]+)?[hms](?:[0-9]+(?:\.[0-9]+)?[hms])*)",
        str(error),
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


async def answer_question(project_path: Path, question: str) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        print("无法调用 Agent：当前终端未检测到 OPENAI_API_KEY。")
        print("你仍然可以使用 files、policy、project、help 和 exit 命令。")
        return

    print("\nAgent 开始分析...\n")

    try:
        result = await Runner.run(
            agent,
            build_prompt(project_path, question),
            max_turns=6,
        )
    except AuthenticationError:
        print("调用失败：API Key 无效或未被当前终端读取，请检查 OPENAI_API_KEY。")
        return
    except RateLimitError as error:
        wait_time = extract_retry_wait(error)
        print("调用失败：已触发 API 速率限制。")

        if wait_time:
            print(f"预计等待时间：{wait_time}")

        print("等待期间可以使用 files 命令进行本地文件查询，不消耗 API。")
        return
    except APIConnectionError:
        print("调用失败：无法连接 OpenAI API，请检查网络或当前终端的代理设置。")
        return
    except MaxTurnsExceeded:
        print("本次分析调用工具次数过多，已停止。请把问题缩小到一个具体目标后重试。")
        return
    except Exception as error:
        print(f"分析失败：{type(error).__name__}: {error}")
        return

    print("Agent 最终回答：")
    print(result.final_output)


async def main() -> None:
    print("RepoPilot 第一版已启动")
    print("输入 help 查看帮助，输入 exit 退出程序")

    if not os.environ.get("OPENAI_API_KEY"):
        print("未检测到 OPENAI_API_KEY：Agent 问答不可用，本地命令仍可使用。")

    project_path = read_project_path()

    if project_path is None:
        print("程序已退出")
        return

    print(f"当前项目：{project_path}")

    while True:
        question = input("\n请输入问题：").strip()
        command = question.lower()

        if command == "exit":
            print("程序已退出")
            break

        if command == "help":
            show_help()
            continue

        if command == "policy":
            print(f"\n{get_blocklist_status()}")
            continue

        if command == "check":
            print("用法：check 相对路径或完整路径")
            continue

        if command.startswith("check "):
            requested_path = question[6:].strip()
            result = check_project_path_access(
                str(project_path),
                requested_path,
            )
            print(f"\n{result}")
            continue

        if command == "files" or command.startswith("files "):
            extension = question[5:].strip() or None
            result = list_project_files_local(
                str(project_path),
                extension=extension,
            )
            print("\n本地文件结果：")
            print(result)
            continue

        if command == "project":
            new_project_path = read_project_path()

            if new_project_path is None:
                print("已取消更换项目。")
                continue

            project_path = new_project_path
            print(f"当前项目已更换为：{project_path}")
            continue

        if command == "multi":
            question = read_multiline_question()

        if not question:
            print("问题不能为空。")
            continue

        await answer_question(project_path, question)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        print("\n程序已退出")
