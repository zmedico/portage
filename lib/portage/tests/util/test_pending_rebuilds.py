# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import collections
import tempfile

from portage.dep import Atom
from portage.tests import TestCase
from portage.util._pending_rebuilds import (
    add_pending_rebuild,
    get_pending_rebuilds,
    remove_pending_rebuild,
)

FakePackage = collections.namedtuple("FakePackage", ["cpv", "slot", "slot_atom"])


def _pkg(cpv, slot="0"):
    cp = cpv.rsplit("-", 1)[0]
    return FakePackage(cpv=cpv, slot=slot, slot_atom=Atom(f"{cp}:{slot}"))


class PendingRebuildsTestCase(TestCase):
    def testPendingRebuilds(self):
        freetype = _pkg("media-libs/freetype-2.13.3")
        rust = _pkg("dev-lang/rust-1.80.0")

        with tempfile.TemporaryDirectory() as eroot:
            self.assertEqual(get_pending_rebuilds(eroot), [])

            # Clearing a package that was never recorded is a no-op, so
            # that every merge can call it unconditionally.
            remove_pending_rebuild(eroot, freetype)
            self.assertEqual(get_pending_rebuilds(eroot), [])

            add_pending_rebuild(eroot, freetype)
            self.assertEqual(
                get_pending_rebuilds(eroot), ["=media-libs/freetype-2.13.3:0"]
            )

            # Recording the same package twice does not duplicate it.
            add_pending_rebuild(eroot, freetype)
            self.assertEqual(
                get_pending_rebuilds(eroot), ["=media-libs/freetype-2.13.3:0"]
            )

            add_pending_rebuild(eroot, rust)
            self.assertEqual(
                get_pending_rebuilds(eroot),
                ["=dev-lang/rust-1.80.0:0", "=media-libs/freetype-2.13.3:0"],
            )

            remove_pending_rebuild(eroot, freetype)
            self.assertEqual(get_pending_rebuilds(eroot), ["=dev-lang/rust-1.80.0:0"])

            remove_pending_rebuild(eroot, rust)
            self.assertEqual(get_pending_rebuilds(eroot), [])

    def testNewerVersionSettlesTheDebt(self):
        """
        The rebuild does not have to be the same version, as long as it
        is the same slot. A different slot is left alone.
        """
        with tempfile.TemporaryDirectory() as eroot:
            add_pending_rebuild(eroot, _pkg("dev-lang/rust-1.80.0"))
            add_pending_rebuild(eroot, _pkg("dev-lang/rust-1.81.0", slot="stable"))

            remove_pending_rebuild(eroot, _pkg("dev-lang/rust-1.82.0"))
            self.assertEqual(
                get_pending_rebuilds(eroot), ["=dev-lang/rust-1.81.0:stable"]
            )

            remove_pending_rebuild(eroot, _pkg("dev-lang/rust-1.82.0", slot="stable"))
            self.assertEqual(get_pending_rebuilds(eroot), [])
