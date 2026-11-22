"""Suite 2 entry point for the frozen DataHub staggered process pool."""

from pathlib import Path
import sys

from bench import egpot_suite2_locked as suite
from bench.results import datahub_stagger_1cf9dce0 as stagger

if __name__ == "__main__":
    phase = sys.argv[sys.argv.index("--phase") + 1]
    checkpoint = Path(sys.argv[sys.argv.index("--checkpoint") + 1])
    stagger.PLAN = suite.PHASES[phase][2]
    if "--resume" in sys.argv:
        stagger.inspect_snapshot(checkpoint)
    suite.main(pool=stagger.StaggeredPool)
