# RepoPilot

RepoPilot 是一个面向初学者的只读项目学习与报错诊断 Agent。用户可以选择本地项目目录或获准访问的 GitHub 仓库，并用中文询问项目类型、目录结构、入口文件、运行方式和报错原因。

第三版坚持一个明确边界：**只读取和分析，不修改、删除、克隆或运行被分析的项目。**

## 第三版功能

- 识别 Python、JavaScript/TypeScript、Maven、Gradle 和 HarmonyOS ArkTS 项目。
- 列出项目文件，并跳过虚拟环境、依赖目录、构建目录和缓存目录。
- 按相对路径读取文本文件，返回真实行号。
- 在项目中搜索关键词，返回文件名、行号和匹配内容。
- 根据配置文件给出安装和运行候选命令，但不执行命令。
- 根据完整报错分析现象、依据、原因和解决步骤。
- 支持在程序运行时切换要分析的项目。
- 支持多行粘贴 Traceback，整段内容只发起一次 Agent 分析。
- 拒绝读取 `.env`、私钥和常见凭据文件。
- 支持在 RepoPilot 中集中配置隐私黑名单。
- 支持 `files` 本地文件查询，API 限流时也可使用。
- 支持 `check` 本地检查文件访问权限，不读取文件内容。
- 支持输入公开 GitHub 仓库主页链接。
- 支持使用 `GITHUB_TOKEN` 登录 GitHub，提高 API 额度。
- 可通过显式开关只读分析令牌获准访问的私有仓库，默认关闭。
- 使用 `github` 查看登录状态、私有仓库开关和 REST API 剩余额度。
- 读取公开仓库的名称、描述、主要语言、默认分支和更新时间。
- 通过 GitHub 文件树查看仓库结构，并过滤敏感路径。
- 按需读取公开仓库中的文本文件，返回真实行号。
- 将 GitHub 文件内容视为不可信外部数据，不执行其中的指令。
- 默认关闭 SDK tracing，避免后台追踪失败污染终端。
- 对单次分析设置工具调用上限，避免无休止调用。
- 使用 `history` 查看当前运行期间的成功分析记录，不自动写入磁盘。
- 使用 `report` 将最近一次成功分析显式导出为 Markdown 报告。

## 项目结构

```text
repo-learning-agent/
├── main.py            # 终端程序与 Agent 配置
├── tools.py           # 本地项目与 GitHub 仓库只读工具
├── reporting.py       # 会话内历史与显式报告导出
├── test_tools.py      # 不调用模型 API 的离线测试
├── test_main.py       # 终端辅助逻辑的离线测试
├── test_reporting.py  # 历史与报告功能的离线测试
├── requirements.txt  # Python 依赖
├── .gitignore         # Git 忽略规则
└── README.md          # 使用说明
```

## 安装

在 PowerShell 中进入项目目录：

```powershell
Set-Location D:\GitHub\repo-learning-agent
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

确认当前终端可以读取智谱 API Key：

```powershell
if ($env:ZHIPU_API_KEY) { "智谱 API Key 已设置" } else { "智谱 API Key 未设置" }
```

不要把 API Key 写进代码、README 或提交到 GitHub。

## 隐私黑名单

访问规则集中保存在 **RepoPilot 自己的根目录**中：

```text
D:\GitHub\repo-learning-agent\.repopilotignore
```

不需要在被分析的项目中创建任何配置文件。修改规则后，下一次提问立即生效，不需要重启程序。这个配置文件已经加入 `.gitignore`，不会随项目上传到 GitHub。

### 黑名单：`.repopilotignore`

黑名单中的文件不会出现在文件列表中，不能被读取、搜索、识别为入口文件，也不会参与运行命令分析。

项目已经自带 `.repopilotignore` 模板。打开它并添加规则：

```text
# 整个隐私目录
private/
personal-data/

# 任意位置的这些文件
*.log
*.private.json
profile.txt

# 指定路径
src/config/personal.json

# 指定某个项目中的完整路径
D:/GitHub/my-project/data/user_info.json
D:/GitHub/my-project/private/
```

### 规则说明

- 空行会被忽略。
- 以 `#` 开头的是注释。
- 路径统一建议使用 `/`，Windows 路径也一样。
- 完整路径可以不加引号；误加一层单引号或双引号也能识别。
- `private/` 表示整个目录及其子目录。
- `*.log`、`*.json` 等支持通配符。
- 相对规则会应用到每一个本地或 GitHub 项目，例如 `private/` 会屏蔽所有项目中的 `private` 目录。
- 完整路径只屏蔽指定项目中的文件，例如 `D:/GitHub/demo/private/user.json`。
- `.repopilotignore` 本身不会提供给 Agent。
- `.env`、私钥、凭据文件和内置忽略目录始终禁止访问。

