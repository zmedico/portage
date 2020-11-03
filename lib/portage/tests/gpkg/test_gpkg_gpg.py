# Copright Gentoo Foundation 2006-2020
# Portage Unit Testing Functionality

import io
import sys
import tarfile
import tempfile
from os import urandom

from portage import os
from portage import shutil
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.gpkg import gpkg
from portage.gpg import GPG
from portage.exception import MissingSignature, InvalidSignature


class test_gpkg_gpg_case(TestCase):
	def test_gpkg_missing_manifest_signature(self):
		if sys.version_info.major < 3:
			self.skipTest("Not support Python 2")

		playground = ResolverPlayground(
			user_config={
				"make.conf":
				(
					'FEATURES="${FEATURES} binpkg-signing '
					'binpkg-request-signature"',
					'BINPKG_FORMAT="gpkg"',
				),
			}
		)
		tmpdir = tempfile.mkdtemp()

		try:
			settings = playground.settings
			gpg = GPG(settings)
			gpg.unlock()
			orig_full_path = os.path.join(tmpdir, "orig/")
			os.makedirs(orig_full_path)

			data = urandom(1048576)
			with open(os.path.join(orig_full_path, "data"), 'wb') as f:
				f.write(data)

			binpkg_1 = gpkg(settings, "test",
				os.path.join(tmpdir, "test-1.gpkg.tar"))
			binpkg_1.compress(orig_full_path, {})

			with tarfile.open(
				os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
				with tarfile.open(
					os.path.join(tmpdir, "test-2.gpkg.tar"), "w") as tar_2:
					for f in tar_1.getmembers():
						if f.name != "Manifest.sig":
							tar_2.addfile(f, tar_1.extractfile(f))

			binpkg_2 = gpkg(settings, "test",
				os.path.join(tmpdir, "test-2.gpkg.tar"))

			self.assertRaises(MissingSignature,
				binpkg_2.decompress, os.path.join(tmpdir, "test"))
		finally:
			shutil.rmtree(tmpdir)
			playground.cleanup()

	def test_gpkg_missing_signature(self):
		if sys.version_info.major < 3:
			self.skipTest("Not support Python 2")

		playground = ResolverPlayground(
			user_config={
				"make.conf":
				(
					'FEATURES="${FEATURES} binpkg-signing '
					'binpkg-request-signature"',
					'BINPKG_FORMAT="gpkg"',
				),
			}
		)
		tmpdir = tempfile.mkdtemp()

		try:
			settings = playground.settings
			gpg = GPG(settings)
			gpg.unlock()
			orig_full_path = os.path.join(tmpdir, "orig/")
			os.makedirs(orig_full_path)

			data = urandom(1048576)
			with open(os.path.join(orig_full_path, "data"), 'wb') as f:
				f.write(data)

			binpkg_1 = gpkg(settings, "test",
				os.path.join(tmpdir, "test-1.gpkg.tar"))
			binpkg_1.compress(orig_full_path, {})

			with tarfile.open(
				os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
				with tarfile.open(
					os.path.join(tmpdir, "test-2.gpkg.tar"), "w") as tar_2:
					for f in tar_1.getmembers():
						if f.name.endswith(".sig") and f.name != "Manifest.sig":
							pass
						else:
							tar_2.addfile(f, tar_1.extractfile(f))

			binpkg_2 = gpkg(settings, "test",
				os.path.join(tmpdir, "test-2.gpkg.tar"))
			self.assertRaises(MissingSignature,
				binpkg_2.decompress, os.path.join(tmpdir, "test"))

		finally:
			shutil.rmtree(tmpdir)
			playground.cleanup()

	def test_gpkg_ignore_signature(self):
		if sys.version_info.major < 3:
			self.skipTest("Not support Python 2")

		playground = ResolverPlayground(
			user_config={
				"make.conf":
				(
					'FEATURES="${FEATURES} binpkg-signing '
					'binpkg-ignore-signature"',
					'BINPKG_FORMAT="gpkg"',
				),
			}
		)
		tmpdir = tempfile.mkdtemp()

		try:
			settings = playground.settings
			gpg = GPG(settings)
			gpg.unlock()
			orig_full_path = os.path.join(tmpdir, "orig/")
			os.makedirs(orig_full_path)

			data = urandom(1048576)
			with open(os.path.join(orig_full_path, "data"), 'wb') as f:
				f.write(data)

			binpkg_1 = gpkg(settings, "test",
				os.path.join(tmpdir, "test-1.gpkg.tar"))
			binpkg_1.compress(orig_full_path, {})

			with tarfile.open(
				os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
				with tarfile.open(
					os.path.join(tmpdir, "test-2.gpkg.tar"), "w") as tar_2:
					for f in tar_1.getmembers():
						if f.name == "Manifest.sig":
							pass
						else:
							tar_2.addfile(f, tar_1.extractfile(f))

			binpkg_2 = gpkg(settings, "test",
				os.path.join(tmpdir, "test-2.gpkg.tar"))
			binpkg_2.decompress(os.path.join(tmpdir, "test"))
		finally:
			shutil.rmtree(tmpdir)
			playground.cleanup()

	def test_gpkg_auto_use_signature(self):
		if sys.version_info.major < 3:
			self.skipTest("Not support Python 2")

		playground = ResolverPlayground(
			user_config={
				"make.conf":
				(
					'FEATURES="${FEATURES} binpkg-signing '
					'-binpkg-request-signature"',
					'BINPKG_FORMAT="gpkg"',
				),
			}
		)
		tmpdir = tempfile.mkdtemp()

		try:
			settings = playground.settings
			gpg = GPG(settings)
			gpg.unlock()
			orig_full_path = os.path.join(tmpdir, "orig/")
			os.makedirs(orig_full_path)

			data = urandom(1048576)
			with open(os.path.join(orig_full_path, "data"), 'wb') as f:
				f.write(data)

			binpkg_1 = gpkg(settings, "test",
				os.path.join(tmpdir, "test-1.gpkg.tar"))
			binpkg_1.compress(orig_full_path, {})

			with tarfile.open(
				os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
				with tarfile.open(
					os.path.join(tmpdir, "test-2.gpkg.tar"), "w") as tar_2:
					for f in tar_1.getmembers():
						if f.name.endswith(".sig") and f.name != "Manifest.sig":
							pass
						else:
							tar_2.addfile(f, tar_1.extractfile(f))

			binpkg_2 = gpkg(settings, "test",
				os.path.join(tmpdir, "test-2.gpkg.tar"))
			self.assertRaises(MissingSignature,
				binpkg_2.decompress, os.path.join(tmpdir, "test"))
		finally:
			shutil.rmtree(tmpdir)
			playground.cleanup()

	def test_gpkg_invalid_signature(self):
		if sys.version_info.major < 3:
			self.skipTest("Not support Python 2")

		playground = ResolverPlayground(
			user_config={
				"make.conf":
				(
					'FEATURES="${FEATURES} binpkg-signing '
					'binpkg-request-signature"',
					'BINPKG_FORMAT="gpkg"',
				),
			}
		)
		tmpdir = tempfile.mkdtemp()

		try:
			settings = playground.settings
			gpg = GPG(settings)
			gpg.unlock()
			orig_full_path = os.path.join(tmpdir, "orig/")
			os.makedirs(orig_full_path)

			data = urandom(1048576)
			with open(os.path.join(orig_full_path, "data"), 'wb') as f:
				f.write(data)

			binpkg_1 = gpkg(settings, "test",
				os.path.join(tmpdir, "test-1.gpkg.tar"))
			binpkg_1.compress(orig_full_path, {})

			with tarfile.open(
				os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
				with tarfile.open(
					os.path.join(tmpdir, "test-2.gpkg.tar"), "w") as tar_2:
					for f in tar_1.getmembers():
						if f.name == "Manifest.sig":
							sig = b"""
-----BEGIN PGP SIGNATURE-----

iHUEUCXw1ePQAKCRB+k2dcK9uy
Ij41J83LBxquFJK9w0wHqtPQEAng76U5G41NEC
HWhcS+9vk1Q4/qMk2Q4=
=Gb7U
-----END PGP SIGNATURE-----
"""
							data = io.BytesIO(sig)
							f.size = len(sig)
							tar_2.addfile(f, data)
							data.close()
						else:
							tar_2.addfile(f, tar_1.extractfile(f))

			binpkg_2 = gpkg(settings, "test",
				os.path.join(tmpdir, "test-2.gpkg.tar"))
			self.assertRaises(InvalidSignature,
				binpkg_2.decompress, os.path.join(tmpdir, "test"))
		finally:
			shutil.rmtree(tmpdir)
			playground.cleanup()

	def test_gpkg_untrusted_signature(self):
		if sys.version_info.major < 3:
			self.skipTest("Not support Python 2")

		gpg_test_path = os.environ["GNUPGHOME"]

		playground = ResolverPlayground(
			user_config={
				"make.conf":
				(
					'FEATURES="${FEATURES} binpkg-signing '
					'binpkg-request-signature"',
					'BINPKG_FORMAT="gpkg"',

					'BINPKG_GPG_UNLOCK_COMMAND='
					'"/usr/bin/gpg --detach-sig --armor --batch --no-tty --yes '
					'--digest-algo SHA256 --homedir "%s" '
					'--pinentry-mode loopback --passphrase "GentooTest" '
					'--local-user 8812797DDF1DD192 --output /dev/null /dev/null"'
					% gpg_test_path,

					'BINPKG_GPG_SIGNING_COMMAND='
					'"/usr/bin/gpg --detach-sig --armor --batch --no-tty --yes '
					'--digest-algo SHA256 --homedir "%s" '
					'--local-user 8812797DDF1DD192"'
					% gpg_test_path,
				),
			}
		)
		tmpdir = tempfile.mkdtemp()

		try:
			settings = playground.settings
			gpg = GPG(settings)
			gpg.unlock()
			orig_full_path = os.path.join(tmpdir, "orig/")
			os.makedirs(orig_full_path)

			data = urandom(1048576)
			with open(os.path.join(orig_full_path, "data"), 'wb') as f:
				f.write(data)

			binpkg_1 = gpkg(settings, "test",
				os.path.join(tmpdir, "test-1.gpkg.tar"))
			binpkg_1.compress(orig_full_path, {})

			binpkg_2 = gpkg(settings, "test",
				os.path.join(tmpdir, "test-1.gpkg.tar"))
			self.assertRaises(InvalidSignature,
				binpkg_2.decompress, os.path.join(tmpdir, "test"))

		finally:
			shutil.rmtree(tmpdir)
			playground.cleanup()

	def test_gpkg_unknown_signature(self):
		if sys.version_info.major < 3:
			self.skipTest("Not support Python 2")

		playground = ResolverPlayground(
			user_config={
				"make.conf":
				(
					'FEATURES="${FEATURES} binpkg-signing '
					'binpkg-request-signature"',
					'BINPKG_FORMAT="gpkg"',
				),
			}
		)
		tmpdir = tempfile.mkdtemp()

		try:
			settings = playground.settings
			gpg = GPG(settings)
			gpg.unlock()
			orig_full_path = os.path.join(tmpdir, "orig/")
			os.makedirs(orig_full_path)

			data = urandom(1048576)
			with open(os.path.join(orig_full_path, "data"), 'wb') as f:
				f.write(data)

			binpkg_1 = gpkg(settings, "test",
				os.path.join(tmpdir, "test-1.gpkg.tar"))
			binpkg_1.compress(orig_full_path, {})

			with tarfile.open(
				os.path.join(tmpdir, "test-1.gpkg.tar"), "r") as tar_1:
				with tarfile.open(
					os.path.join(tmpdir, "test-2.gpkg.tar"), "w") as tar_2:
					for f in tar_1.getmembers():
						if f.name == "Manifest.sig":
							sig = b"""
-----BEGIN PGP SIGNATURE-----

iHUEABYIAB0WIQRVhCbPGi/rhGTq4nV+k2dcK9uyIgUCXw4ehAAKCRB+k2dcK9uy
IkCfAP49AOYjzuQPP0n5P0SGCINnAVEXN7QLQ4PurY/lt7cT2gEAq01stXjFhrz5
87Koh+ND2r5XfQsz3XeBqbb/BpmbEgo=
=sc5K
-----END PGP SIGNATURE-----
"""
							data = io.BytesIO(sig)
							f.size = len(sig)
							tar_2.addfile(f, data)
							data.close()
						else:
							tar_2.addfile(f, tar_1.extractfile(f))

			binpkg_2 = gpkg(settings, "test",
				os.path.join(tmpdir, "test-2.gpkg.tar"))
			self.assertRaises(InvalidSignature,
				binpkg_2.decompress, os.path.join(tmpdir, "test"))

		finally:
			shutil.rmtree(tmpdir)
			playground.cleanup()
