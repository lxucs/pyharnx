# pyharnx

**English** · [简体中文](https://github.com/lxucs/pyharnx/blob/main/README.zh-CN.md)

[![CI](https://github.com/lxucs/pyharnx/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/lxucs/pyharnx/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://github.com/lxucs/pyharnx/blob/main/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](https://github.com/lxucs/pyharnx/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/pyharnx)](https://pypi.org/project/pyharnx/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24283575.svg)](https://doi.org/10.5281/zenodo.24283575)

pyharnx is **a minimal harness built for agent experiments, a lightweight
Python alternative to [pi](https://github.com/earendil-works/pi)**, short for
**Py**thon **harn**ess for e**x**periments.

It has a **clean agentic loop**, friendly for research experiments in python, with
built-in support to record and visualize trajectories for training or debugging.
The code is small enough to read in an afternoon, and complete enough to run end to end.

The model reads and writes files, runs commands and searches the web, with
whichever of those tools you give it. There are two ways in:

- **An interactive terminal**, just like Claude Code CLI — thinking and
  tool calls as they stream, a token, cache and cost readout, and sessions that
  resume and export as a web page.
- **A Python API**, ready in Python directly — `from pyharnx.agent import Agent` is
  the whole integration. [`search_agent/`](https://github.com/lxucs/pyharnx/tree/main/search_agent) is a complete search
  agent example built that way.

<sub>Note: pyharnx was previously named lab-harness; the demo and report below
show the old name.</sub>

A run in the terminal:

<img src="https://github.com/lxucs/pyharnx/raw/main/img/demo.gif" width="600" alt="pyharnx in the terminal: a question answered from a handful of documents, one tool call at a time">

The [trajectory report](https://lxucs.github.io/pyharnx/search_agent/runs/793/report.html) a run records by `/export` in the terminal — the whole agentic trace for easy reading:

<a href="https://lxucs.github.io/pyharnx/search_agent/runs/793/report.html"><img src="https://github.com/lxucs/pyharnx/raw/main/img/report.png" width="600" alt="The trajectory report of a search agent run: turns, requests, tool calls, tokens, cache and cost, then every step"></a>

## Why pyharnx

An agent experiment asks different things of a harness than a product does. A
product harness is built to get work done out of the box; an experiment needs
to know exactly what happened, and to change one thing at a time. Four problems
keep getting in the way:

1. **You can't tell what the model actually saw.** A response means little
   without the request behind it: the system prompt, the tool declarations,
   the model, the reasoning effort, the config. Those change mid-session, and a
   hook may rewrite a single request.
2. **Changing one piece means forking the rest.** An experiment varies one
   tool, one hook, one provider, one prompt. When the loop is tangled up with
   the features around it, each change means reading and patching code you do
   not care about — and never being sure what else moved.
3. **Trajectories are an afterthought.** Debugging a run, or training on it,
   needs the whole trace and the exact bodies the endpoint received — not logs
   to reconstruct them from.

pyharnx's answer: keep the core small, put the seams where changes go, and
record every request. What it gives up for that — MCP, sub-agents, plan mode
and the like — is listed under
[Roadmap](https://github.com/lxucs/pyharnx#roadmap).

## Features

- **Minimal.** The stateless agent loop is about 500 lines of code, in
  [`agent/loop.py`](https://github.com/lxucs/pyharnx/blob/main/pyharnx/agent/loop.py); the stateful `Agent` that wraps
  it — transcript, subscribers, abort — about 150, in
  [`agent/agent.py`](https://github.com/lxucs/pyharnx/blob/main/pyharnx/agent/agent.py). No other framework dependencies, so
  what you read is all that runs.
- **Every request reproducible.** A session records the system prompt, tools,
  model, reasoning effort and config each request was sent with — changes
  mid-session and a hook's rewrites included.
  [`trajectories.py --wire`](https://github.com/lxucs/pyharnx/blob/main/examples/trajectories.py) exports them as the JSON
  bodies the endpoint got. See [trajectories](https://github.com/lxucs/pyharnx/blob/main/docs/sessions.md#trajectories).
- **Trajectories you can read.** Every run is an append-only JSONL transcript
  with its token, cache and cost numbers. `/export` turns it into one HTML
  page — the [report](https://lxucs.github.io/pyharnx/search_agent/runs/793/report.html) above — and the
  session resumes where it left off.
- **Change a piece, not the loop.** Almost everything extensible goes through
  two seams: the [event stream](https://github.com/lxucs/pyharnx/blob/main/docs/events.md) and four
  [hooks](https://github.com/lxucs/pyharnx/blob/main/examples/hooks.py). Tools come from a registry, the system prompt is
  configurable TOML sections, and a [custom tool](https://github.com/lxucs/pyharnx/blob/main/examples/custom_tool.py) is one
  file.
- **One loop, many models.** Claude, OpenAI, DeepSeek, GLM, or any other
  OpenAI-compatible endpoint. Every endpoint and model is a table in
  [`llm/catalog.toml`](https://github.com/lxucs/pyharnx/blob/main/pyharnx/llm/catalog.toml), so a new vendor or model
  is a few lines of TOML, not code, and switching between them is `--model`.

## Architecture

pyharnx keeps pi's layering — `llm/` for pi-ai, `agent/` for pi-agent-core, a
pure loop wrapped by a stateful `Agent` — in Python. Where it departs from pi,
and why: [architecture.md](https://github.com/lxucs/pyharnx/blob/main/docs/architecture.md#relationship-to-pi).

Dependencies point strictly downward: each box imports only from the boxes
below it, and `llm/` from no other layer. (Every layer reads the leaf modules
`config.py` and `logs.py`, which import only each other.)

```
         cli/                 terminal, json sink   (subscribers)
          │
          ▼
       session/               transcripts           (a subscriber too)
          │
          ▼
        agent/   prompts/     the loop · the system prompt
          │
          ▼
        tools/                built-ins, the registry
          │
          ▼
         llm/                 providers, messages, streaming
```

| Layer | Responsibility |
|---|---|
| `llm/` | Provider-neutral LLM access — messages, models, streaming, tool declarations |
| `agent/` | The agentic loop and a stateful `Agent` that owns the transcript and emits events |
| `tools/` | Built-in capabilities and the registry that declares them to the model |
| `session/` | Append-only JSONL transcripts, resume, rebuilding requests — a subscriber, not a dependency |
| `prompts/` | The system prompt: the configured sections, the environment, the project's `AGENTS.md` — built once and handed to the agent as a string |
| `cli/` | Terminal and JSONL subscribers to the event stream |

Two seams carry almost everything extensible:

**The event stream.** `Agent.subscribe(listener)` is the only way to observe a
run. The terminal is a subscriber; so is the JSONL writer. Every event is a
frozen dataclass of JSON primitives, enforced by a round-trip test — which is
what lets a frontend in another language be a third subscriber later.

**The hooks.** `before_tool_call`, `after_tool_call`, `prepare_request`, and
`finish_turn`. A feature that fits a hook does not belong in the loop — tool
approval is one, which is why `-p` and interactive modes differ without the
loop branching. Context compaction will be another.

Details in [docs/architecture.md](https://github.com/lxucs/pyharnx/blob/main/docs/architecture.md).

## Install

```bash
uv tool install pyharnx      # the pyharnx command, on your PATH
pip install pyharnx          # or into the current environment
uv add pyharnx               # or as a dependency of your project
```

`pyharnx[ddgs]` adds the keyless web search backend. To read and change the
code as you go, work from a clone instead: `uv sync`, then `uv run pyharnx`.

## Quick start

```bash
export OPENAI_API_KEY=sk-...                          # or api_key in .pyharnx/config.local.toml
export TAVILY_API_KEY=tvly-...                        # optional, for web_search
pyharnx                                               # interactive terminal
pyharnx -p "summarize the config module"              # one-shot
```

Check [examples/terminal.md](https://github.com/lxucs/pyharnx/blob/main/examples/terminal.md) for more details on the interactive terminal.

To keep settings without exporting them each time, put them in
`~/.pyharnx/config.local.toml` for every project. It merges over the
defaults, so it holds only the keys you change:

```toml
[agent]
model = "gpt-6.1-sol"     # the default model; --model still wins

[providers.openai.openai]
api_key = "sk-..."        # OPENAI_API_KEY still wins if set

[tools.web.tavily]
api_key = "tvly-..."
```

Every key, and the order the layers apply in:
[docs/configuration.md](https://github.com/lxucs/pyharnx/blob/main/docs/configuration.md).

## From Python

The CLI is a thin layer over a library, so an experiment can drive the agent
directly:

```python
import asyncio

from pyharnx.agent import Agent
from pyharnx.config import load_config
from pyharnx.llm.providers import route
from pyharnx.tools import default_registry

config = load_config()
model, provider = route(None, config)  # $PYHARNX_MODEL, else agent.model
tools = default_registry().select(["read", "ls", "grep", "glob"])
agent = Agent(model=model, provider=provider, tools=tools, config=config)
messages = asyncio.run(agent.prompt("What does this project do?"))
```

That agent has no system prompt. `build_system_prompt` from `pyharnx.prompts`
builds the one the CLI sends, as [quickstart.py](https://github.com/lxucs/pyharnx/blob/main/examples/quickstart.py) shows;
see the `[prompts]` sections in [prompts.toml](https://github.com/lxucs/pyharnx/blob/main/pyharnx/prompts/prompts.toml).

[examples/](https://github.com/lxucs/pyharnx/tree/main/examples) goes further: streaming events, a custom tool, all four
hooks, a scripted model that needs no key, and exporting a session's requests
for training. Configuration and every environment variable:
[docs/configuration.md](https://github.com/lxucs/pyharnx/blob/main/docs/configuration.md).

## Example: a search agent built on pyharnx

[`search_agent/`](https://github.com/lxucs/pyharnx/tree/main/search_agent) is a search agent — an agent that answers a
question by searching and reading documents — running as a program you can start
with one command. The agent itself is a few lines:

```python
model, provider = route(None, config)  # the model, from config alone
tools = tools_for(settings.tools, settings.corpus)  # built-ins plus search_docs
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

`uv run python -m search_agent` runs it, and a real run is committed to look
at: [the report it produced](https://lxucs.github.io/pyharnx/search_agent/runs/793/report.html), with the
trajectory as JSON beside it.

## Documentation

| Page | Covers |
|---|---|
| [examples/](https://github.com/lxucs/pyharnx/tree/main/examples) | Runnable usage, from the terminal and from Python |
| [search_agent/](https://github.com/lxucs/pyharnx/tree/main/search_agent) | A search agent: a whole program in Python, and a committed run to read |
| [architecture.md](https://github.com/lxucs/pyharnx/blob/main/docs/architecture.md) | Layering, module boundaries, deviations from pi |
| [events.md](https://github.com/lxucs/pyharnx/blob/main/docs/events.md) | The event protocol between runtime and frontend |
| [providers.md](https://github.com/lxucs/pyharnx/blob/main/docs/providers.md) | Provider contract, profiles, adding a vendor |
| [tools.md](https://github.com/lxucs/pyharnx/blob/main/docs/tools.md) | Tool contract, built-ins, adding a tool |
| [sessions.md](https://github.com/lxucs/pyharnx/blob/main/docs/sessions.md) | Transcript format, resume, rebuilding trajectories |
| [cli.md](https://github.com/lxucs/pyharnx/blob/main/docs/cli.md) | Terminal, flags, keybindings, the usage and cost readout |
| [configuration.md](https://github.com/lxucs/pyharnx/blob/main/docs/configuration.md) | Config files, environment variables, models and prices, prompts |
| [contributing.md](https://github.com/lxucs/pyharnx/blob/main/docs/contributing.md) | Code conventions, architectural invariants, config rules |

Contributing: [docs/contributing.md](https://github.com/lxucs/pyharnx/blob/main/docs/contributing.md). AI coding agents
should also read [AGENTS.md](https://github.com/lxucs/pyharnx/blob/main/AGENTS.md).

## Roadmap

- **Context compaction** — the one planned piece unbuilt. It fits the
  `prepare_request` hook, so it lands without touching the loop.

Not planned: MCP, sub-agents, plan mode, an RPC control channel,
extensions-as-plugins, sandboxing, provider-native `web_search`. Each is a
trade for a core that stays small and readable; what each item needs, and why
it is left out: [docs/README.md](https://github.com/lxucs/pyharnx/blob/main/docs/README.md#todo).

## Citation

If pyharnx helps your research, GitHub's **Cite this repository** button
gives a citation in APA or BibTeX, from [CITATION.cff](https://github.com/lxucs/pyharnx/blob/main/CITATION.cff).
Its DOI, [10.5281/zenodo.24283575](https://doi.org/10.5281/zenodo.24283575),
resolves to the latest release; each release's Zenodo record has one of its own.

## License

[MIT](https://github.com/lxucs/pyharnx/blob/main/LICENSE).
