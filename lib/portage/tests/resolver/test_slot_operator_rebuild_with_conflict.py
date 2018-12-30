# Copyright 2014-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SlotOperatorRebuildWithConflictTestCase(TestCase):

	def testSlotOperatorRebuildWithConflict(self):
		debug = False
		self.todo = True

		ebuilds = {
			"app-misc/A-1" : {
				"EAPI": "5",
				"RDEPEND": "|| ( app-misc/B app-misc/C )"
			},

			"app-misc/C-0" : {
				"EAPI": "5",
			},

			"app-misc/E-1" : {
				"EAPI": "5",
				"SLOT": "0/1",
			},

			"app-misc/E-2" : {
				"EAPI": "5",
				"SLOT": "0/2",
			},
		}

		binpkgs = {
			"app-misc/E-0" : {
				"EAPI": "5",
				"SLOT": "0/1",
			},
		}

		installed = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"RDEPEND": "|| ( app-misc/B app-misc/C )"
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"RDEPEND": "app-misc/E:0/1="
			},

			"app-misc/E-1" : {
				"EAPI": "5",
				"SLOT": "0/1",
			},

		}

		world = ["app-misc/A"]

		test_cases = (

			ResolverPlaygroundTestCase(
				[">=app-misc/E-2"],
				options = {"--dynamic-deps": "n", "--backtrack": 10, "--update": True, "--deep": True},
				success = True,
				ambiguous_merge_order = True,
				mergelist = [('app-misc/E-2', 'app-misc/C-0')]
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, binpkgs=binpkgs,
			installed=installed, world=world, debug=debug)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
