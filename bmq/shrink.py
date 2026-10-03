"""Greedy, constraint-preserving row minimization of a counterexample."""

from collections.abc import Callable
from contextlib import closing
from copy import deepcopy

from bmq.db import LoadError, TABLES, build_db


def shrink(dataset, still_fails: Callable[[dict], bool]) -> dict[str, list[list]]:
    """Return a row-minimal dataset, not a guarantee of the global smallest set.

    The predicate should return False when the learner errors on a candidate.
    Validation connections are closed before the predicate builds its own DB.
    """
    current = deepcopy(dataset)
    changed = True
    while changed:
        changed = False
        for table in reversed(TABLES):
            for index in range(len(current[table]) - 1, -1, -1):
                candidate = deepcopy(current)
                del candidate[table][index]
                try:
                    with closing(build_db(candidate)):
                        pass
                except LoadError:
                    continue
                if still_fails(candidate):
                    current = candidate
                    changed = True
    return current
