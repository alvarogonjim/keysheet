# keysheet: your own cheat sheet of key shortcuts and commands, searchable from the shell.
# Copyright (C) 2026 Alvaro Gonzalez-Jimenez
#
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, either version 3
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with this program.
# If not, see <https://www.gnu.org/licenses/>.
"""Search your own cheat sheets of key shortcuts and commands.

Sheets are plain-text *.sheet files in the folders listed in $KEYSHEET_PATH (separated by
":"); by default ~/.config/keysheet. One entry per line:

  # Section name
  KEY                 what it does
  $ COMMAND           what it does     ("$ " marks a command you can put on your prompt)
  // a comment

The two columns are separated by two or more spaces. In commands, words in CAPITALS are
placeholders to replace (FILE, NAME…).
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from . import __version__

SEP = re.compile(r"\s{2,}")
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
KEY_WIDTH_MAX = 38


@dataclass
class Entry:
    section: str
    key: str
    desc: str
    is_cmd: bool = False

    def matches(self, words: list[str]) -> bool:
        text = f"{self.section} {self.key} {self.desc}".lower()
        return all(w.lower() in text for w in words)


# --- Reading sheets


def sheet_dirs() -> list[Path]:
    env = os.environ.get("KEYSHEET_PATH")
    if env:
        return [Path(os.path.expandvars(os.path.expanduser(p))) for p in env.split(":") if p]
    config = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return [Path(config) / "keysheet"]


def sheet_files(dirs: list[Path]) -> list[Path]:
    return [f for d in dirs if d.is_dir() for f in sorted(d.glob("*.sheet"))]


def parse(text: str, default_section: str = "") -> list[Entry]:
    entries, section = [], default_section
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("# "):
            section = line[2:].strip()
            continue
        key, desc = ([*SEP.split(line, maxsplit=1), ""])[:2]
        if key.startswith("$ "):
            entries.append(Entry(section, key[2:].strip(), desc, is_cmd=True))
        else:
            entries.append(Entry(section, key, desc))
    return entries


def load(dirs: list[Path]) -> list[Entry]:
    entries = []
    for f in sheet_files(dirs):
        entries += parse(f.read_text(encoding="utf-8"), default_section=f.stem)
    return entries


# --- Showing them


class Style:
    def __init__(self, enabled: bool):
        on = enabled and not os.environ.get("NO_COLOR")
        self.bold, self.dim, self.reset = ("\033[1m", "\033[2m", "\033[0m") if on else ("",) * 3
        self.section, self.key, self.cmd = ("\033[36m", "\033[33m", "\033[32m") if on else ("",) * 3

    def entry_key(self, e: Entry) -> str:
        return f"{self.cmd if e.is_cmd else self.key}{e.key}{self.reset}"


def key_width(entries: list[Entry]) -> int:
    return min(max((len(e.key) for e in entries), default=10), KEY_WIDTH_MAX)


def render(entries: list[Entry], style: Style) -> str:
    kw, out, last = key_width(entries), [], None
    for e in entries:
        if e.section != last:
            if last is not None:
                out.append("")
            out.append(f"{style.bold}{style.section}{e.section}{style.reset}")
            last = e.section
        pad = " " * max(kw - len(e.key), 0)
        out.append(f"  {style.entry_key(e)}{pad}  {e.desc}".rstrip())
    return "\n".join(out) + "\n"


def show(entries: list[Entry]) -> None:
    tty = sys.stdout.isatty()
    style = Style(tty)
    text = render(entries, style)
    if tty and style.reset:
        legend = "yellow: keys · green: commands (CAPITALS are placeholders)"
        text += f"\n{style.dim}{legend}{style.reset}\n"
    rows = shutil.get_terminal_size((80, 24)).lines
    if tty and text.count("\n") > rows - 2 and shutil.which("less"):
        subprocess.run(["less", "-R", "-F", "-X"], input=text, text=True, check=False)
    else:
        sys.stdout.write(text)


def pick(entries: list[Entry], query: str = "") -> Entry | None:
    """Let the user choose an entry with fzf. Returns it, or None if they pressed Esc."""
    style = Style(True)
    sw = min(max(len(e.section) for e in entries), 24)
    kw = key_width(entries)
    lines = []
    for i, e in enumerate(entries):
        pad = " " * max(kw - len(e.key), 0)
        section = f"{e.section[:sw]:<{sw}}"
        lines.append(f"{i}\t{style.dim}{section}{style.reset}  {style.entry_key(e)}{pad}  {e.desc}")
    header = "Enter: put the command on your prompt (CAPITALS are placeholders) · Esc: close"
    fzf = [
        "fzf", "--ansi", "--layout=reverse", "--height=90%", "--border", "--info=inline",
        "--prompt=keysheet> ", f"--header={header}", "--delimiter=\t", "--with-nth=2..",
        "--tiebreak=index", f"--query={query}",
    ]  # fmt: skip
    p = subprocess.run(fzf, input="\n".join(lines), text=True, stdout=subprocess.PIPE, check=False)
    if p.returncode != 0 or not p.stdout.strip():
        return None
    return entries[int(p.stdout.split("\t", 1)[0])]


# --- --check: entries that point at things that don't exist


def command_words(cmd: str) -> list[str]:
    try:
        words = shlex.split(cmd)
    except ValueError:
        words = cmd.split()
    if "&&" in words:  # "cd DIR && COMMAND": check the last command
        words = words[len(words) - words[::-1].index("&&") :]
    while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):  # VAR=value prefixes
        words = words[1:]
    if words and words[0] in ("sudo", "doas", "env", "nohup", "time"):
        words = words[1:]
    return words


def local_paths(words: list[str]) -> list[str]:
    if words and words[0] == "ssh":  # paths are on the other machine, except after "<"
        words = words[words.index("<") + 1 :] if "<" in words else []
    return [
        w
        for w in words
        if w.startswith(("~/", "/")) and not re.search(r"[A-Z]{2,}|[*?…]", w)  # no placeholders
    ]


def missing_commands(names: list[str]) -> set[str]:
    """Names unknown to the user's shell, which also knows their aliases and functions."""
    if not names:
        return set()
    shell = Path(os.environ.get("SHELL", "")).name
    mark = "KEYSHEET-MISSING:"
    scripts = {
        "zsh": f'for w in "$@"; do whence -w -- "$w" >/dev/null || print -r -- "{mark}$w"; done',
        "bash": f'for w in "$@"; do type -t -- "$w" >/dev/null || printf "%s\\n" "{mark}$w"; done',
    }
    if shell in scripts and shutil.which(shell):
        try:
            r = subprocess.run(
                [shell, "-ic", scripts[shell], shell, *names],
                capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
            )  # fmt: skip
            return {line[len(mark) :] for line in r.stdout.splitlines() if line.startswith(mark)}
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {n for n in names if not shutil.which(n)}


