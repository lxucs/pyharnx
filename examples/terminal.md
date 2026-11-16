# The terminal

![An interactive session: the request typed in, thinking and tool calls as they stream, the answer, the usage line](../img/demo.gif)

The workflows people use most, from the repository root. Every flag, key and
config setting is in [docs/cli.md](../docs/cli.md).

## Interactive

```bash
export OPENAI_API_KEY=sk-...
uv run pyharnx
```

| Key or command | Does |
|---|---|
| `Ctrl-C` | Cancel the turn in flight; the session carries on |
| `Ctrl-O` | Expand or collapse the model's thinking |
| `/` | List the commands, each with what it does |
| `/status` | Tokens, cache hits and cost so far |
| `/effort [LEVEL]` | Show or set how hard the model thinks, e.g. `/effort low`; `/effort default` sends none |
| `/model [ID]` | Show or switch the model, among the ones this session's provider serves |
| `/export [PATH]` | Write the session so far as a web page, beside its transcript or to `PATH` |
| `/clear` | Forget the conversation; the transcript on disk keeps it |
| `/help` | Every command, with what it does |
| `Esc` | Close the command list once it is open |
| `Ctrl-D` | Exit |

Mutating tools — `bash`, `write`, `edit` — ask before they run, and anything
but an explicit yes denies. `--yes` turns the asking off.

A `HARNESS.md` or `AGENTS.md` in the working directory is appended to the
system prompt, so a project's conventions do not have to be rediscovered every
run.

## One-shot

```bash
uv run pyharnx -p "summarize the config module"
uv run pyharnx -p "summarize the config module" > summary.txt       # the answer alone
```

**There is no approval gate in `-p` mode** — nobody is at the keyboard to
answer, so `bash`, `write` and `edit` run unprompted. To rule them out, give
the run fewer tools; a tool left out is never offered to the model:

```bash
uv run pyharnx -p "review the config module" --tools read,ls,grep,glob
```

Tool notices go to stderr and the answer to stdout. The exit status is `1`
when the final turn errored or was aborted, `0` otherwise.

## Events as JSONL, for scripts

```bash
uv run pyharnx -p "what files are here?" --json \
  | jq -c 'select(.type == "tool_execution_end") | {tool_name, is_error, duration_ms}'
```

One event per line, flushed as it happens. The event types and their fields:
[docs/events.md](../docs/events.md).

## Sessions

```bash
uv run pyharnx --resume                     # what is saved for this directory
uv run pyharnx --resume <session-id>        # continue one; a unique prefix works
uv run pyharnx --no-save                    # write nothing
```

Continuing one prints the saved conversation — questions, answers, tool calls —
before the first prompt, so the session picks up where the eye left off.

### Viewing a session

```bash
uv run pyharnx --resume <session-id> --no-save       # read it in the terminal, then Ctrl-D
uv run pyharnx --export <session-id>                 # or as a web page; prints its path
open "$(uv run pyharnx --export)"                    # the latest session, in a browser (macOS)
```

`--resume` with `--no-save` is a read-only view: the whole conversation, Ctrl-O
to expand every thought, and nothing appended to the file. `--export` — or
`/export` inside a session — writes one self-contained HTML page beside the
transcript.

Transcripts live under `~/.pyharnx/sessions/`, one directory per project.
Each records what every request was sent with;
[trajectories.py](trajectories.py) exports them as JSONL, and with `--wire` as the
JSON bodies the endpoint received — OpenAI-format messages and tools, for a
Chat Completions model.

## Other models

```bash
uv run pyharnx --model gpt-6.1-sol
ANTHROPIC_API_KEY=sk-... uv run pyharnx --model claude-sonnet-5
DEEPSEEK_API_KEY=sk-... uv run pyharnx --model deepseek-flash       # routed by config
ZHIPUAI_API_KEY=... uv run pyharnx --model glm-5.3
uv run pyharnx --reasoning-effort low                              # think less
```

Adding a vendor or a model is a few lines of config:
[docs/configuration.md](../docs/configuration.md#provider-profiles).

## The system prompt

```bash
uv run pyharnx --system-prompt "Answer in one sentence."
uv run pyharnx -p "summarize the config module" --system-prompt-file prompts/terse.md
```

Either replaces the opening section of the default, which ships in
[`pyharnx/prompts/prompts.toml`](../pyharnx/prompts/prompts.toml), for
one run. The rest is still sent — how the harness works, the working
directory, platform and model, and a project's `AGENTS.md`. To change any
section for good, or leave one out, set it under `[prompts]` in config:
[docs/configuration.md](../docs/configuration.md#prompts).

## From another directory

Install the command once, from the repository root, and move the settings and
keys every project should get to `~/.pyharnx/`, which is read wherever the
harness runs:

```bash
uv tool install --editable .        # pyharnx on PATH; edits here apply at once
mkdir -p ~/.pyharnx
cp .pyharnx/config.local.toml ~/.pyharnx/config.local.toml
```

Then start it in the directory to work on — no `--cwd`, no `uv run`:

```bash
cd /path/to/project
pyharnx                             # its tools, AGENTS.md and sessions; your config
```

A `.pyharnx/` there still applies on top of yours. Without installing,
`uv run pyharnx --cwd /path/to/project` from here does the same.

## Debugging

```bash
uv run pyharnx --log-level debug -p "..."                 # trace a run on stderr
uv run pyharnx --log-level debug 2> pyharnx.log           # interactive, trace kept apart
```

The debug trace shows each request, response and tool call by size and id,
never by content.
