# Copright Gentoo Foundation 2006-2020
# Portage Unit Testing Functionality

import tempfile
import tarfile
import io
import sys
from os import urandom
import gzip

from portage import os
from portage import shutil
from portage.util._compare_files import compare_files
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.gpkg import gpkg

class test_gpkg_large_size_case(TestCase):
	def test_gpkg_large_size(self):
		if sys.version_info.major < 3:
			self.skipTest("Not support Python 2")

		playground = ResolverPlayground(
			user_config={
				"make.conf":
				(
					'BINPKG_COMPRESS="gzip"',
				),
			}
		)
		settings = playground.settings

		tmpdir = tempfile.mkdtemp()
		orig_full_path = os.path.join(tmpdir, 'orig/')
		os.makedirs(orig_full_path)
		# Check if filesystem support sparse file
		with open(os.path.join(orig_full_path, 'test'), 'wb') as test_file:
			test_file.truncate(1048576)

		if os.stat(os.path.join(orig_full_path, 'test')).st_blocks != 0:
			self.skipTest("Filesystem does not support sparse file")

		with open(os.path.join(orig_full_path, 'test'), 'wb') as test_file:
			test_file.truncate(10737418240)

		gpkg_file_loc = os.path.join(tmpdir, 'test.gpkg.tar')
		test_gpkg = gpkg(settings, 'test', gpkg_file_loc)

		check_result = test_gpkg._check_pre_image_files(
			os.path.join(tmpdir, 'orig'))
		self.assertEqual(check_result, (4, 10737418240, 10737418240))

		test_gpkg.compress(os.path.join(tmpdir, 'orig'), {'meta': 'test'})

		with open(gpkg_file_loc, 'rb') as container:
			# container
			self.assertEqual(test_gpkg._get_tar_format(container),
				tarfile.GNU_FORMAT)

		shutil.rmtree(tmpdir)
