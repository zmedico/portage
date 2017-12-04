# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep._extract_conditionals import extract_conditionals


class ExtractConditionalsTestCase(TestCase):

	def testExtractConditionals(self):

		test_cases = (
			(
				'test? ( A ) ',
				('test',),
				['test?', ['A']],
			),
			(
				'foo? ( A ) ',
				('test',),
				[],
			),
			(
				'test? ( foo? ( A ) )',
				('test',),
				['test?', ['foo?', ['A']]],
			),
			(
				'|| ( test? ( A ) )',
				('test',),
				['test?', ['A']],
			),
			(
				'|| ( test? ( A ) B )',
				('test',),
				['test?', ['A']],
			),
			(
				'|| ( test? ( A B ) )',
				('test',),
				['test?', ['A', 'B']],
			),
			(
				'|| ( test? ( A ) ( B test? ( C ) ) )',
				('test',),
				['||', ['test?', ['A'], 'test?', ['C']]],
			),
			(
				'|| ( test? ( A ) ( B test? ( C foo? ( D ) ) ) )',
				('test',),
				['||', ['test?', ['A'], 'test?', ['C', 'foo?', ['D']]]],
			),
		)

		for dep_str, selected, result in test_cases:
			self.assertEqual(extract_conditionals(dep_str, selected), result)
