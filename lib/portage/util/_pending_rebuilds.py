# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

"""
Bookkeeping for packages that have been installed with a reduced USE
configuration in order to break a circular dependency, and that still
have to be rebuilt with the requested configuration.

If the rebuild does not happen, because the build fails or the operation
is interrupted, the packages are still recorded here, so that the user
can be told about them.
"""

import errno

from portage import os
from portage.const import PENDING_REBUILDS_FILE
from portage.dep import Atom
from portage.exception import InvalidAtom
from portage.locks import lockfile, unlockfile
from portage.output import colorize
from portage.util import atomic_ofstream, ensure_dirs, grabfile, writemsg


def _path(eroot):
    return os.path.join(eroot, PENDING_REBUILDS_FILE)


def get_pending_rebuilds(eroot):
    """
    Return the list of atoms that still have to be rebuilt.
    """
    return grabfile(_path(eroot))


def _write(eroot, atoms):
    path = _path(eroot)
    if not atoms:
        try:
            os.unlink(path)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
        return

    ensure_dirs(os.path.dirname(path))
    f = atomic_ofstream(path)
    for atom in sorted(set(atoms)):
        f.write(f"{atom}\n")
    f.close()


def _same_slot(recorded, slot_atom):
    """
    Return True if the recorded atom names a version of the slot that
    slot_atom refers to.
    """
    try:
        recorded = Atom(recorded)
    except InvalidAtom:
        return False
    return recorded.cp == slot_atom.cp and recorded.slot == slot_atom.slot


def _update(eroot, add=None, remove=None):
    """
    Add or remove an atom, with the file locked so that concurrent
    emerges do not lose each other's entries.
    """
    path = _path(eroot)
    ensure_dirs(os.path.dirname(path))
    lock = lockfile(path, wantnewlockfile=True)
    try:
        atoms = grabfile(path)
        if remove is not None:
            atoms = [x for x in atoms if not _same_slot(x, remove)]
        if add is not None:
            atoms.append(add)
        _write(eroot, atoms)
    finally:
        unlockfile(lock)


def add_pending_rebuild(eroot, pkg):
    """
    Record that pkg has been installed with a reduced USE configuration
    and still needs to be rebuilt.
    """
    try:
        _update(eroot, add=f"={pkg.cpv}:{pkg.slot}")
    except OSError as e:
        writemsg(f"!!! Failed to record pending rebuild: {e}\n", noiselevel=-1)


def remove_pending_rebuild(eroot, pkg):
    """
    Record that pkg has been merged with the requested configuration.
    Every recorded version of its slot is dropped, since a newer version
    settles the debt as well.
    """
    if not os.path.exists(_path(eroot)):
        # The common case, so avoid taking a lock for nothing.
        return
    try:
        _update(eroot, remove=pkg.slot_atom)
    except OSError as e:
        writemsg(f"!!! Failed to clear pending rebuild: {e}\n", noiselevel=-1)


def display_pending_rebuilds(eroot):
    """
    Warn about packages that are still installed with a reduced USE
    configuration. Returns True if anything was displayed.
    """
    atoms = get_pending_rebuilds(eroot)
    if not atoms:
        return False

    writemsg(
        "\n"
        + colorize("WARN", "!!!")
        + " The following packages were installed with a reduced USE\n"
        + colorize("WARN", "!!!")
        + " configuration, in order to break a circular dependency, and\n"
        + colorize("WARN", "!!!")
        + " still have to be rebuilt:\n",
        noiselevel=-1,
    )
    for atom in atoms:
        writemsg(f"    {atom}\n", noiselevel=-1)
    return True
