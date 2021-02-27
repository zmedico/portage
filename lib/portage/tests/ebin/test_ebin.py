# Copyright 2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import contextlib
import os
import tempfile
from unittest.mock import patch

from portage.tests import TestCase
from portage.ebin.main import main


class EbinTestCase(TestCase):
	def test_ebin_main(self):
		with contextlib.ExitStack() as stack:
			tmpdir = stack.enter_context(tempfile.TemporaryDirectory())
			config_root = os.path.join(tmpdir, "config_root")
			dest_distdir = os.path.join(tmpdir, "dest_distdir")
			dest_repo = os.path.join(tmpdir, "dest_repo")
			source_image = os.path.join(tmpdir, "source_image")
			with patch(
				"sys.argv",
				[
					"ebin",
					"-vvv",
					"regen",
					"--source-dir",
					source_image,
					"--dest-distdir",
					dest_distdir,
					"--dest-repo",
					dest_repo,
				],
			):
				main()
