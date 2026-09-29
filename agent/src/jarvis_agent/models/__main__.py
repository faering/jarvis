"""The model playground: ``python -m jarvis_agent.models <list|pull|chat|bench> ...``.

    list                 the catalogue, and which model fills each role on this device
    pull <id>            download a model into its runtime (Ollama)
    chat <id>            talk to one model, with time to first token and tokens/s per reply
    bench <id> [<id>..]  run the Jarvis prompt set on each model and compare them

Runtimes are found through this device's config ([runtimes.<name>], JARVIS_RUNTIME_*);
``--base-url`` points at another server instead, e.g. an Ollama started by hand. On the Pi,
run it in the agent container: ``docker exec -it jarvis-agent-1 python -m jarvis_agent.models``.
"""

import argparse
import asyncio
import os
import platform
import statistics
import sys
import tomllib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from importlib import resources
from typing import TextIO

import httpx

from jarvis_agent.backends import ChatMessage
from jarvis_agent.config import ConfigError, load_config
from jarvis_agent.config.schema import JarvisConfig
from jarvis_agent.loop.voice import DEFAULT_SYSTEM_PROMPT
from jarvis_agent.models.catalogue import ROLES, WIRED, ModelEntry, load_catalogue
from jarvis_agent.models.probe import (
    ProbeError,
    Reply,
    chat,
    cpu_temp,
    loaded_size,
    ollama_root,
    pull,
    unload,
)

CHAT_ROLES = {"llm", "heavy_llm", "vlm"}
THINK_HELP = "let thinking models think first (off by default: the hot path can't wait)"
TIMEOUT = httpx.Timeout(300.0, connect=5.0)  # a cold model on a Pi CPU loads slowly

type ClientFactory = Callable[[str], httpx.AsyncClient]


def default_client(base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=TIMEOUT)


# -- helpers --------------------------------------------------------------------------------


class UsageError(Exception):
    pass


def entry_for(model_id: str) -> ModelEntry:
    """A catalogue model, or an ad-hoc ``ollama:<name>`` to try one before it's catalogued."""
    catalogue = load_catalogue()
    if model_id in catalogue.model:
        return catalogue.model[model_id]
    runtime, _, source = model_id.partition(":")
    if runtime == "ollama" and source:
        return ModelEntry(roles=("llm",), runtime="ollama", source=source, notes="ad hoc")
    known = ", ".join(sorted(catalogue.model))
    raise UsageError(
        f"unknown model {model_id!r}; the catalogue has: {known} "
        "(or try any Ollama model as ollama:<name>, e.g. ollama:gemma3:1b)"
    )


def base_url_for(config: JarvisConfig | None, entry: ModelEntry, override: str | None) -> str:
    if override:
        return override
    runtime = config.runtimes.get(entry.runtime) if config else None
    if runtime is None or not runtime.base_url:
        env = f"JARVIS_RUNTIME_{entry.runtime.upper()}_URL"
        raise UsageError(
            f"where is {entry.runtime!r}? Set {env} or [runtimes.{entry.runtime}] base_url, "
            "or pass --base-url"
        )
    return runtime.base_url


def client_url(entry: ModelEntry, base_url: str) -> str:
    """Ollama is reached through its own API root; everything else through ``/v1``."""
    return ollama_root(base_url) if entry.runtime == "ollama" else base_url


