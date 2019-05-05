# Copyright 2012-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase)


class AutounmaskUseConflictTestCase(TestCase):

	def testUseConflict(self):

		ebuilds = {
			"dev-libs/libxml2-2.8.0": {
				"EAPI": "2",
				"IUSE": "+icu",
				"SLOT": "2",
			},
			"x11-libs/qt-webkit-4.8.2": {
				"EAPI": "2",
				"IUSE": "icu",
				"RDEPEND" : "dev-libs/libxml2:2[!icu?]",
			},
			"www-client/chromium-19.0.1084.52": {
				"EAPI": "2",
				"RDEPEND" : "dev-libs/libxml2[icu]",
			}
		}

		installed = {}

		world = []

		test_cases = (

			ResolverPlaygroundTestCase(
				["x11-libs/qt-webkit", "www-client/chromium"],
				options = {
					'--complete-graph-if-new-use' : 'y',
					'--autounmask-backtrack': 'y',
				},
				ambiguous_merge_order = True,
				mergelist = ["dev-libs/libxml2-2.8.0", ("x11-libs/qt-webkit-4.8.2", "www-client/chromium-19.0.1084.52")],
				use_changes = {"dev-libs/libxml2-2.8.0": {"icu": True }},
				success = False,
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=True)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
