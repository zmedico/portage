# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import subprocess
import sys

import portage
from portage.const import PORTAGE_PYM_PATH, USER_CONFIG_PATH
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs
from portage.util._pending_rebuilds import get_pending_rebuilds


class CycleBreakEmergeTestCase(TestCase):
    def testCycleBreak(self):
        """
        Merge a cycle with --cycle-break=y and check that the first
        build really uses the reduced USE configuration, that the
        second one uses the requested configuration, and that nothing
        is left recorded as needing a rebuild.
        """
        debug = False

        ebuilds = {
            "media-libs/freetype-1": {
                "EAPI": "8",
                "IUSE": "+harfbuzz",
                "DEPEND": "harfbuzz? ( media-libs/harfbuzz )",
                "RDEPEND": "harfbuzz? ( media-libs/harfbuzz )",
                "MISC_CONTENT": 'S="${WORKDIR}"\n',
            },
            "media-libs/harfbuzz-1": {
                "EAPI": "8",
                "DEPEND": "media-libs/freetype",
                "RDEPEND": "media-libs/freetype",
                # Record the USE configuration of the freetype that was
                # installed when this package was built.
                "MISC_CONTENT": (
                    'S="${WORKDIR}"\n'
                    "src_install() {\n"
                    "\tinsinto /usr/share/${PN}\n"
                    "\tif has_version 'media-libs/freetype[harfbuzz]' ; then\n"
                    '\t\techo harfbuzz > "${T}"/freetype-use.txt\n'
                    "\telse\n"
                    '\t\techo -harfbuzz > "${T}"/freetype-use.txt\n'
                    "\tfi\n"
                    '\tdoins "${T}"/freetype-use.txt\n'
                    "}\n"
                ),
            },
        }

        # The user asks for USE=harfbuzz, so the cycle cannot be solved
        # with a USE change.
        user_config = {"make.conf": ('USE="harfbuzz"',)}

        playground = ResolverPlayground(
            ebuilds=ebuilds, user_config=user_config, debug=debug
        )

        settings = playground.settings
        eprefix = settings["EPREFIX"]
        eroot = settings["EROOT"]
        trees = playground.trees
        vardb = trees[eroot]["vartree"].dbapi
        var_cache_edb = os.path.join(eprefix, "var", "cache", "edb")
        user_config_dir = os.path.join(eprefix, USER_CONFIG_PATH)

        portage_python = portage._python_interpreter
        emerge_cmd = (
            portage_python,
            "-b",
            "-Wd",
            os.path.join(str(self.bindir), "emerge"),
            "--cycle-break=y",
        )

        portage_tmpdir = os.path.join(eprefix, "var", "tmp", "portage")
        fake_bin = os.path.join(eprefix, "bin")

        path = settings.get("PATH")
        if path is not None and not path.strip():
            path = None
        if path is None:
            path = ""
        else:
            path = ":" + path
        path = fake_bin + path

        pythonpath = os.environ.get("PYTHONPATH")
        if pythonpath is not None and not pythonpath.strip():
            pythonpath = None
        if pythonpath is not None and pythonpath.split(":")[0] == PORTAGE_PYM_PATH:
            pass
        else:
            if pythonpath is None:
                pythonpath = ""
            else:
                pythonpath = ":" + pythonpath
            pythonpath = PORTAGE_PYM_PATH + pythonpath

        env = {
            "PORTAGE_OVERRIDE_EPREFIX": eprefix,
            "PATH": path,
            "PORTAGE_PYTHON": portage_python,
            "PORTAGE_REPOSITORIES": settings.repositories.config_string(),
            "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE", ""),
            "PYTHONPATH": pythonpath,
            "PORTAGE_INST_GID": str(os.getgid()),
            "PORTAGE_INST_UID": str(os.getuid()),
        }

        if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
            env["__PORTAGE_TEST_HARDLINK_LOCKS"] = os.environ[
                "__PORTAGE_TEST_HARDLINK_LOCKS"
            ]

        dirs = [
            playground.distdir,
            fake_bin,
            portage_tmpdir,
            user_config_dir,
            var_cache_edb,
        ]
        true_symlinks = ["chown", "chgrp"]
        true_binary = find_binary("true")
        self.assertEqual(true_binary is None, False, "true command not found")

        try:
            for d in dirs:
                ensure_dirs(d)
            for x in true_symlinks:
                os.symlink(true_binary, os.path.join(fake_bin, x))

            with open(os.path.join(var_cache_edb, "counter"), "wb") as f:
                f.write(b"100")

            if debug:
                stdout = None
            else:
                stdout = subprocess.PIPE

            proc = subprocess.Popen(
                emerge_cmd + ("media-libs/harfbuzz",), env=env, stdout=stdout
            )
            if debug:
                proc.wait()
            else:
                output = proc.stdout.readlines()
                proc.wait()
                proc.stdout.close()
                if proc.returncode != os.EX_OK:
                    for line in output:
                        sys.stderr.write(line.decode("utf-8", "replace"))

            self.assertEqual(
                os.EX_OK,
                proc.returncode,
                f"emerge failed with exit code {proc.returncode}",
            )

            # Both packages are installed, and freetype ended up with
            # the requested USE configuration.
            self.assertTrue(vardb.cpv_exists("media-libs/harfbuzz-1"))
            self.assertTrue(vardb.cpv_exists("media-libs/freetype-1"))
            (use,) = vardb.aux_get("media-libs/freetype-1", ["USE"])
            self.assertTrue("harfbuzz" in use.split())

            # harfbuzz was built against the temporary freetype, which
            # really was built with USE=-harfbuzz.
            use_file = os.path.join(
                eroot, "usr", "share", "harfbuzz", "freetype-use.txt"
            )
            with open(use_file) as f:
                self.assertEqual(f.read().split(), ["-harfbuzz"])

            # Nothing is left waiting for a rebuild.
            self.assertEqual(get_pending_rebuilds(eroot), [])

            # Only the requested package is recorded in the world file,
            # never the temporary build.
            world_file = os.path.join(eroot, portage.const.WORLD_FILE)
            with open(world_file) as f:
                self.assertEqual(f.read().split(), ["media-libs/harfbuzz"])
        finally:
            playground.debug = False
            playground.cleanup()
