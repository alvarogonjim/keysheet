# keysheet

Your own cheat sheet of **key shortcuts and commands**, searchable from the shell.

You set up aliases, tmux bindings, little scripts and tools, and a month later you can't
remember half of them. keysheet keeps them in plain-text sheets you write yourself, and finds
them when you need them:

```console
$ help tmux split
tmux: panes
  Ctrl-B %  split side by side
  Ctrl-B "  split top and bottom
```

Type `help` on its own to search everything with [fzf](https://github.com/junegunn/fzf):
pick a command and it lands on your prompt, ready to edit or run.

## Install

Needs Python 3.10 or newer, and fzf for the interactive search.

```sh
uv tool install git+https://github.com/alvarogonjim/keysheet
# or: pipx install git+https://github.com/alvarogonjim/keysheet
```

## Start

```sh
keysheet --examples                # copies three example sheets to ~/.config/keysheet
echo 'eval "$(keysheet --init zsh)"' >> ~/.zshrc     # or: --init bash >> ~/.bashrc
```

Open a new terminal and type `help`. Then make the sheets yours: `help --edit`, delete what
you already know, add what you keep forgetting.

## Use

| Command | What it does |
|---|---|
| `help` | search all sheets; Enter puts the command you pick on the prompt |
| `help WORD…` | print the entries that contain all the words (`help git branch`) |
| `help --all` | print every entry |
| `help --edit` | open the sheets in `$VISUAL` / `$EDITOR` |
| `help --check` | list commands and paths in the sheets that no longer exist |
| `keysheet --format` | the sheet format, in short |

`help` is a small shell function made by `keysheet --init`; the program itself is
`keysheet`, so everything above also works as `keysheet …`. Prefer another name? Use
`keysheet --init zsh --name cheat`.

In **zsh**, the command you pick appears on the prompt. In **bash**, it goes into your
history: press ↑ to get it. For the zsh behaviour in bash, bind the widget to a key:
`bind -x '"\C-g": _keysheet_widget'` (Ctrl-G). When `help` is the name in bash, bash's own
help is still there as `builtin help`.

## Sheets

Any `*.sheet` file in `~/.config/keysheet`. One entry per line, two columns separated by
**two or more spaces**:

```text
// a comment
# tmux: panes
Ctrl-B %                split side by side
$ tmux new -s NAME      start a session called NAME
```

- `# Section` starts a section (otherwise the file name is used).
- `$ ` marks a command: picking it puts it on your prompt. Without `$ ` an entry is a key
  or a note, shown but not inserted.
- Words in CAPITALS in a command are placeholders (`FILE`, `NAME`) to replace.
- Files are read in name order, so `10-shell.sheet` comes before `20-tmux.sheet`.

### Several folders

`KEYSHEET_PATH` lists the folders to read, separated by `:`. Keep general sheets in your
dotfiles and one machine's own tools next to that machine's config:

```sh
export KEYSHEET_PATH=~/.config/keysheet:~/server-config/keysheet
```

`help --edit` opens all of them and reminds you to commit the ones kept in git.

### Keeping them honest

`keysheet --check` runs every command's program through your shell (so aliases and
functions count) and checks the paths in it, and lists what no longer exists: the tool you
uninstalled, the script you moved. Paths in `ssh` commands are on the other machine and are
skipped.

## How it compares

- [navi](https://github.com/denisidoro/navi) is the closest: interactive cheat sheets with
  fzf and a shell widget, plus variables with suggestions and community repositories. Use it
  if you want those. keysheet is smaller: a two-column format you can read without the
  tool, key shortcuts as first-class entries, several folders merged, `--check`, and no
  dependencies besides Python and fzf.
- [cheat](https://github.com/cheat/cheat) and [tldr](https://github.com/tldr-pages/tldr)
  show examples for *other people's* commands. keysheet is for *your* setup.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