def check(entries: list[Entry]) -> int:
    problems, by_name = [], {}
    commands = [e for e in entries if e.is_cmd]
    for e in commands:
        words = command_words(e.key)
        for p in local_paths(words):
            if not Path(os.path.expanduser(p)).exists():
                problems.append((e, f"no such path: {p}"))
        if words and not words[0].startswith(("~", "/", ".")):
            by_name.setdefault(words[0], []).append(e)
    for name in sorted(missing_commands(sorted(by_name))):
        problems += [(e, f"no such command: {name}") for e in by_name[name]]
    for e, why in problems:
        print(f"{e.section}: {e.key}\n    {why}")
    print(f"{len(problems)} problem(s) in {len(commands)} commands.")
    return 1 if problems else 0


# --- Setting things up


def init_code(shell: str, name: str) -> str:
    if shell == "zsh":
        return f"""\
# keysheet: `{name}` searches your cheat sheets and puts the command you pick on the prompt;
# `{name} WORD…` prints the entries that match.
{name}() {{
	if (( $# )); then keysheet "$@"; return; fi
	local c
	c=$(keysheet --pick) && [[ -n $c ]] && print -z -- "$c"
}}
"""
    if shell == "bash":
        return f"""\
# keysheet: `{name}` searches your cheat sheets; the command you pick goes into your history,
# so ↑ brings it to the prompt. `{name} WORD…` prints the entries that match.
# (If {name} is "help", bash's own help is still there as `builtin help`.)
{name}() {{
	if (( $# )); then keysheet "$@"; return; fi
	local c
	c=$(keysheet --pick) && [[ -n $c ]] && history -s -- "$c" && printf '↑ for: %s\\n' "$c"
}}
# To get the pick straight onto the prompt with a key instead, e.g. Ctrl-G:
#   bind -x '"\\C-g": _keysheet_widget'
_keysheet_widget() {{
	local c
	c=$(keysheet --pick) && [[ -n $c ]] && READLINE_LINE=$c && READLINE_POINT=${{#c}}
}}
"""
    raise ValueError(shell)


