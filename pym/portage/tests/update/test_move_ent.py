# Copyright 2012-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import textwrap

import portage
from portage import os
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs
from portage._global_updates import _do_global_updates

class MoveEntTestCase(TestCase):

	def testMoveEnt(self):
		self._testMoveEnt(False)

	def testMoveEntMultiInstance(self):
		self._testMoveEnt(True)

	def _testMoveEnt(self, multi_instance):

		ebuilds = {

			"dev-libs/A-2::dont_apply_updates" : {
				"EAPI": "4",
				"SLOT": "2",
			},

		}

		installed = {

			"dev-libs/A-1::test_repo" : {
				"EAPI": "4",
			},

			"dev-libs/A-2::dont_apply_updates" : {
				"EAPI": "4",
				"SLOT": "2",
			},

			"dev-libs/A-1::test_repo" : {
				"EAPI": "4",
			},

			"old-cat/B-1::test_repo" : {
				"EAPI": "4",
			},
		}

		binpkgs = {
			"dev-libs/A-1::test_repo" : {
				"EAPI": "4",
			},

			"dev-libs/A-2::dont_apply_updates" : {
				"EAPI": "4",
				"SLOT": "2",
			},

			"old-cat/B-1::test_repo" : {
				"EAPI": "4",
			},
		}


		user_config = {
			"make.conf":
				(
					"FEATURES=\"binpkg-multi-instance\"" if multi_instance else "",
				),
		}

		updates = textwrap.dedent("""
			move dev-libs/A dev-libs/A-moved
			move old-cat/B new-cat/B
		""")

		playground = ResolverPlayground(binpkgs=binpkgs,
			ebuilds=ebuilds, installed=installed, user_config=user_config, debug=True)

		settings = playground.settings
		trees = playground.trees
		eroot = settings["EROOT"]
		test_repo_location = settings.repositories["test_repo"].location
		portdb = trees[eroot]["porttree"].dbapi
		vardb = trees[eroot]["vartree"].dbapi
		bindb = trees[eroot]["bintree"].dbapi

		updates_dir = os.path.join(test_repo_location, "profiles", "updates")

		try:
			ensure_dirs(updates_dir)
			with open(os.path.join(updates_dir, "1Q-2010"), 'w') as f:
				f.write(updates)

			# Create an empty updates directory, so that this
			# repo doesn't inherit updates from the main repo.
			ensure_dirs(os.path.join(
				portdb.getRepositoryPath("dont_apply_updates"),
				"profiles", "updates"))

			global_noiselimit = portage.util.noiselimit
			portage.util.noiselimit = -2
			try:
				_do_global_updates(trees, {})
			finally:
				portage.util.noiselimit = global_noiselimit

			# Workaround for cache validation not working
			# correctly when filesystem has timestamp precision
			# of 1 second.
			vardb._clear_cache()

			# A -> A-moved
			self.assertRaises(KeyError,
				vardb.aux_get, "dev-libs/A-1", ["EAPI"])
			vardb.aux_get("dev-libs/A-moved-1", ["EAPI"])
			self.assertRaises(KeyError,
				bindb.aux_get, "dev-libs/A-1", ["EAPI"])
			bindb.aux_get("dev-libs/A-moved-1", ["EAPI"])

			# move old-cat/B new-cat/B
			vardb.aux_get("new-cat/B-1", ["EAPI"])
			bindb.aux_get("new-cat/B-1", ["EAPI"])
			for cpv in bindb.cpv_all():
				bindb.aux_update(cpv, {"KEYWORDS": "*"})

			# dont_apply_updates
			self.assertRaises(KeyError,
				vardb.aux_get, "dev-libs/A-moved-2", ["EAPI"])
			vardb.aux_get("dev-libs/A-2", ["EAPI"])
			self.assertRaises(KeyError,
				bindb.aux_get, "dev-libs/A-moved-2", ["EAPI"])
			bindb.aux_get("dev-libs/A-2", ["EAPI"])

		finally:
			playground.cleanup()
