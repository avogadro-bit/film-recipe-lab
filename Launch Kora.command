#!/bin/zsh
cd -- "${0:A:h}" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  print 'Install the project first as described in README.md (Python and the .venv environment).'
  read '?Press Enter to close.'
  exit 1
fi
./.venv/bin/python -m kora gui --port 8766
if (( $? != 0 )); then
  print '\nThe service did not start. Check the message above.'
  read '?Press Enter to close.'
fi