def copy_examples(target: Path) -> int:
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src in sorted(resources.files("keysheet").joinpath("examples").iterdir()):
        if not src.name.endswith(".sheet"):
            continue
        dst = target / src.name
        if dst.exists():
            print(f"kept     {dst} (already there)")
            continue
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"copied   {dst}")
        copied += 1
    return copied


def edit(dirs: list[Path]) -> int:
    files = sheet_files(dirs)
    if not files:
        print(f"No sheets yet. Start with: keysheet --examples {dirs[0]}", file=sys.stderr)
        return 1
    editor = shlex.split(os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi")
    subprocess.run([*editor, *map(str, files)], check=False)
    if not shutil.which("git"):
        return 0
    for d in dirs:  # remind to commit sheets kept in git (dotfiles…)
        top = subprocess.run(
            ["git", "-C", str(d), "rev-parse", "--show-toplevel"], capture_output=True, text=True
        )
        if top.returncode != 0:
            continue
        dirty = subprocess.run(
            ["git", "-C", str(d), "status", "--porcelain", "--", "."],
            capture_output=True,
            text=True,
        ).stdout.strip()
        if dirty:
            print(f"Changed sheets in {top.stdout.strip()}: commit them to keep them.")
    return 0


# --- Command line


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="keysheet",
        description="Search your own cheat sheets of key shortcuts and commands. With no "
        "arguments: search them all with fzf and print the command you pick.",
        epilog="Sheets: *.sheet files in $KEYSHEET_PATH (folders separated by ':'; default "
        "~/.config/keysheet). Format: see `keysheet --format`.",
    )
    p.add_argument("words", nargs="*", help="print the entries that contain all these words")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="print every entry")
    g.add_argument("--pick", action="store_true", help="search with fzf; print only the command")
    g.add_argument("--edit", action="store_true", help="open the sheets in $VISUAL / $EDITOR")
    g.add_argument("--check", action="store_true", help="list commands and paths that don't exist")
    g.add_argument(
        "--examples",
        nargs="?",
        const="",
        metavar="DIR",
        help="copy the example sheets into DIR (default: the first sheet folder)",
    )
    g.add_argument(
        "--init", choices=["zsh", "bash"], help="print shell code to eval in your rc file"
    )
    g.add_argument("--format", action="store_true", help="explain the sheet format")
    g.add_argument("--version", action="version", version=f"keysheet {__version__}")
    p.add_argument("--name", default="help", help="with --init: the command's name (default: help)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dirs = sheet_dirs()

    if args.format:
        print(__doc__.split("\n\n", 1)[1].strip())
        return 0
    if args.init:
        if not NAME.match(args.name):
            print(f"keysheet: not a usable command name: {args.name}", file=sys.stderr)
            return 2
        sys.stdout.write(init_code(args.init, args.name))
        return 0
    if args.examples is not None:
        copy_examples(Path(os.path.expanduser(args.examples)) if args.examples else dirs[0])
        return 0
    if args.edit:
        return edit(dirs)

    entries = load(dirs)
    if not entries:
        where = ", ".join(map(str, dirs))
        print(f"No sheets in {where}. Start with: keysheet --examples", file=sys.stderr)
        return 1
    if args.check:
        return check(entries)
    if args.all:
        show(entries)
        return 0
    if args.words:
        hits = [e for e in entries if e.matches(args.words)]
        if not hits:
            print(f"Nothing matches: {' '.join(args.words)}", file=sys.stderr)
            return 1
        show(hits)
        return 0
    if not shutil.which("fzf") or not (args.pick or sys.stdin.isatty()):
        if args.pick:
            print(
                "keysheet: searching needs fzf (https://github.com/junegunn/fzf)", file=sys.stderr
            )
            return 1
        show(entries)
        return 0
    e = pick(entries)
    if e is None:
        return 0
    if e.is_cmd:
        print(e.key)
    else:
        print(f"{e.key}  {e.desc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
