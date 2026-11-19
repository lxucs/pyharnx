# pyharnx

[English](README.md) · **简体中文**

[![CI](https://github.com/lxucs/pyharnx/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/lxucs/pyharnx/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://github.com/lxucs/pyharnx/blob/main/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](https://github.com/lxucs/pyharnx/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/pyharnx)](https://pypi.org/project/pyharnx/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24283575.svg)](https://doi.org/10.5281/zenodo.24283575)

pyharnx 是**一个为 agent 实验而写的极简 harness，可以当做是 [pi](https://github.com/earendil-works/pi) 的轻量 Python 替代**，名字取自 **Py**thon **harn**ess for e**x**periments。

核心是一个**干净的 agentic loop**，并记录下每一条轨迹 —— 每次请求都按发出时的原样保存，可以阅读、调试，也可以拿去训练。

harness 支持读写文件、执行命令、搜索网页，具体用哪些，取决于你交给它的工具。有两种用法：

- **交互式终端**：类似 Claude Code CLI —— 思考过程与工具调用边生成边显示，实时给出 token、cache 与成本读数；会话可以恢复，也可以导出为网页。
- **Python API**：可以在 python 中直接调用，直接 `from pyharnx.agent import Agent`。[`search_agent/`](search_agent/) 是用这种方式写的一个例子。

<sub>注：pyharnx 前身名为 lab-harness，下方的演示与报告里显示旧名。</sub>

终端里的一次运行：

<img src="img/demo.gif" width="600" alt="pyharnx 在终端中逐次调用工具，从若干文档里回答一个问题">

在终端里用 `/export` 导出的[轨迹报告](https://lxucs.github.io/pyharnx/search_agent/runs/793/report.html) —— 整条 agent 轨迹摊开来，便于阅读：

<a href="https://lxucs.github.io/pyharnx/search_agent/runs/793/report.html"><img src="img/report.png" width="600" alt="一次搜索 agent 运行的轨迹报告：turns、requests、tool calls、tokens、cache、cost，然后是每一步"></a>

## 为什么做 pyharnx

做 agent 实验和做 agent 产品，对 harness 的要求并不相同。产品级 harness 追求开箱即用；实验要的是清楚知道发生了什么，并且每次只改一处。实验里反复卡住的是这四个问题：

1. **说不清模型当时看到了什么。** 一条响应离开它背后的请求就很难解读：system prompt、工具声明、模型、reasoning effort、config。这些会在会话中途改变，hook 也可能改写某一次请求。只保留对话的 harness，留下的结果既无法解释，也无法复现。
2. **想换一个零件，就得 fork 整个框架。** 实验每次只变一个工具、一个 hook、一个 provider 或一段 prompt。如果 loop 和周边功能缠在一起，每改一处都得读懂、修补一大片不相干的代码，还说不准别处有没有跟着变。
3. **轨迹只是副产品。** 调试一次运行、或拿它来训练，需要的是完整的 trace 和端点实际收到的请求体，而不是事后从日志里拼凑。

pyharnx 的回答是：核心做小，接缝留在该改的地方，每次请求都记下来。为此放弃的东西 —— MCP、sub-agents、plan mode 等 —— 列在[路线图](#路线图)里。

## 特性

- **极简。** 无状态的 agent loop 约 500 行代码，在 [`agent/loop.py`](pyharnx/agent/loop.py)；包在外面的有状态 `Agent`（transcript、subscribers、abort）约 150 行，在 [`agent/agent.py`](pyharnx/agent/agent.py)。没有其它框架依赖，你读到的就是运行的全部。
- **每次请求都可复现。** session 记录每次请求发出时的 system prompt、工具、模型、reasoning effort 与 config —— 会话中途的变化和 hook 的改写都在内。[`trajectories.py --wire`](examples/trajectories.py) 把它们导出为端点实际收到的 JSON 请求体。详见 [trajectories](docs/sessions.md#trajectories)。
- **轨迹读得懂。** 每次运行都是一份 append-only 的 JSONL transcript，附带 token、cache 与成本数字。`/export` 把它变成一页 HTML —— 就是上面那份[报告](https://lxucs.github.io/pyharnx/search_agent/runs/793/report.html)；会话也能从中断处恢复。
- **换零件，不动 loop。** 几乎所有扩展都走两个接缝：[事件流](docs/events.md)与四个 [hook](examples/hooks.py)。工具来自 registry，system prompt 是可配置的 TOML 段落，一个[自定义工具](examples/custom_tool.py)就是一个文件。
- **一个 loop，多家模型。** Claude、OpenAI、DeepSeek、GLM，或任何 OpenAI 兼容端点。所有端点与模型都是 [`llm/catalog.toml`](pyharnx/llm/catalog.toml) 里的一张表，接入新厂商或新模型是几行 TOML，不是改代码；在它们之间切换只需 `--model`。

## 架构

pyharnx 在 Python 里沿用了 pi 的分层 —— `llm/` 对应 pi-ai，`agent/` 对应 pi-agent-core，一个纯函数 loop 外面包一层有状态的 `Agent`。与 pi 的不同之处及原因见 [architecture.md](docs/architecture.md#relationship-to-pi)。

依赖严格向下：每个方框只 import 它下面的方框，`llm/` 不依赖任何其它层。（各层都会读取叶子模块 `config.py` 与 `logs.py`，二者只互相 import。）

```
         cli/                 终端、JSON sink     （订阅者）
          │
          ▼
       session/               transcript          （同样是订阅者）
          │
          ▼
        agent/   prompts/     loop · system prompt
          │
          ▼
        tools/                内置工具、registry
          │
          ▼
         llm/                 provider、消息、流式
```

| 层 | 职责 |
|---|---|
| `llm/` | 与 provider 无关的 LLM 访问：消息、模型、流式、工具声明 |
| `agent/` | agentic loop，以及持有 transcript、发出事件的有状态 `Agent` |
| `tools/` | 内置能力，以及向模型声明工具的 registry |
| `session/` | append-only JSONL transcript、恢复、重建请求 —— 是订阅者，不是依赖 |
| `prompts/` | system prompt：配置的段落、运行环境、项目的 `AGENTS.md`，构建一次后以字符串交给 agent |
| `cli/` | 事件流上的终端订阅者与 JSONL 订阅者 |

几乎所有可扩展的东西都走两个接缝：

**事件流。** `Agent.subscribe(listener)` 是观察一次运行的唯一方式。终端是订阅者，JSONL 写入器也是。每个事件都是只含 JSON 原语的 frozen dataclass，由 round-trip 测试保证 —— 正因如此，将来用另一种语言写的前端可以成为第三个订阅者。

**Hooks。** `before_tool_call`、`after_tool_call`、`prepare_request`、`finish_turn`。能放进 hook 的功能就不该进 loop —— 工具审批是一例，所以 `-p` 与交互模式行为不同，而 loop 不必分叉；context compaction 也会是一例。

细节见 [docs/architecture.md](docs/architecture.md)。

## 安装

```bash
uv tool install pyharnx      # 安装 pyharnx 命令到 PATH
pip install pyharnx          # 或装进当前环境
uv add pyharnx               # 或作为项目依赖
```

`pyharnx[ddgs]` 会增加无需 API key 的网页搜索后端。如果想边用边读、边改代码，就从 clone 开始：`uv sync`，然后 `uv run pyharnx`。

## 快速开始

```bash
export OPENAI_API_KEY=sk-...                          # 也可写在 .pyharnx/config.local.toml
export TAVILY_API_KEY=tvly-...                        # 可选，供 web_search 使用
pyharnx                                               # 交互式终端
pyharnx -p "summarize the config module"              # 单次执行
```

交互式终端的更多细节见 [examples/terminal.md](examples/terminal.md)。

不想每次都 export，可以把配置写进 `~/.pyharnx/config.local.toml`，对所有项目生效。它覆盖在默认值之上，因此只需要写要改的键：

```toml
[agent]
model = "gpt-6.1-sol"     # 默认模型；--model 优先

[providers.openai.openai]
api_key = "sk-..."        # 若设置了 OPENAI_API_KEY，环境变量优先

[tools.web.tavily]
api_key = "tvly-..."
```

所有配置项与各层的生效顺序见 [docs/configuration.md](docs/configuration.md)。

## 从 Python 调用

CLI 只是库上面薄薄一层，实验可以直接驱动 agent：

```python
import asyncio

from pyharnx.agent import Agent
from pyharnx.config import load_config
from pyharnx.llm.providers import route
from pyharnx.tools import default_registry

config = load_config()
model, provider = route(None, config)  # $PYHARNX_MODEL，否则用 agent.model
tools = default_registry().select(["read", "ls", "grep", "glob"])
agent = Agent(model=model, provider=provider, tools=tools, config=config)
messages = asyncio.run(agent.prompt("What does this project do?"))
```

这样构造的 agent 没有 system prompt。CLI 发送的那份由 `pyharnx.prompts` 的 `build_system_prompt` 构建，见 [quickstart.py](examples/quickstart.py)；具体段落见 [prompts.toml](pyharnx/prompts/prompts.toml) 里的 `[prompts]`。

[examples/](examples/) 还展示了流式事件、自定义工具、全部四个 hook、无需 API key 的脚本化模型，以及导出会话请求用于训练。配置项与所有环境变量见 [docs/configuration.md](docs/configuration.md)。

## 示例：基于 pyharnx 的 search agent

[`search_agent/`](search_agent/) 是一个 search agent —— 通过检索与阅读文档来回答问题 —— 作为一个程序，一条命令即可运行。agent 本身只有几行：

```python
model, provider = route(None, config)  # 模型完全由配置决定
tools = tools_for(settings.tools, settings.corpus)  # 内置工具 + search_docs
agent = Agent(
    model=model,
    provider=provider,
    tools=tools,
    config=config,
    system_prompt=SYSTEM_PROMPT.format(corpus=settings.corpus),
    cwd=str(settings.cwd),
)
messages = await agent.prompt(question)
```

`uv run python -m search_agent` 即可运行；仓库里还提交了一次真实运行供查阅：[它生成的报告](https://lxucs.github.io/pyharnx/search_agent/runs/793/report.html)，旁边是 JSON 格式的轨迹。

## 文档

| 页面 | 内容 |
|---|---|
| [examples/](examples/) | 可运行的用法，终端与 Python 两侧 |
| [search_agent/](search_agent/) | 一个 search agent：完整的 Python 程序，附一次已提交的运行记录 |
| [architecture.md](docs/architecture.md) | 分层、模块边界、与 pi 的差异 |
| [events.md](docs/events.md) | 运行时与前端之间的事件协议 |
| [providers.md](docs/providers.md) | provider 契约、profile、接入新厂商 |
| [tools.md](docs/tools.md) | 工具契约、内置工具、新增工具 |
| [sessions.md](docs/sessions.md) | transcript 格式、恢复、重建轨迹 |
| [cli.md](docs/cli.md) | 终端、参数、快捷键、用量与成本读数 |
| [configuration.md](docs/configuration.md) | 配置文件、环境变量、模型与价格、prompt |
| [contributing.md](docs/contributing.md) | 代码约定、架构不变量、配置规则 |

文档页均为英文。贡献指南见 [docs/contributing.md](docs/contributing.md)；AI coding agent 还应阅读 [AGENTS.md](AGENTS.md)。

## 路线图

- **Context compaction** —— 唯一计划中但尚未实现的部分。它可以放进 `prepare_request` hook，因此落地时无需改动 loop。

不在计划内：MCP、sub-agents、plan mode、RPC 控制通道、插件化扩展、沙箱、provider 原生 `web_search`。每一项都是为了让核心保持小而可读所做的取舍；每一项需要什么、为什么不做，见 [docs/README.md](docs/README.md#todo)。

## 引用

如果 pyharnx 对你的研究有帮助，GitHub 的 **Cite this repository** 按钮可以从 [CITATION.cff](CITATION.cff) 生成 APA 或 BibTeX 格式的引用。DOI [10.5281/zenodo.24283575](https://doi.org/10.5281/zenodo.24283575) 指向最新版本；每个 release 在 Zenodo 上另有自己的记录。

## 许可

[MIT](LICENSE)。