def fmt_s(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def fmt_rate(reply: Reply) -> str:
    if reply.tokens_per_s is None:
        return "-"
    return f"{'' if reply.exact else '~'}{reply.tokens_per_s:.1f}"


def fmt_bytes(n: int) -> str:
    return f"{n / 2**30:.2f} GiB" if n >= 2**30 else f"{n / 2**20:.0f} MiB"


def table(rows: list[list[str]], out: TextIO) -> None:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for row in rows:
        print("  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)).rstrip(), file=out)


# -- list -----------------------------------------------------------------------------------


def cmd_list(config: JarvisConfig | None, problems: list[str], out: TextIO) -> int:
    catalogue = load_catalogue()
    print("Catalogue (agent/src/jarvis_agent/models/catalogue.toml)\n", file=out)
    rows = [["ID", "ROLES", "RUNTIME", "SOURCE", "SIZE"]]
    for mid, e in sorted(catalogue.model.items()):
        rows.append([mid, ",".join(e.roles), e.runtime, e.source, e.size or ""])
    table(rows, out)
    if config is None:
        print("\nThis device: the config is invalid:", file=out)
        for problem in problems:
            print(f"  - {problem}", file=out)
        return 1
    where = config.profile or "no profile"
    print(f"\nThis device ({where}; layers: {' -> '.join(config.sources)})\n", file=out)
    backends = config.backend_settings()
    rows = [["ROLE", "MODEL", "USES", "SET BY"]]
    for role in ROLES:
        model_id = config.models.get(role)
        if role in WIRED:
            settings = getattr(backends, role)
            if settings.backend == "openai":
                uses = f"{settings.model} @ {settings.base_url}"
            else:
                uses = settings.backend
        else:
            uses = "not wired yet" if model_id else ""
        if model_id or role in WIRED:
            rows.append([role, model_id or "-", uses, config.set_by("models", role) or ""])
    table(rows, out)
    return 0


# -- pull -----------------------------------------------------------------------------------


async def cmd_pull(args, config, factory: ClientFactory, out: TextIO) -> int:
    if args.assigned:
        return await pull_assigned(config, factory, out)
    if not args.model:
        raise UsageError("pull needs a model, or --assigned for every model this device uses")
    entry = entry_for(args.model)
    if entry.runtime != "ollama":
        raise UsageError(
            f"pull only knows Ollama; {args.model!r} runs on {entry.runtime!r}, "
            "which fetches its own models (e.g. speaches PRELOAD_MODELS)"
        )
    base_url = base_url_for(config, entry, args.base_url)
    async with factory(client_url(entry, base_url)) as client:
        await pull(client, entry.source, lambda line: print(f"  {line}", file=out, flush=True))
    print(f"{args.model} ({entry.source}) is ready.", file=out)
    return 0


async def pull_assigned(config: JarvisConfig | None, factory: ClientFactory, out: TextIO) -> int:
    """Pull every Ollama model this device uses (what the deploy runs after starting)."""
    if config is None:
        raise UsageError("the config is invalid; `models list` shows why")
    backends = config.backend_settings()
    catalogue = load_catalogue()
    wanted: dict[tuple[str, str], str] = {}  # (ollama url, model) -> role
    for role, model_id in config.models.items():
        entry = catalogue.model[model_id]
        if entry.runtime != "ollama":
            print(f"  {role}: {model_id} runs on {entry.runtime}, skipped", file=out)
            continue
        settings = getattr(backends, role, None)
        if settings is not None and settings.backend != "openai":
            continue  # overridden to mock/none here
        base_url = settings.base_url if settings else base_url_for(config, entry, None)
        source = settings.model if settings else entry.source
        wanted.setdefault((ollama_root(base_url), source), role)
    if not wanted:
        print("No Ollama models assigned on this device.", file=out)
        return 0
    for (url, source), role in wanted.items():
        print(f"{role}: pulling {source} from {url}", file=out, flush=True)
        async with factory(url) as client:
            await pull(client, source, lambda line: print(f"  {line}", file=out, flush=True))
    print(f"Ready: {', '.join(source for _, source in wanted)}", file=out)
    return 0


# -- chat -----------------------------------------------------------------------------------


async def cmd_chat(args, config, factory: ClientFactory, stdin: TextIO, out: TextIO) -> int:
    entry = entry_for(args.model)
    if not CHAT_ROLES & set(entry.roles):
        raise UsageError(f"{args.model!r} is a {'/'.join(entry.roles)} model; chat needs an llm")
    base_url = base_url_for(config, entry, args.base_url)
    system = "" if args.no_system else DEFAULT_SYSTEM_PROMPT
    history: list[ChatMessage] = []
    print(
        f"Chatting with {args.model} ({entry.source} @ {base_url}). "
        "/reset clears the history, /quit or Ctrl+D ends.",
        file=out,
    )
    async with factory(client_url(entry, base_url)) as client:
        while True:
            print("you> ", end="", file=out, flush=True)
            line = stdin.readline()
            if not line or line.strip() == "/quit":
                print(file=out)
                return 0
            text = line.strip()
            if not text:
                continue
            if text == "/reset":
                history.clear()
                print("(history cleared)", file=out)
                continue
            history.append({"role": "user", "content": text})
            messages = ([{"role": "system", "content": system}] if system else []) + history
            print("jarvis> ", end="", file=out, flush=True)
            reply = await chat(
                client,
                entry.runtime,
                entry.source,
                messages,
                lambda t: print(t, end="", file=out, flush=True),
                think=args.think,
            )
            history.append({"role": "assistant", "content": reply.text})
            stats = [f"first token {fmt_s(reply.ttft_s)}s", f"{fmt_rate(reply)} tok/s"]
            if reply.tokens is not None:
                stats.append(f"{'' if reply.exact else '~'}{reply.tokens} tokens")
            if reply.load_s and reply.load_s > 0.5:
                stats.append(f"model load {fmt_s(reply.load_s)}s")
            print(f"\n  [{', '.join(stats)}]", file=out)


# -- bench ----------------------------------------------------------------------------------


def bench_prompts(path: str | None) -> list[dict[str, str]]:
    if path:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    else:
        text = (resources.files("jarvis_agent.models") / "bench_prompts.toml").read_text()
        data = tomllib.loads(text)
    prompts = data.get("prompt", [])
    if not prompts:
        raise UsageError("the prompt file has no [[prompt]] entries")
    return prompts


async def cmd_bench(args, config, factory: ClientFactory, out: TextIO) -> int:
    prompts = bench_prompts(args.prompts)
    system = "" if args.no_system else DEFAULT_SYSTEM_PROMPT
    entries = {mid: entry_for(mid) for mid in args.models}
    for mid, entry in entries.items():
        if not CHAT_ROLES & set(entry.roles):
            raise UsageError(f"{mid!r} is a {'/'.join(entry.roles)} model; bench needs llms")
    results: dict[str, dict] = {}
    for mid, entry in entries.items():
        base_url = base_url_for(config, entry, args.base_url)
        print(f"{mid}: ", end="", file=sys.stderr, flush=True)
        replies: dict[str, list[Reply]] = {}
        temp_before = cpu_temp()
        async with factory(client_url(entry, base_url)) as client:
            if entry.runtime == "ollama" and not args.warm:
                await unload(client, entry.source)  # LOAD = a cold start
            for prompt in prompts:
                for _ in range(args.runs):
                    messages: list[ChatMessage] = [{"role": "user", "content": prompt["text"]}]
                    if system:
                        messages.insert(0, {"role": "system", "content": system})
                    reply = await chat(
                        client, entry.runtime, entry.source, messages, think=args.think
                    )
                    replies.setdefault(prompt["id"], []).append(reply)
                    print(".", end="", file=sys.stderr, flush=True)
            size = await loaded_size(client, entry.source) if entry.runtime == "ollama" else None
        print(file=sys.stderr)
        temps = (temp_before, cpu_temp())
        results[mid] = {"entry": entry, "replies": replies, "size": size, "temps": temps}
    report(results, prompts, args, out)
    return 0


def temps(pair: tuple[float | None, float | None] | None) -> str:
    """``before→after`` in °C; a hot Pi 5 throttles (around 80 °C), which lowers tok/s."""
    if not pair or None in pair:
        return "-"
    return f"{pair[0]:.0f}→{pair[1]:.0f}"


def summary_rows(results: dict[str, dict]) -> list[list[str]]:
    rows = [["MODEL", "LOAD s", "FIRST TOKEN s", "TOK/S", "TOKENS", "IN MEMORY", "CPU °C"]]
    for mid, r in results.items():
        every = [rep for reps in r["replies"].values() for rep in reps]
        first = every[0]
        ttfts = [x.ttft_s for x in every if x.ttft_s is not None]
        rates = [x.tokens_per_s for x in every if x.tokens_per_s is not None]
        tokens = [x.tokens for x in every if x.tokens is not None]
        approx = "" if first.exact else "~"
        size = ""
        if r["size"]:
            total, on_accel = r["size"]
            size = fmt_bytes(total) + (f" ({fmt_bytes(on_accel)} GPU/NPU)" if on_accel else "")
        rows.append(
            [
                mid,
                fmt_s(first.load_s),
                fmt_s(statistics.median(ttfts)) if ttfts else "-",
                f"{approx}{statistics.median(rates):.1f}" if rates else "-",
                f"{approx}{sum(tokens)}" if tokens else "-",
                size,
                temps(r.get("temps")),
            ]
        )
    return rows


def report(results: dict[str, dict], prompts: list[dict[str, str]], args, out: TextIO) -> None:
    rows = summary_rows(results)
    if not args.markdown:
        table(rows, out)
        print("\nMedians over every prompt; LOAD = the first request's model load.", file=out)
        print("For the answers side by side, add --markdown.", file=out)
        return
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    print(f"# Model bench, {now}\n", file=out)
    print(f"- Device: `{platform.node()}` ({platform.machine()})", file=out)
    print(
        f"- Prompts: {len(prompts)} × {args.runs} run(s); system prompt: "
        f"{'none' if args.no_system else 'Jarvis default'}; "
        f"thinking: {'on' if args.think else 'off'}",
        file=out,
    )
    print(
        "- LOAD = the first request's model load; the rest are medians. "
        "`~` = approximate (streamed chunks, not the model's token count).\n",
        file=out,
    )
    print("| " + " | ".join(rows[0]) + " |", file=out)
    print("|" + "---|" * len(rows[0]), file=out)
    for row in rows[1:]:
        print("| " + " | ".join(row) + " |", file=out)
    for prompt in prompts:
        print(f"\n## {prompt['id']}\n\n> {prompt['text']}\n", file=out)
        for mid, r in results.items():
            reply = r["replies"][prompt["id"]][0]
            answer = reply.text.strip().replace("\n", "\n> ")
            stats = f"{fmt_s(reply.ttft_s)}s to first token, {fmt_rate(reply)} tok/s"
            print(f"**{mid}** ({stats})\n\n> {answer}\n", file=out)


# -- main -----------------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m jarvis_agent.models", description=__doc__.split("\n")[0]
    )
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="the catalogue and this device's models")
    for name, help_ in (("pull", "download a model (Ollama)"), ("chat", "talk to one model")):
        cmd = sub.add_parser(name, help=help_)
        cmd.add_argument(
            "model", nargs="?" if name == "pull" else None, help="catalogue id or ollama:<name>"
        )
        if name == "pull":
            cmd.add_argument(
                "--assigned", action="store_true", help="every Ollama model this device uses"
            )
        cmd.add_argument("--base-url", help="the runtime's URL, instead of this device's config")
        if name == "chat":
            cmd.add_argument("--no-system", action="store_true", help="skip Jarvis's system prompt")
            cmd.add_argument("--think", action="store_true", help=THINK_HELP)
    bench = sub.add_parser("bench", help="compare models on the Jarvis prompt set")
    bench.add_argument("models", nargs="+", help="catalogue ids")
    bench.add_argument("--runs", type=int, default=1, help="runs per prompt (default 1)")
    bench.add_argument("--prompts", help="a TOML prompt file instead of the built-in set")
    bench.add_argument("--markdown", action="store_true", help="full report with the answers")
    bench.add_argument("--base-url", help="the runtime's URL, instead of this device's config")
    bench.add_argument("--no-system", action="store_true", help="skip Jarvis's system prompt")
    bench.add_argument("--think", action="store_true", help=THINK_HELP)
    bench.add_argument(
        "--warm", action="store_true", help="don't unload the model first (LOAD is then ~0)"
    )
    return p


def main(
    argv: list[str] | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    factory: ClientFactory = default_client,
    stdin: TextIO = sys.stdin,
    out: TextIO = sys.stdout,
) -> int:
    args = parser().parse_args(argv)
    try:
        config: JarvisConfig | None = load_config(os.environ if environ is None else environ)
        problems: list[str] = []
    except ConfigError as exc:
        config, problems = None, exc.problems
    try:
        match args.command:
            case "list":
                return cmd_list(config, problems, out)
            case "pull":
                return asyncio.run(cmd_pull(args, config, factory, out))
            case "chat":
                return asyncio.run(cmd_chat(args, config, factory, stdin, out))
            case _:
                return asyncio.run(cmd_bench(args, config, factory, out))
    except (UsageError, ProbeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
