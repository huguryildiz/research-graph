"""Run a command with a real terminal on its stdin, typing scripted answers.

`rgraph decide` refuses a pipe on purpose: `yes y | rgraph decide H1` would
answer a human gate in order without anybody reading anything. CI still has to
prove that the newcomer path reaches a green gate, so this opens a terminal and
types what a person sitting at one would type.

It is a rig for this repository's own workflow test, not a supported way to run
`decide`. Nothing here ships: it lives outside the package and outside the
wheel, and the refusal it works around is asserted in the same CI step.

    python .github/at_a_terminal.py y y -- rgraph decide H1 --as "CI Smoke Test"

A command that asks more than it was given gets end-of-input rather than a wait,
and the timeout is the backstop, so this fails a job instead of hanging one.
"""

from __future__ import annotations

import os
import subprocess
import sys

TIMEOUT = 120
END_OF_INPUT = b"\x04"  # what Ctrl-D sends; every prompt here reads it as a stop


def main(argv: list[str]) -> int:
    if "--" not in argv or not argv[argv.index("--") + 1:]:
        print(f"usage: {sys.argv[0]} ANSWER... -- COMMAND...", file=sys.stderr)
        return 2
    split = argv.index("--")
    typed = "".join(f"{answer}\n" for answer in argv[:split]).encode()
    command = argv[split + 1:]

    master, slave = os.openpty()
    try:
        # Only stdin is the terminal. Output stays on the inherited streams, so
        # it reaches the CI log in order and no buffer of ours can fill up.
        with subprocess.Popen(command, stdin=slave) as process:
            os.close(slave)
            slave = -1
            os.write(master, typed + END_OF_INPUT)
            try:
                return process.wait(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                process.kill()
                print(
                    f"{sys.argv[0]}: {command[0]} asked for more than it was given",
                    file=sys.stderr,
                )
                return 1
    finally:
        if slave != -1:
            os.close(slave)
        os.close(master)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
