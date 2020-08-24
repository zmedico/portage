# -*- coding: utf-8 -*-
# Copright Gentoo Foundation 2006
# Portage Unit Testing Functionality

import tempfile
import tarfile
import io
import sys
from os import urandom

from portage import os
from portage import shutil
from portage.util._compare_files import compare_files
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.gpkg import gpkg


class test_gpkg_path_case(TestCase):
	def test_gpkg_short_path(self):
		if sys.version_info.major < 3:
			self.skipTest("Not support Python 2")

		playground = ResolverPlayground(
			user_config={
				"make.conf":
				(
					'BINPKG_COMPRESS="none"',
				),
			}
		)
		tmpdir = tempfile.mkdtemp()

		try:
			settings = playground.settings
			path_name = (
				'aaaabbbb/ccccdddd/eeeeffff/gggghhhh/iiiijjjj/kkkkllll/'
				'mmmmnnnn/oooopppp/qqqqrrrr/sssstttt/uuuuvvvv/wwwwxxxx/'
				'yyyyzzzz/00001111/22223333/44445555/66667777/88889999/')
			orig_full_path = os.path.join(tmpdir, 'orig/' + path_name)
			os.makedirs(orig_full_path)
			with open(os.path.join(orig_full_path, 'test'), 'wb') as test_file:
				test_file.write(urandom(1048576))

			gpkg_file_loc = os.path.join(tmpdir, 'test.gpkg.tar')
			test_gpkg = gpkg(settings, 'test', gpkg_file_loc)

			check_result = test_gpkg._check_pre_image_files(
				os.path.join(tmpdir, 'orig'))
			self.assertEqual(check_result, (166, 1048576, 1048576))

			test_gpkg.compress(os.path.join(tmpdir, 'orig'), {'meta': 'test'})
			with open(gpkg_file_loc, 'rb') as container:
				# container
				self.assertEqual(test_gpkg._get_tar_format(container),
					tarfile.USTAR_FORMAT)

			with tarfile.open(gpkg_file_loc, 'r') as container:
				metadata = io.BytesIO(
					container.extractfile('test/metadata.tar').read())
				self.assertEqual(test_gpkg._get_tar_format(metadata),
					tarfile.USTAR_FORMAT)
				metadata.close()

				image = io.BytesIO(
					container.extractfile('test/image.tar').read())
				self.assertEqual(test_gpkg._get_tar_format(image),
					tarfile.USTAR_FORMAT)
				image.close()

			test_gpkg.decompress(os.path.join(tmpdir, 'test'))
			r = compare_files(
				os.path.join(tmpdir, 'orig/' + path_name + 'test'),
				os.path.join(tmpdir, 'test/' + path_name + 'test'),
				skipped_types=('atime', 'mtime', 'ctime'))
			self.assertEqual(r, ())
		finally:
			shutil.rmtree(tmpdir)
			playground.cleanup()

	def test_gpkg_long_path(self):
		if sys.version_info.major < 3:
			self.skipTest("Not support Python 2")

		playground = ResolverPlayground(
			user_config={
				"make.conf":
				(
					'BINPKG_COMPRESS="none"',
				),
			}
		)
		tmpdir = tempfile.mkdtemp()

		try:
			settings = playground.settings

			path_name = (
				'aaaabbbb/ccccdddd/eeeeffff/gggghhhh/iiiijjjj/kkkkllll/'
				'mmmmnnnn/oooopppp/qqqqrrrr/sssstttt/uuuuvvvv/wwwwxxxx/'
				'yyyyzzzz/00001111/22223333/44445555/66667777/88889999/'
				'aaaabbbb/ccccdddd/eeeeffff/gggghhhh/iiiijjjj/kkkkllll/'
				'mmmmnnnn/oooopppp/qqqqrrrr/sssstttt/uuuuvvvv/wwwwxxxx/'
				'yyyyzzzz/00001111/22223333/44445555/66667777/88889999/')
			orig_full_path = os.path.join(tmpdir, 'orig/' + path_name)
			os.makedirs(orig_full_path)
			with open(os.path.join(orig_full_path, 'test'), 'wb') as test_file:
				test_file.write(urandom(1048576))

			gpkg_file_loc = os.path.join(tmpdir, 'test.gpkg.tar')
			test_gpkg = gpkg(settings, 'test', gpkg_file_loc)

			check_result = test_gpkg._check_pre_image_files(
				os.path.join(tmpdir, 'orig'))
			self.assertEqual(check_result, (328, 1048576, 1048576))

			test_gpkg.compress(os.path.join(tmpdir, 'orig'), {'meta': 'test'})
			with open(gpkg_file_loc, 'rb') as container:
				# container
				self.assertEqual(test_gpkg._get_tar_format(container),
					tarfile.USTAR_FORMAT)

			with tarfile.open(gpkg_file_loc, 'r') as container:
				metadata = io.BytesIO(
					container.extractfile('test/metadata.tar').read())
				self.assertEqual(test_gpkg._get_tar_format(metadata),
					tarfile.USTAR_FORMAT)
				metadata.close()

				image = io.BytesIO(
					container.extractfile('test/image.tar').read())
				self.assertEqual(test_gpkg._get_tar_format(image),
					tarfile.GNU_FORMAT)
				image.close()

			test_gpkg.decompress(os.path.join(tmpdir, 'test'))
			r = compare_files(
				os.path.join(tmpdir, 'orig/' + path_name + 'test'),
				os.path.join(tmpdir, 'test/' + path_name + 'test'),
				skipped_types=('atime', 'mtime', 'ctime'))
			self.assertEqual(r, ())
		finally:
			shutil.rmtree(tmpdir)
			playground.cleanup()

	def test_gpkg_non_ascii_path(self):
		if sys.version_info.major < 3:
			self.skipTest("Not support Python 2")

		playground = ResolverPlayground(
			user_config={
				"make.conf":
				(
					'BINPKG_COMPRESS="none"',
				),
			}
		)
		tmpdir = tempfile.mkdtemp()

		try:
			settings = playground.settings

			path_name = '中文测试/日本語テスト/한국어시험/'
			orig_full_path = os.path.join(tmpdir, 'orig/' + path_name)
			os.makedirs(orig_full_path)
			with open(os.path.join(orig_full_path, 'test'), 'wb') as test_file:
				test_file.write(urandom(1048576))

			gpkg_file_loc = os.path.join(tmpdir, 'test.gpkg.tar')
			test_gpkg = gpkg(settings, 'test', gpkg_file_loc)

			check_result = test_gpkg._check_pre_image_files(
				os.path.join(tmpdir, 'orig'))
			self.assertEqual(check_result, (52, 1048576, 1048576))

			test_gpkg.compress(os.path.join(tmpdir, 'orig'), {'meta': 'test'})
			with open(gpkg_file_loc, 'rb') as container:
				# container
				self.assertEqual(test_gpkg._get_tar_format(container),
					tarfile.USTAR_FORMAT)

			with tarfile.open(gpkg_file_loc, 'r') as container:
				metadata = io.BytesIO(
					container.extractfile('test/metadata.tar').read())
				self.assertEqual(test_gpkg._get_tar_format(metadata),
					tarfile.USTAR_FORMAT)
				metadata.close()

				image = io.BytesIO(
					container.extractfile('test/image.tar').read())
				self.assertEqual(test_gpkg._get_tar_format(image),
					tarfile.USTAR_FORMAT)
				image.close()

			test_gpkg.decompress(os.path.join(tmpdir, 'test'))
			r = compare_files(
				os.path.join(tmpdir, 'orig/' + path_name + 'test'),
				os.path.join(tmpdir, 'test/' + path_name + 'test'),
				skipped_types=('atime', 'mtime', 'ctime'))
			self.assertEqual(r, ())
		finally:
			shutil.rmtree(tmpdir)
			playground.cleanup()

	def test_gpkg_symlink_path(self):
		if sys.version_info.major < 3:
			self.skipTest("Not support Python 2")

		playground = ResolverPlayground(
			user_config={
				"make.conf":
				(
					'BINPKG_COMPRESS="none"',
				),
			}
		)
		tmpdir = tempfile.mkdtemp()

		try:
			settings = playground.settings

			orig_full_path = os.path.join(tmpdir, 'orig/')
			os.makedirs(orig_full_path)
			os.symlink(
				'aaaabbbb/ccccdddd/eeeeffff/gggghhhh/iiiijjjj/kkkkllll/'
				'mmmmnnnn/oooopppp/qqqqrrrr/sssstttt/uuuuvvvv/wwwwxxxx/'
				'yyyyzzzz/00001111/22223333/44445555/66667777/88889999/'
				'aaaabbbb/ccccdddd/eeeeffff/gggghhhh/iiiijjjj/kkkkllll/'
				'mmmmnnnn/oooopppp/qqqqrrrr/sssstttt/uuuuvvvv/wwwwxxxx/'
				'yyyyzzzz/00001111/22223333/44445555/66667777/88889999/',
				os.path.join(orig_full_path, 'a_long_symlink'))

			gpkg_file_loc = os.path.join(tmpdir, 'test.gpkg.tar')
			test_gpkg = gpkg(settings, 'test', gpkg_file_loc)

			check_result = test_gpkg._check_pre_image_files(
				os.path.join(tmpdir, 'orig'))
			self.assertEqual(check_result, (324, 0, 0))

			test_gpkg.compress(os.path.join(tmpdir, 'orig'), {'meta': 'test'})
			with open(gpkg_file_loc, 'rb') as container:
				# container
				self.assertEqual(test_gpkg._get_tar_format(container),
					tarfile.USTAR_FORMAT)

			with tarfile.open(gpkg_file_loc, 'r') as container:
				metadata = io.BytesIO(
					container.extractfile('test/metadata.tar').read())
				self.assertEqual(test_gpkg._get_tar_format(metadata),
					tarfile.USTAR_FORMAT)
				metadata.close()

				image = io.BytesIO(
					container.extractfile('test/image.tar').read())
				self.assertEqual(test_gpkg._get_tar_format(image),
					tarfile.GNU_FORMAT)
				image.close()

			test_gpkg.decompress(os.path.join(tmpdir, 'test'))
			r = compare_files(
				os.path.join(tmpdir, 'orig/', 'a_long_symlink'),
				os.path.join(tmpdir, 'test/', 'a_long_symlink'),
				skipped_types=('atime', 'mtime', 'ctime'))
			self.assertEqual(r, ())
		finally:
			shutil.rmtree(tmpdir)
			playground.cleanup()
