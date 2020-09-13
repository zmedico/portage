# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SlotOperatorRebuildZstandardTestCase(TestCase):

	def testSlotOperatorRebuildZstandard(self):

		ebuilds = {

			'dev-python/cffi-1.14.2' : {
				'EAPI': '7',
				'SLOT': '0/1.14.2',
			},

			'dev-python/cffi-1.14.1' : {
				'EAPI': '7',
				'SLOT': '0/1.14.1',
			},

			'dev-python/zstandard-0.14.0' : {
				'EAPI': '7',
				'RDEPEND': 'dev-python/cffi:=',
			},

			'dev-vcs/mercurial-5.5.1' : {
				'EAPI': '7',
				'RDEPEND': 'dev-python/zstandard',
			},

		}

		installed = {

			'dev-python/cffi-1.14.1' : {
				'EAPI': '7',
				'SLOT': '0/1.14.1',
			},

			'dev-python/zstandard-0.14.0' : {
				'EAPI': '7',
				'RDEPEND': 'dev-python/cffi:0/1.14.1=',
			},

			'dev-vcs/mercurial-5.5.1' : {
				'EAPI': '7',
				'RDEPEND': 'dev-python/zstandard',
			},
		}

		world = ['dev-vcs/mercurial']

		test_cases = (

			# Test https://bugs.funtoo.org/browse/FL-7370
			ResolverPlaygroundTestCase(
				['dev-python/cffi'],
				options = {'--backtrack': 0},
				success = True,
				mergelist = ['dev-python/cffi-1.14.2', 'dev-python/zstandard-0.14.0']),

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
