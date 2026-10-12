import os
import shutil
import subprocess
import sys

import pytest

from keysheet import __version__, cli

SHEET = """\
// a comment
# Shell
Ctrl-R            search history
$ du -sh * | sort -h  what takes space
no-description

# Git
$ git status      what changed
$ git add -f FILE  add an ignored file
"""


@pytest.fixture
def sheets(tmp_path, monkeypatch):
    d = tmp_path / "sheets"
    d.mkdir()
    (d / "a.sheet").write_text(SHEET)
    monkeypatch.setenv("KEYSHEET_PATH", str(d))
    monkeypatch.setenv("NO_COLOR", "1")
    return d


def test_parse_sections_keys_commands():
    entries = cli.parse(SHEET, default_section="file")
    assert [(e.section, e.key, e.is_cmd) for e in entries] == [
        ("Shell", "Ctrl-R", False),
        ("Shell", "du -sh * | sort -h", True),
        ("Shell", "no-description", False),
        ("Git", "git status", True),
        ("Git", "git add -f FILE", True),
    ]
    assert entries[0].desc == "search history"
    assert entries[2].desc == ""


def test_section_defaults_to_file_name():
    assert cli.parse("$ ls  list files", default_section="10-shell")[0].section == "10-shell"


def test_single_spaces_stay_in_the_key():
    (e,) = cli.parse("Ctrl-B arrow keys  move between panes")
    assert (e.key, e.desc) == ("Ctrl-B arrow keys", "move between panes")


def test_sheet_dirs_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("KEYSHEET_PATH", f"{tmp_path}/a::~/b")
    dirs = cli.sheet_dirs()
    assert dirs == [tmp_path / "a", cli.Path(os.path.expanduser("~/b"))]


def test_sheet_dirs_default(monkeypatch, tmp_path):
    monkeypatch.delenv("KEYSHEET_PATH", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert cli.sheet_dirs() == [tmp_path / "keysheet"]


def test_files_are_read_in_folder_then_name_order(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "2.sheet").write_text("two  2")
    (a / "1.sheet").write_text("one  1")
    (b / "0.sheet").write_text("zero  0")
    (a / "ignored.txt").write_text("nope  x")
    assert [e.key for e in cli.load([a, b])] == ["one", "two", "zero"]


def test_words_filter_all_words_any_case(sheets, capsys):
    assert cli.main(["GIT", "ignored"]) == 0
    out = capsys.readouterr().out
    assert "git add -f FILE" in out
    assert "git status" not in out


def test_no_match_exits_1(sheets, capsys):
    assert cli.main(["nothing-like-this"]) == 1
    assert "Nothing matches" in capsys.readouterr().err


def test_all_groups_by_section_without_colour(sheets, capsys):
    assert cli.main(["--all"]) == 0
    out = capsys.readouterr().out
    assert "\033[" not in out
    assert out.index("Shell") < out.index("Ctrl-R") < out.index("Git") < out.index("git status")


def test_no_sheets_explains_how_to_start(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("KEYSHEET_PATH", str(tmp_path / "empty"))
    assert cli.main([]) == 1
    assert "keysheet --examples" in capsys.readouterr().err


def test_examples_copy_without_overwriting(tmp_path, capsys):
    target = tmp_path / "new"
    assert cli.copy_examples(target) == 3
    (target / "10-shell.sheet").write_text("mine  kept")
    assert cli.copy_examples(target) == 0
    assert (target / "10-shell.sheet").read_text() == "mine  kept"
    assert all(cli.parse(f.read_text()) for f in target.glob("*.sheet"))


@pytest.mark.parametrize("shell", ["zsh", "bash"])
def test_init_defines_the_named_function(shell, capsys):
    assert cli.main(["--init", shell, "--name", "cheat"]) == 0
    out = capsys.readouterr().out
    assert "cheat() {" in out and "keysheet --pick" in out


def test_init_rejects_bad_names(capsys):
    assert cli.main(["--init", "zsh", "--name", "rm -rf"]) == 2


@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh not installed")
def test_zsh_init_is_valid_zsh():
    code = cli.init_code("zsh", "help")
    assert subprocess.run(["zsh", "-n", "-c", code]).returncode == 0


@pytest.mark.skipif(not shutil.which("bash"), reason="bash not installed")
def test_bash_init_is_valid_bash():
    assert subprocess.run(["bash", "-n", "-c", cli.init_code("bash", "help")]).returncode == 0


def test_command_words_skips_prefixes():
    assert cli.command_words("sudo bash ~/x.sh")[0] == "bash"
    assert cli.command_words("SKIP=1 git commit")[0] == "git"
    assert cli.command_words("cd ~/dir && docker compose up -d")[:2] == ["docker", "compose"]


def test_local_paths_ignore_remote_and_placeholders():
    assert cli.local_paths(["ssh", "host", "ls", "/srv"]) == []
    assert cli.local_paths(["ssh", "host", "bash", "<", "~/t.sh"]) == ["~/t.sh"]
    assert cli.local_paths(["cat", "~/dir/FILE", "/etc/*.conf", "/etc/hosts"]) == ["/etc/hosts"]


def test_check_reports_missing_commands_and_paths(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SHELL", "/bin/sh")  # plain PATH lookup
    entries = cli.parse(
        f"$ ls {tmp_path}  fine\n$ no-such-tool-xyz  gone\n$ cat {tmp_path}/missing  gone too"
    )
    assert cli.check(entries) == 1
    out = capsys.readouterr().out
    assert "no such command: no-such-tool-xyz" in out
    assert f"no such path: {tmp_path}/missing" in out
    assert "2 problem(s) in 3 commands." in out


@pytest.mark.skipif(not shutil.which("fzf"), reason="fzf not installed")
def test_pick_prints_only_the_command(sheets, monkeypatch, capsys):
    monkeypatch.setenv("FZF_DEFAULT_OPTS", "--filter=status")  # non-interactive fzf
    assert cli.main(["--pick"]) == 0
    assert capsys.readouterr().out == "git status\n"


@pytest.mark.skipif(not shutil.which("fzf"), reason="fzf not installed")
def test_picking_a_key_shows_it_on_stderr(sheets, monkeypatch, capsys):
    monkeypatch.setenv("FZF_DEFAULT_OPTS", "--filter=Ctrl-R")
    assert cli.main(["--pick"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Ctrl-R  search history" in captured.err


def test_module_runs_and_reports_version():
    r = subprocess.run(
        [sys.executable, "-m", "keysheet", "--version"], capture_output=True, text=True
    )
    assert r.stdout.strip() == f"keysheet {__version__}"
