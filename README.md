# mutate4bash

`mutate4bash` performs safe one-at-a-time mutation testing for Bash scripts. It ignores comments and quoted strings and checks each mutated file with `bash -n` before the test command.

## Install

```bash
pipx install git+https://github.com/lukasa1993/mutate4bash.git
```

## Run

```bash
mutate4bash --test-command "bats tests" --fail-on-survivors
```

The default manifest is `target/mutation/mutations.json`. Use `--list`, `--max-mutants`, and path fragments to control the run.
