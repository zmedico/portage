# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class CycleBreakTestCase(TestCase):
    """
    With --cycle-break=y, a cycle that cannot be solved otherwise is
    broken by building one of the packages twice: first with the USE
    flag that closes the cycle disabled, and then as requested.
    """

    def testFreetypeHarfbuzz(self):
        ebuilds = {
            "media-libs/freetype-1": {
                "DEPEND": "harfbuzz? ( media-libs/harfbuzz )",
                "IUSE": "+harfbuzz",
                "EAPI": "8",
            },
            "media-libs/harfbuzz-1": {
                "DEPEND": "media-libs/freetype",
                "EAPI": "8",
            },
        }

        # The user asked for USE=harfbuzz, so the cycle cannot be solved
        # with a USE change.
        user_config = {"make.conf": ('USE="harfbuzz"',)}

        test_cases = (
            ResolverPlaygroundTestCase(
                ["media-libs/harfbuzz"],
                options={"--cycle-break": "y"},
                success=True,
                mergelist=[
                    "[cycle-break]media-libs/freetype-1",
                    "media-libs/harfbuzz-1",
                    "media-libs/freetype-1",
                ],
            ),
            # Disabled by default.
            ResolverPlaygroundTestCase(
                ["media-libs/harfbuzz"],
                success=False,
                circular_dependency_solutions={
                    "media-libs/harfbuzz-1": frozenset(
                        [frozenset([("harfbuzz", False)])]
                    )
                },
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds, user_config=user_config)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testRustSystemBootstrap(self):
        """
        dev-lang/rust with USE=system-bootstrap needs an already
        installed rust to build. Building it once without the flag
        provides one (bug 888177).
        """
        ebuilds = {
            "dev-lang/rust-2": {
                "BDEPEND": "system-bootstrap? ( dev-lang/rust )",
                "IUSE": "+system-bootstrap",
                "EAPI": "8",
            },
        }

        user_config = {"make.conf": ('USE="system-bootstrap"',)}

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-lang/rust"],
                options={"--cycle-break": "y"},
                success=True,
                mergelist=[
                    "[cycle-break]dev-lang/rust-2",
                    "dev-lang/rust-2",
                ],
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds, user_config=user_config)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testNoUnnecessaryCycleBreak(self):
        """
        --cycle-break=y does not change anything when there is no cycle.
        """
        ebuilds = {
            "dev-libs/A-1": {"DEPEND": "dev-libs/B", "EAPI": "8"},
            "dev-libs/B-1": {"EAPI": "8"},
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                options={"--cycle-break": "y"},
                success=True,
                mergelist=["dev-libs/B-1", "dev-libs/A-1"],
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
