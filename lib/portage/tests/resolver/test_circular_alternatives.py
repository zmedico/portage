# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class CircularAlternativesTestCase(TestCase):
    def testAnyOfAlternative(self):
        """
        A || ( ) choice that does not close the cycle is selected, even
        though it is not the first one (bug 515630).
        """
        ebuilds = {
            "dev-libs/A-1": {"EAPI": "8", "DEPEND": "|| ( dev-libs/B dev-libs/C )"},
            "dev-libs/B-1": {"EAPI": "8", "DEPEND": "dev-libs/A"},
            "dev-libs/C-1": {"EAPI": "8"},
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                success=True,
                mergelist=["dev-libs/C-1", "dev-libs/A-1"],
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testOlderVersion(self):
        """
        An older version whose dependencies do not close the cycle is
        selected (bug 407351).
        """
        ebuilds = {
            "dev-libs/A-1": {"EAPI": "8"},
            "dev-libs/A-2": {"EAPI": "8", "DEPEND": "dev-libs/B"},
            "dev-libs/B-1": {"EAPI": "8", "DEPEND": "dev-libs/A"},
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/B"],
                success=True,
                mergelist=["dev-libs/A-1", "dev-libs/B-1"],
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testNoDowngradeOfInstalled(self):
        """
        The older version is not used when it would downgrade what is
        already installed.
        """
        ebuilds = {
            "dev-libs/A-1": {"EAPI": "8"},
            "dev-libs/A-2": {"EAPI": "8", "DEPEND": "dev-libs/B"},
            "dev-libs/B-1": {"EAPI": "8", "DEPEND": "dev-libs/A"},
        }

        installed = {
            "dev-libs/A-2": {"EAPI": "8", "DEPEND": "dev-libs/B"},
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/B"],
                success=True,
                mergelist=["dev-libs/B-1"],
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
