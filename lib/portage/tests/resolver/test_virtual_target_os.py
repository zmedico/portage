# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class VirtualTargetOsTestCase(TestCase):

	def testVirtualTargetOs(self):
		ebuilds = {
			'app-eselect/eselect-awk-0.2': {},
			'sys-apps/gawk-4.1.4': {
				'RDEPEND': 'sys-libs/readline'
			},
			'sys-apps/mawk-1.3.4_p20171017-r1': {
				'RDEPEND': 'app-eselect/eselect-awk'
			},
			'sys-libs/ncurses-6.0-r2': {},
			'sys-libs/readline-7.0_p3': {
				'RDEPEND': 'sys-libs/ncurses'
			},
			'virtual/awk-1': {
				'RDEPEND': '|| ( >=sys-apps/gawk-4.0.1-r1 sys-apps/mawk )'
			},
			'virtual/implicit-system-1': {
				'EAPI': '5',
				'RDEPEND': 'sys-apps/mawk'
			},
			'virtual/target-os-1': {
				'EAPI': '5',
				'RDEPEND': 'virtual/implicit-system virtual/awk'
			},
		}

		binpkgs = {
			'app-eselect/eselect-awk-0.2': {},
			'sys-apps/gawk-4.1.4': {
				'RDEPEND': 'sys-libs/readline'
			},
			'sys-apps/mawk-1.3.4_p20171017-r1': {
				'RDEPEND': 'app-eselect/eselect-awk'
			},
			'sys-libs/ncurses-6.0-r2': {},
			'sys-libs/readline-7.0_p3': {
				'RDEPEND': 'sys-libs/ncurses'
			},
			'virtual/awk-1': {
				'RDEPEND': '|| ( >=sys-apps/gawk-4.0.1-r1 sys-apps/mawk )'
			},
			'virtual/implicit-system-1': {
				'EAPI': '5',
				'RDEPEND': 'sys-apps/mawk'
			},
			'virtual/target-os-1': {
				'EAPI': '5',
				'RDEPEND': 'virtual/implicit-system virtual/awk'
			},
		}

		test_cases = (
			# bug 645914
			ResolverPlaygroundTestCase(
				['virtual/target-os'],
				options={'--emptytree': True, '--usepkgonly': False},
				success=True,
				ambiguous_merge_order=True,
				mergelist=[
					'[binary]app-eselect/eselect-awk-0.2{targetroot}',
					'[binary]sys-apps/mawk-1.3.4_p20171017-r1{targetroot}',
					(
						'[binary]virtual/awk-1{targetroot}',
						'[binary]virtual/implicit-system-1{targetroot}',
					),
					'[binary]virtual/target-os-1{targetroot}',
				]
			),
		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds, binpkgs=binpkgs, targetroot=True)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
