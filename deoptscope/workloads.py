"""Real-library workloads used for the census.

Each factory builds its inputs outside the measured call and returns a
zero-argument callable.  These are ordinary usage patterns, not harnesses:
Jinja2 renders a 200-row HTML table, markdown-it parses a real Markdown
document, and Click parses a realistic argv.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

CORPUS = Path(__file__).resolve().parent.parent / "experiments" / "corpus.md"

TEMPLATE = """<table>
{% for row in rows %}
  <tr class="{{ 'odd' if loop.index is odd else 'even' }}">
    <td>{{ row.name|upper }}</td>
    <td>{{ "%.2f"|format(row.score) }}</td>
    <td>{{ row.tags|join(", ") }}</td>
  </tr>
{% endfor %}
</table>
"""

ROWS = [
    {
        "name": f"item-{i}",
        "score": (i * 37 % 1000) / 10.0,
        "tags": [f"t{(i + k) % 7}" for k in range(3)],
    }
    for i in range(200)
]


def jinja_render() -> Callable[[], Any]:
    from jinja2 import Environment

    env = Environment(autoescape=False, trim_blocks=True)
    template = env.from_string(TEMPLATE)

    def run() -> str:
        return template.render(rows=ROWS)

    return run


def markdown_parse() -> Callable[[], Any]:
    from markdown_it import MarkdownIt

    text = CORPUS.read_text(encoding="utf-8")
    md = MarkdownIt("commonmark")

    def run() -> str:
        return md.render(text)

    return run


def click_invoke() -> Callable[[], Any]:
    import click
    from click.testing import CliRunner

    @click.command()
    @click.option("--count", type=int, default=3)
    @click.option("--name", required=True)
    @click.option("--tag", multiple=True)
    @click.option("--verbose", is_flag=True)
    @click.option("--ratio", type=float, default=0.5)
    @click.argument("paths", nargs=-1)
    def cli(count: int, name: str, tag: tuple[str, ...], verbose: bool, ratio: float, paths: tuple[str, ...]) -> None:
        click.echo(json.dumps({"count": count, "name": name, "tags": list(tag), "verbose": verbose, "ratio": ratio, "paths": list(paths)}))

    runner = CliRunner()
    argv = [
        "--count", "7",
        "--name", "release-candidate",
        "--tag", "fast", "--tag", "stable", "--tag", "verified",
        "--verbose",
        "--ratio", "0.125",
        "src/alpha.py", "src/beta.py", "docs/guide.md",
    ]

    def run() -> Any:
        return runner.invoke(cli, argv)

    return run


WORKLOADS: dict[str, Callable[[], Callable[[], Any]]] = {
    "jinja2_render": jinja_render,
    "markdown_parse": markdown_parse,
    "click_invoke": click_invoke,
}


def get(name: str) -> Callable[[], Any]:
    if name not in WORKLOADS:
        raise KeyError(f"unknown workload {name!r}; choose from {sorted(WORKLOADS)}")
    return WORKLOADS[name]()


def available() -> dict[str, bool]:
    out: dict[str, bool] = {}
    for name in WORKLOADS:
        try:
            get(name)
            out[name] = True
        except Exception:
            out[name] = False
    return out
