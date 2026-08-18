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
