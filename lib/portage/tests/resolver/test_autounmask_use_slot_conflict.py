# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class AutounmaskUseSlotConflictTestCase(TestCase):

	def testAutounmaskUseSlotConflict(self):

		ebuilds = {
			"sci-libs/K-1": {
				"IUSE": "+foo",
				"EAPI": 1
			},
			"sci-libs/L-1": {
				"DEPEND": "sci-libs/K[-foo]",
				"EAPI": 2
			},
			"sci-libs/M-1": {
				"DEPEND": "sci-libs/K[foo=]",
				"IUSE": "+foo",
				"EAPI": 2
			},
		}

		installed = {}

		test_cases = (
			ResolverPlaygroundTestCase(
				["sci-libs/L", "sci-libs/M"],
				#options={"--backtrack": 0},
				options={'--autounmask-backtrack': 'y'},
				success = False,
				#mergelist = [
				#	"sci-libs/L-1",
				#	"sci-libs/M-1",
				#	"sci-libs/K-1",
				#],
				#ignore_mergelist_order = True,
				#slot_collision_solutions = [
				#	{
				#		"sci-libs/K-1": {"foo": False},
				#		"sci-libs/M-1": {"foo": False}
				#	}
				#]
			),
		)

		playground = ResolverPlayground(
			ebuilds=ebuilds, installed=installed, debug=True)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success,
					True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