默认允许访问普通文本和代码文件；只有命中黑名单或内置敏感规则的文件会被拒绝。

## 运行

```powershell
python main.py
```

启动后可以输入本地项目目录：

```text
D:\GitHub\agent\_firstTry
```

也可以输入 GitHub 仓库主页链接：

```text
https://github.com/openai/openai-python
```

然后可以提问：

```text
请分析这个项目的类型、入口文件和运行方式。
```

```text
请诊断 ModuleNotFoundError: No module named 'chromadb'，不要执行命令。
```

分析 GitHub 仓库时可以提问：

```text
请根据仓库文件和 README，说明项目用途、技术栈、入口文件和候选运行方式。
```

## 终端命令

- `help`：显示帮助。
- `project`：切换本地项目或 GitHub 仓库。
- `files`：列出当前目标中的可见文件，不调用模型 API。
- `files txt`：列出当前目标中的 `.txt` 文件，不调用模型 API。
- `check private/data.txt`：检查文件是否会被黑名单或内置规则阻止，不读取内容。
- `policy`：显示黑名单文件位置和有效规则数量，不显示隐私规则。
- `github`：显示 GitHub Token、私有仓库开关和 REST API 额度状态，不显示令牌。
- `history`：显示当前运行期间最近 20 条成功分析记录。
- `history clear`：清空内存中的分析记录。
- `report`：把最近一次成功分析导出到本地 `reports/`，不会自动上传 GitHub。
- `multi`：进入多行输入模式；粘贴完成后单独输入 `END`，整段只分析一次。
- `exit`：退出程序。

多行报错示例：

```text
请输入问题：multi
请粘贴多行问题或完整报错，单独输入 END 结束：
Traceback (most recent call last):
  ...
ModuleNotFoundError: No module named 'chromadb'
END
```

## 离线测试

下面的测试使用本地临时目录和模拟 GitHub 响应，不调用模型 API，也不会真实访问 GitHub：

```powershell
python -m unittest -v
```

测试会在系统临时目录建立示例项目，结束后自动清理，不会修改你的真实项目。

## GitHub 登录与私有仓库

公开仓库建议设置 GitHub Token，避免共享 IP 的匿名访问额度过低：

```powershell
$env:GITHUB_TOKEN="你的细粒度 GitHub Token"
```

令牌只保存在当前终端环境中，不要写入代码、README 或 `.env` 后上传。公开仓库无需写权限。

私有仓库默认拒绝读取。只有在令牌已经具备目标仓库只读权限，并且你明确接受把按需读取的代码片段发送给智谱模型时，才设置：

```powershell
$env:REPOPILOT_ALLOW_PRIVATE_GITHUB="1"
```

关闭私有仓库访问：

```powershell
Remove-Item Env:REPOPILOT_ALLOW_PRIVATE_GITHUB -ErrorAction SilentlyContinue
```

## 第三版限制

- GitHub 功能支持公开仓库，以及显式授权的只读私有仓库；不支持 Issue 或 Pull Request。
- 不克隆仓库，只通过 GitHub REST API 获取文件树和按需读取文本文件。
- 未配置 GitHub 身份验证时，公开 API 通常按来源 IP 限制为每小时 60 次请求。
- 超大仓库的文件树可能被 GitHub 截断；RepoPilot 最多向 Agent 展示前 120 个可见文件。
- 不提供远程仓库全文搜索，避免为大量文件发出请求并快速耗尽 GitHub 限额。
- 普通自然语言问题需要调用 Agent；`files`、`check`、`policy`、`project`、`help` 和 `exit` 不调用 API。
- GitHub 目标使用 `files` 时虽然不调用模型 API，但会访问 GitHub API。
- 历史记录只保存在当前进程内；退出程序后自动消失。
- `report` 会把用户明确要求导出的内容写入本地 `reports/`，该目录默认不上传 GitHub。
- 不负责自动修复代码或执行命令。

后续版本可以继续加入多项目比较和经用户确认后的代码修改工作流。
