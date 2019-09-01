# Copyright 2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class AutounmaskUseConflictTestCase(TestCase):

	def testAutounmaskUseConflict(self):
		ebuilds = {
			'dev-libs/A-1': {
				'EAPI': '7',
				'RDEPEND': 'dev-libs/B dev-libs/C',
			},
			'dev-libs/B-1': {
				'EAPI': '7',
				'RDEPEND': 'dev-libs/D[foo]',
			},
			'dev-libs/C-1': {
				'EAPI': '7',
				'RDEPEND': 'dev-libs/D[-foo]',
			},
			'dev-libs/D-1': {
				'EAPI': '7',
				'IUSE': 'foo',
			},
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				['dev-libs/A'],
				options={"--autounmask": "n"},
				success=False,
				mergelist=None
			),
			ResolverPlaygroundTestCase(
				['dev-libs/A'],
				options={"--autounmask": "y"},
				success=False,
				ambiguous_merge_order = True,
				mergelist=[
					'dev-libs/D-1',
					('dev-libs/B-1', 'dev-libs/C-1'),
					'dev-libs/A-1',
				],
				use_changes={'dev-libs/D-1': {'foo': True}},
			),
			ResolverPlaygroundTestCase(
				['dev-libs/A'],
				options={"--autounmask": "y", "--autounmask-backtrack": "y"},
				success=False,
				mergelist=None
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, debug=False)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
