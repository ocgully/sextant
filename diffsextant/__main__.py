"""Allow `python -m sextant`."""
import sys
from diffsextant.cli import main

if __name__ == "__main__":
    sys.exit(main())
