# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import portage
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground

from _emerge.Package import Package


class CyclePassPackageTestCase(TestCase):
    """
    A package that is merged twice in one session, in order to break a
    circular dependency, needs an identity of its own and has to be
    built with the USE flags that the resolver chose for it.
    """

    def testCyclePassIdentity(self):
        ebuilds = {
            "media-libs/freetype-1": {
                "DEPEND": "harfbuzz? ( media-libs/harfbuzz )",
                "IUSE": "+harfbuzz",
                "EAPI": "8",
            },
            "media-libs/harfbuzz-1": {
                "DEPEND": "media-libs/freetype",
                "EAPI": "8",
            },
        }

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            root_config = playground.trees[playground.eroot]["root_config"]
            portdb = playground.trees[playground.eroot]["porttree"].dbapi
            cpv = portdb.cp_list("media-libs/freetype")[0]
            metadata = zip(
                Package.metadata_keys,
                portdb.aux_get(cpv, Package.metadata_keys, myrepo=cpv.repo),
            )
            metadata = dict(metadata)

            final = Package(
                built=False,
                cpv=cpv,
                metadata=metadata,
                root_config=root_config,
                type_name="ebuild",
            )
            transient = Package(
                built=False,
                cpv=cpv,
                cycle_pass=1,
                cycle_use_changes={"harfbuzz": False},
                metadata=metadata,
                root_config=root_config,
                type_name="ebuild",
            )

            # The two instances must be distinguishable, so that both can
            # be present in the same graph and merge list.
            self.assertNotEqual(final, transient)
            self.assertEqual(len({final, transient}), 2)
            self.assertEqual(final.cycle_pass, None)
            self.assertEqual(transient.cycle_pass, 1)

            # The forced USE flags are applied to the build settings.
            settings = portage.config(clone=playground.settings)
            settings.unlock()
            settings.setcpv(final)
            self.assertTrue("harfbuzz" in settings["PORTAGE_USE"].split())
            settings.setcpv(transient)
            self.assertFalse("harfbuzz" in settings["PORTAGE_USE"].split())
            settings.setcpv(final)
            self.assertTrue("harfbuzz" in settings["PORTAGE_USE"].split())
        finally:
            playground.cleanup()
