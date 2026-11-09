"""``python -m hebloc …`` = the ``hebloc`` command.

On Windows with Smart App Control, the unsigned launcher ``.venv\\Scripts\\hebloc.exe`` that uv
generates for every new environment can be blocked ("An Application Control policy has blocked
this file"); the signed python.org interpreter is not. ``uv run python -m hebloc`` always works (D-038).
"""

import sys

from hebloc.cli import main

sys.exit(main())
