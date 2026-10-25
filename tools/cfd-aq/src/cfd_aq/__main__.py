"""``python -m cfd_aq`` — always available, even when the console script is broken.

pip bakes ``sys.executable`` into the console script's shebang, which is wrong
wherever that path is not valid at run time: Python served from an
Apptainer/Singularity image through ``module load``, a moved virtualenv, or an
interpreter path longer than the kernel's 127-byte ``#!`` limit. ``python -m``
has none of those failure modes.
"""

from __future__ import annotations

import sys

from cfd_aq.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
