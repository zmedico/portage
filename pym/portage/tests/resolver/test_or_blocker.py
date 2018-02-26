# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class OrBlockerTestCase(TestCase):

	def testOrBlocker(self):
		ebuilds = {
			'app-misc/A-1': {
				'EAPI': '6',
				'RDEPEND': '|| ( media-plugins/alsa-plugins !media-sound/pulseaudio )'
			},
			'media-plugins/alsa-plugins-1.1.1': {
				'EAPI': '6',
			},
			'media-sound/pulseaudio-11.1': {
				'EAPI': '6',
			},
		}

		installed = {
			'media-plugins/alsa-plugins-1.1.1': {
				'EAPI': '6',
			},
			'media-sound/pulseaudio-11.1': {
				'EAPI': '6',
			},
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				['app-misc/A'],
				success=True,
				mergelist=[
					'app-misc/A-1',
				],
			),
		)

		playground = ResolverPlayground(debug=True,
			ebuilds=ebuilds, installed=installed)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
