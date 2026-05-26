#!/usr/bin/env python3
import sys
import os

# Allow running directly from the src/ directory or the project root
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from application import ClassevivaApplication


def main() -> int:
    app = ClassevivaApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
