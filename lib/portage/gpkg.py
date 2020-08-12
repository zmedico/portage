# Copyright 2001-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import tarfile
import io
import threading
import subprocess
import errno
import pwd
import grp
import stat
import sys
import tempfile
from datetime import datetime

from portage import checksum
from portage import os
from portage import shutil
from portage import normalize_path
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.exception import (FileNotFound, InvalidBinaryPackageFormat,
	InvalidCompressionMethod, CompressorNotFound,
	CompressorOperationFailed, CommandNotFound, GPGException,
	DigestException, MissingSignature, InvalidSignature)
from portage.output import colorize
from portage.util._urlopen import urlopen
from portage.util import writemsg
from portage.util import shlex_split, varexpand
from portage.util.compression_probe import _compressors
from portage.process import find_binary
from portage.package.ebuild.config import config
from portage.const import MANIFEST2_HASH_DEFAULTS, HASHING_BLOCKSIZE


class tar_stream_writer:
	"""
	One-pass helper function that return a file-like object
	for create a file inside of a tar container.

	This helper allowed streaming add a new file to tar
	without prior knows the file size.

	With optional call and pipe data through external program,
	the helper can transparently save compressed data.

	With optional checksum helper, this helper can create
	corresponding checksum and GPG signature.

	Example:

	writer = tar_stream_writer(
		file_tarinfo,            # the file tarinfo that need to be added
		container,               # the outer container tarfile object
		tarfile.USTAR_FORMAT,    # the outer container format
		["gzip"],                # compression command
		checksum_helper          # checksum helper
	)

	writer.write(data)
	writer.close()
	"""
	def __init__(self, tarinfo, container, tar_format, cmd=None,
			checksum_helper=None):
		"""
		tarinfo          # the file tarinfo that need to be added
		container        # the outer container tarfile object
		tar_format       # the outer container format for create the tar header
		cmd              # subprocess.Popen format compression command
		checksum_helper  # checksum helper
		"""
		self.checksum_helper = checksum_helper
		self.closed = False
		self.container = container
		self.killed = False
		self.tar_format = tar_format
		self.tarinfo = tarinfo

		# Record container end position
		self.container.fileobj.seek(0, io.SEEK_END)
		self.begin_position = self.container.fileobj.tell()
		self.end_position = 0
		self.file_size = 0

		# Write tar header without size
		tar_header = self.tarinfo.tobuf(self.tar_format,
			self.container.encoding,
			self.container.errors)
		self.header_size = len(tar_header)
		self.container.fileobj.write(tar_header)
		self.container.fileobj.flush()
		self.container.offset += self.header_size

		# Start external compressor if needed
		if cmd is None:
			self.proc = None
		else:
			self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
				stdout=subprocess.PIPE, stderr=subprocess.PIPE)
			self.read_thread = threading.Thread(target=self._cmd_read_thread,
				name="tar_stream_cmd_read", daemon=True)
			self.read_thread.start()

	def __del__(self):
		self.close()

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		self.close()

	def kill(self):
		"""
		kill external program if any error happened in python
		"""
		if self.proc is not None:
			self.killed = True
			self.proc.kill()
			self.proc.stdin.close()
			self.close()

	def _cmd_read_thread(self):
		"""
		Use thread to avoid block.
		Read stdout from external compressor, then write to the file
		in container, and to checksum helper if needed.
		"""
		while True:
			try:
				buffer = self.proc.stdout.read(HASHING_BLOCKSIZE)
				if not buffer:
					self.proc.stdout.close()
					self.proc.stderr.close()
					return
			except BrokenPipeError:
				self.proc.stdout.close()
				if not self.killed:
					# Do not raise error if killed by portage
					raise CompressorOperationFailed("PIPE broken")

			self.container.fileobj.write(buffer)
			if self.checksum_helper:
				self.checksum_helper.update(buffer)

	def write(self, data):
		"""
		Write data to tarfile or external compressor stdin
		"""
		if self.closed:
			raise OSError("writer closed")

		if self.proc:
			# Write to external program
			self.proc.stdin.write(data)
		else:
			# Write to container
			self.container.fileobj.write(data)
			if self.checksum_helper:
				self.checksum_helper.update(data)

	def close(self):
		"""
		Update the new file tar header when close
		"""
		if self.closed:
			return

		# Wait compressor exit
		if self.proc is not None:
			self.proc.stdin.close()
			if self.proc.wait() != os.EX_OK:
				raise CompressorOperationFailed("compression failed")
			if self.read_thread.is_alive():
				self.read_thread.join()

		# Get container end position and calculate file size
		self.container.fileobj.seek(0, io.SEEK_END)
		self.end_position = self.container.fileobj.tell()
		self.file_size = self.end_position - self.begin_position \
			- self.header_size
		self.tarinfo.size = self.file_size

		# Tar block is 512, need padding \0
		_, remainder = divmod(self.file_size, 512)
		if remainder > 0:
			padding_size = 512 - remainder
			self.container.fileobj.write(b'\0' * padding_size)
			self.container.offset += padding_size
			self.container.fileobj.flush()

		# Update tar header
		tar_header = self.tarinfo.tobuf(self.tar_format,
			self.container.encoding,
			self.container.errors)
		self.container.fileobj.seek(self.begin_position)
		self.container.fileobj.write(tar_header)
		self.container.fileobj.seek(0, io.SEEK_END)
		self.container.fileobj.flush()
		self.container.offset = self.container.fileobj.tell()
		self.closed = True

		# Add tarinfo to tarfile
		self.container.members.append(self.tarinfo)

		if self.checksum_helper:
			self.checksum_helper.finish()

		self.closed = True


class tar_stream_reader:
	"""
	helper function that return a file-like object
	for read a file inside of a tar container.

	This helper allowed transparently streaming read a compressed
	file in tar.

	With optional call and pipe compressed data through external
	program, and return the uncompressed data.

	reader = tar_stream_reader(
		fileobj,             # the fileobj from tarfile.extractfile(f)
		["gzip", "-d"],      # decompression command
	)

	reader.read()
	reader.close()
	"""
	def __init__(self, fileobj, cmd=None):
		"""
		fileobj should be a file-like object that have read().
		cmd is optional external decompressor command.
		"""
		self.closed = False
		self.cmd = cmd
		self.fileobj = fileobj
		self.killed = False

		if cmd is None:
			self.read_io = fileobj
			self.proc = None
		else:
			# Start external decompressor
			self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
				stdout=subprocess.PIPE, stderr=subprocess.PIPE)
			self.read_io = self.proc.stdout
			# Start stdin block writing thread
			self.thread = threading.Thread(target=self._write_thread,
				name="tar_stream_stdin_writer", daemon=True)
			self.thread.start()

	def __del__(self):
		try:
			self.close()
		except CompressorOperationFailed:
			pass

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		try:
			self.close()
		except CompressorOperationFailed:
			pass

	def _write_thread(self):
		"""
		writing thread to avoid full buffer blocking
		"""
		try:
			while True:
				buffer = self.fileobj.read(HASHING_BLOCKSIZE)
				if buffer:
					try:
						self.proc.stdin.write(buffer)
					except ValueError:
						if self.killed:
							return
						else:
							raise
				else:
					self.proc.stdin.flush()
					self.proc.stdin.close()
					break
		except BrokenPipeError:
			if self.killed is False:
				raise CompressorOperationFailed("PIPE broken")

	def kill(self):
		"""
		kill external program if any error happened in python
		"""
		if self.proc is not None:
			self.killed = True
			self.proc.kill()
			self.proc.stdin.close()
			self.close()

	def read(self, bufsize=-1):
		"""
		return decompressor stdout data
		"""
		if self.closed:
			raise OSError("writer closed")
		else:
			return self.read_io.read(bufsize)

	def close(self):
		"""
		wait external program complete and do clean up
		"""
		if self.closed:
			return

		self.closed = True

		if self.proc is not None:
			self.thread.join()
			try:
				if self.proc.wait() != os.EX_OK:
					if not self.proc.stderr.closed:
						stderr = self.proc.stderr.read().decode()
					if not self.killed:
						writemsg(colorize("BAD", "!!!" + "\n" + stderr))
						raise CompressorOperationFailed("decompression failed")
			finally:
				self.proc.stdout.close()
				self.proc.stderr.close()


class checksum_helper:
	"""
	Do checksum generation and GPG Signature generation and verification
	"""
	SIGNING = 0
	VERIFY = 1

	def __init__(self, settings, gpg_operation=None, signature=None):
		"""
		settings         # portage settings
		gpg_operation    # either SIGNING or VERIFY
		signature        # GPG signature string used for GPG verify only
		"""
		self.settings = settings
		self.gpg_operation = gpg_operation
		self.gpg_proc = None
		self.gpg_result = None
		self.gpg_output = None
		self.finished = False

		# Initialize the hash libs
		self.libs = {}
		for hash_name in MANIFEST2_HASH_DEFAULTS:
			self.libs[hash_name] = (checksum.hashfunc_map[hash_name]
				._hashobject())

		# GPG
		if self.gpg_operation == checksum_helper.SIGNING:
			self.GPG_signing_command = self.settings.get(
				"BINPKG_GPG_SIGNING_COMMAND", None)

			if self.GPG_signing_command:
				self.GPG_signing_command = shlex_split(
					varexpand(self.GPG_signing_command, mydict=self.settings))
				self.GPG_signing_command = [
					x for x in self.GPG_signing_command if x != ""]
				try:
					os.environ["GPG_TTY"] = os.ttyname(sys.stdout.fileno())
				except OSError:
					pass
			else:
				raise CommandNotFound("GPG signing command is not set")

			self.gpg_proc = subprocess.Popen(self.GPG_signing_command,
				stdin=subprocess.PIPE, stdout=subprocess.PIPE,
				stderr=subprocess.PIPE)

		elif self.gpg_operation == checksum_helper.VERIFY:
			if signature is None:
				raise MissingSignature("No signature provided")

			self.GPG_verify_command = self.settings.get(
				"BINPKG_GPG_VERIFY_COMMAND", None)

			if self.GPG_verify_command:
				self.sign_file_fd, self.sign_file_path = tempfile.mkstemp(
					".sig", "portage-sign-")

				# Use local settings to add signature file path
				local_settings = config(clone=self.settings)
				local_settings["SIGN_FILE"] = self.sign_file_path

				# Create signature file and allow everyone read
				with open(self.sign_file_fd, "wb") as sign:
					sign.write(signature)
				os.chmod(self.sign_file_path, 0o644)

				self.GPG_verify_command = shlex_split(
					varexpand(self.GPG_verify_command, mydict=local_settings))
				self.GPG_verify_command = [
					x for x in self.GPG_verify_command if x != ""]
			else:
				raise CommandNotFound("GPG signing command is not set")

			self.gpg_proc = subprocess.Popen(self.GPG_verify_command,
				stdin=subprocess.PIPE, stdout=subprocess.PIPE,
				stderr=subprocess.PIPE)

	def __del__(self):
		self.finish()

	def _check_gpg_status(self, gpg_status):
		"""
		Check GPG status log for extra info.
		GPG will return OK even if the signature owner is not trusted.
		"""
		good_signature = False
		trust_signature = False

		for l in gpg_status.splitlines():
			if l.startswith('[GNUPG:] GOODSIG'):
				good_signature = True

			if (l.startswith('[GNUPG:] TRUST_ULTIMATE')
				or l.startswith('[GNUPG:] TRUST_FULLY')):
				trust_signature = True

		if (not good_signature) or (not trust_signature):
			writemsg(colorize("BAD", "!!!" + "\n" + self.gpg_result.decode()))
			raise InvalidSignature("GPG verify failed")

	def update(self, data):
		"""
		Write data to hash libs and GPG stdin.
		"""
		for c in self.libs:
			self.libs[c].update(data)

		if self.gpg_proc is not None:
			self.gpg_proc.stdin.write(data)

	def finish(self):
		"""
		Tell GPG file is EOF, and get results, then do clean up.
		"""
		if self.finished:
			return

		if self.gpg_proc is not None:
			# Tell GPG EOF
			self.gpg_proc.stdin.close()

			return_code = self.gpg_proc.wait()

			if self.gpg_operation == checksum_helper.VERIFY:
				os.remove(self.sign_file_path)

			self.finished = True

			self.gpg_result = self.gpg_proc.stderr.read()
			self.gpg_output = self.gpg_proc.stdout.read()
			self.gpg_proc.stdout.close()
			self.gpg_proc.stderr.close()

			if return_code == os.EX_OK:
				if self.gpg_operation == checksum_helper.VERIFY:
					self._check_gpg_status(self.gpg_output.decode())
			else:
				writemsg(colorize("BAD", "!!!" + "\n"
					+ self.gpg_result.decode()))
				if self.gpg_operation == checksum_helper.SIGNING:
					writemsg(colorize("BAD", self.gpg_output.decode()))
					raise GPGException("GPG signing failed")
				elif self.gpg_operation == checksum_helper.VERIFY:
					raise InvalidSignature("GPG verify failed")


class gpkg:
	"""
	Gentoo binary package
	https://www.gentoo.org/glep/glep-0078.html
	"""
	def __init__(self,
			settings,
			base_name=None,
			gpkg_file=None):
		"""
		gpkg class handle all gpkg operations for one package.
		base_name is the package basename.
		gpkg_file should be exists file path for read or will create.
		"""
		if sys.version_info.major < 3:
			raise InvalidBinaryPackageFormat("GPKG not support Python 2")
		self.settings = settings
		self.gpkg_version = 'gpkg-1'
		if gpkg_file is None:
			self.gpkg_file = None
		else:
			self.gpkg_file = _unicode_decode(gpkg_file,
				encoding=_encodings['fs'], errors='strict')
		self.base_name = base_name
		self.checksums = []

		# Compression is the compression algorithm, if set to None will
		# not use compression.
		self.compression = self.settings.get("BINPKG_COMPRESS", None)
		if self.compression in ["", "none"]:
			self.compression = None

		# The create_signature is whether create signature for the package or not.
		if "binpkg-signing" in self.settings.features:
			self.create_signature = True
		else:
			self.create_signature = False

		# The rquest_signature is whether signature files are mandatory.
		# If set true, any missing signature file will cause reject processing.
		if "binpkg-request-signature" in self.settings.features:
			self.request_signature = True
		else:
			self.request_signature = False

		# The verify_signature is whether verify package signature or not.
		# In rare case user may want to ignore signature,
		# E.g. package with expired signature.
		if "binpkg-ignore-signature" in self.settings.features:
			self.verify_signature = False
		else:
			self.verify_signature = True

		self.ext_list = {"gzip": ".gz", "bzip2": ".bz2", "lz4": ".lz4",
			"lzip": ".lz", "lzop": ".lzo", "xz": ".xz", "zstd": ".zst"}

	def unpack_metadata(self, dest_dir=None):
		"""
		Unpack metadata to dest_dir.
		If dest_dir is None, return files and values in dict.
		The dict key will be UTF-8, not bytes.
		"""
		self._verify_binpkg(metadata_only=True)

		with tarfile.open(self.gpkg_file, 'r') as container:
			metadata_tarinfo, metadata_comp = self._get_inner_tarinfo(
				container, 'metadata')

			with tar_stream_reader(container.extractfile(metadata_tarinfo),
				self._get_decompression_cmd(metadata_comp)) \
				as metadata_reader:
				metadata_tar = io.BytesIO(metadata_reader.read())

			with tarfile.open(mode='r:', fileobj=metadata_tar) as metadata:
				if dest_dir is None:
					metadata_ = {k.name: metadata.extractfile(k).read()
						for k in metadata.getmembers()}
				else:
					metadata.extractall(dest_dir)
					metadata_ = True
			metadata_tar.close()
		return metadata_

	def get_metadata(self, want=None):
		"""
		get package metadata.
		if want is list, return all want key-values in dict
		if want is str, return the want key value
		"""
		if want is None:
			return self.unpack_metadata()
		elif isinstance(want, str):
			metadata = self.unpack_metadata()
			metadata_want = metadata.get(want, None)
			return metadata_want
		else:
			metadata = self.unpack_metadata()
			metadata_want = {k: metadata.get(k, None) for k in want}
			return metadata_want

	def get_metadata_url(self, url, want=None):
		"""
		Return the requested metadata from url gpkg.
		Default return all meta data.
		Use 'want' to get specific name from metadata.
		This method only support the correct package format.
		Wrong files order or incorrect basename will be considered invalid
		to reduce potential attacks.
		Only signature will be check if the signature file is the next file.
		Manifest will be ignored since it will be at the end of package.
		"""
		# The init download file head size
		init_size = 51200

		# Load remote container
		container_file = io.BytesIO(urlopen(url, headers={
			'Range': 'bytes=0-' + str(init_size)}).read())

		# Check gpkg and metadata
		with tarfile.open(mode='r', fileobj=container_file) as container:
			if self.gpkg_version not in container.getnames():
				raise InvalidBinaryPackageFormat("Invalid gpkg file.")

			metadata_tarinfo, metadata_comp = self._get_inner_tarinfo(
				container, 'metadata')

			# Extra 10240 bytes for signature
			end_size = metadata_tarinfo.offset_data \
				+ metadata_tarinfo.size + 10240
			_, remainder = divmod(end_size, 512)
			end_size += 512 - remainder

			# If need more data
			if end_size > 10000000:
				raise InvalidBinaryPackageFormat("metadata too large "
					+ str(end_size))
			if end_size > init_size:
				container_file.seek(0, io.SEEK_END)
				container_file.write(urlopen(url, headers={
					'Range': 'bytes=' + str(init_size + 1) + '-'
					+ str(end_size)}).read())

		container_file.seek(0)

		# Reload and process full metadata
		with tarfile.open(mode='r', fileobj=container_file) as container:
			metadata_tarinfo, metadata_comp = self._get_inner_tarinfo(
				container, 'metadata')

			# Verify metadata file signature if needed
			# binpkg-ignore-signature can override this.
			signature_filename = metadata_tarinfo.name + ".sig"
			if signature_filename in container.getnames():
				if (self.request_signature and self.verify_signature):
					metadata_signature = container.extractfile(
						signature_filename).read()
					checksum_info = checksum_helper(self.settings,
						gpg_operation=checksum_helper.VERIFY,
						signature=metadata_signature)
					checksum_info.update(
						container.extractfile(metadata_tarinfo).read())
					checksum_info.finish()

			# Load metadata
			with tar_stream_reader(container.extractfile(metadata_tarinfo),
				self._get_decompression_cmd(metadata_comp)) \
				as metadata_reader:
				metadata_file = io.BytesIO(metadata_reader.read())

			with tarfile.open(mode='r:', fileobj=metadata_file) as metadata:
				if want is None:
					metadata_ = {k.name: metadata.extractfile(k).read()
						for k in metadata.getmembers()}
				else:
					metadata_ = {k.name: metadata.extractfile(k).read()
						for k in metadata.getmembers() if k in want}
			metadata_file.close()
		container_file.close()
		return metadata_

	def compress(self, root_dir, metadata, clean=False):
		"""
		Use initialized configuation create new gpkg file from root_dir.
		Will overwrite any exists file.
		metadata is a dict, the key will be file name, the value will be
		the file contents.
		"""

		root_dir = normalize_path(_unicode_decode(root_dir,
			encoding=_encodings['fs'], errors='strict'))

		# Get pre image info
		container_tar_format, image_tar_format = \
			self._get_tar_format_from_stats(
				*self._check_pre_image_files(root_dir))

		# gpkg container
		container = tarfile.TarFile(name=self.gpkg_file, mode='w',
			format=container_tar_format)

		# gpkg version
		gpkg_version_file = tarfile.TarInfo(self.gpkg_version)
		gpkg_version_file.mtime = datetime.utcnow().timestamp()
		container.addfile(gpkg_version_file)

		compression_cmd = self._get_compression_cmd()

		# metadata
		self._add_metadata(container, metadata, compression_cmd)

		# image
		if self.create_signature:
			checksum_info = checksum_helper(self.settings,
				gpg_operation=checksum_helper.SIGNING)
		else:
			checksum_info = checksum_helper(self.settings)

		image_tarinfo = self._create_tarinfo("image")
		image_tarinfo.mtime = datetime.utcnow().timestamp()
		with tar_stream_writer(image_tarinfo, container,
			image_tar_format, compression_cmd, checksum_info) as image_writer:
			with tarfile.open(mode='w|', fileobj=image_writer,
				format=image_tar_format) as image_tar:
				image_tar.add(root_dir, ".", recursive=True)

		image_tarinfo = container.getmember(image_tarinfo.name)
		self._record_checksum(checksum_info, image_tarinfo)

		if self.create_signature:
			self._add_signature(checksum_info, image_tarinfo, container)

		self._add_manifest(container)
		container.close()

	def decompress(self, decompress_dir):
		"""
		decompress current gpkg to decompress_dir
		"""
		decompress_dir = normalize_path(_unicode_decode(decompress_dir,
			encoding=_encodings['fs'], errors='strict'))

		self._verify_binpkg()

		with tarfile.open(self.gpkg_file, 'r') as container:
			image_tarinfo, image_comp = \
				self._get_inner_tarinfo(container, 'image')

			with tar_stream_reader(container.extractfile(image_tarinfo),
				self._get_decompression_cmd()) as image_tar:

				with tarfile.open(mode='r|', fileobj=image_tar) as image:
					try:
						image.extractall(decompress_dir)
					except:
						e = sys.exc_info()[0]
						writemsg(colorize("BAD", "!!!" + "\n" + e))
					finally:
						image_tar.kill()

	def update_metadata(self, metadata):
		"""
		Update metadata in the gpkg file.
		"""
		self._verify_binpkg()
		self.checksums = []

		with open(self.gpkg_file, 'rb') as container:
			container_tar_format = self._get_tar_format(container)
			if container_tar_format is None:
				raise InvalidBinaryPackageFormat('Cannot identify tar format')

		# container
		tmp_gpkg_file_name = self.gpkg_file + "." + str(os.getpid())
		with tarfile.TarFile(name=tmp_gpkg_file_name,
			mode='w', format=container_tar_format) as container:
			# gpkg version
			gpkg_version_file = tarfile.TarInfo(self.gpkg_version)
			gpkg_version_file.mtime = datetime.utcnow().timestamp()
			container.addfile(gpkg_version_file)

			compression_cmd = self._get_compression_cmd()

			# metadata
			self._add_metadata(container, metadata, compression_cmd)

			# reuse image
			with tarfile.open(self.gpkg_file, 'r') \
				as container_old:
				image_old_tarinfo, image_old_comp = \
					self._get_inner_tarinfo(container_old, 'image')

				manifest_old = self._load_manifest(
					container_old.extractfile("Manifest"
						).read().decode("UTF-8"))

				for m in manifest_old:
					if m[1] == image_old_tarinfo.name:
						self.checksums.append(m)
						break

				container.addfile(image_old_tarinfo,
					container_old.extractfile(image_old_tarinfo))

				image_sign_old_name = image_old_tarinfo.name + ".sig"
				if image_sign_old_name in container_old.getnames():
					image_sign_tarinfo = container_old.getmember(
						image_sign_old_name)
					container.addfile(image_sign_tarinfo,
						container_old.extractfile(image_sign_tarinfo))

			self._add_manifest(container)

		shutil.move(tmp_gpkg_file_name, self.gpkg_file)

	def _add_metadata(self, container, metadata, compression_cmd):
		"""
		add metadata to container
		"""
		if metadata is None:
			metadata = {}
		metadata_tarinfo = self._create_tarinfo('metadata')
		metadata_tarinfo.mtime = datetime.utcnow().timestamp()

		if self.create_signature:
			checksum_info = checksum_helper(self.settings,
				gpg_operation=checksum_helper.SIGNING)
		else:
			checksum_info = checksum_helper(self.settings)

		with tar_stream_writer(metadata_tarinfo, container,
			tarfile.USTAR_FORMAT, compression_cmd, checksum_info
			) as metadata_writer:
			with tarfile.open(mode='w|', fileobj=metadata_writer,
				format=tarfile.USTAR_FORMAT) as metadata_tar:

				for m in metadata:
					m_info = tarfile.TarInfo(m)
					m_info.mtime = datetime.utcnow().timestamp()

					if isinstance(metadata[m], bytes):
						m_data = io.BytesIO(metadata[m])
					else:
						m_data = io.BytesIO(metadata[m].encode("UTF-8"))

					m_data.seek(0, io.SEEK_END)
					m_info.size = m_data.tell()
					m_data.seek(0)
					metadata_tar.addfile(m_info, m_data)
					m_data.close()

		metadata_tarinfo = container.getmember(metadata_tarinfo.name)
		self._record_checksum(checksum_info, metadata_tarinfo)

		if self.create_signature:
			self._add_signature(checksum_info, metadata_tarinfo, container)

	def _quickpkg(self, contents, metadata, root_dir, protect=None):
		"""
		Similar to compress, but for quickpkg.
		Will compress the given files to image with root,
		ignoring all other files.
		"""

		protect_file = io.BytesIO(
			b'# empty file because --include-config=n '
			+ b'when `quickpkg` was used\n')
		protect_file.seek(0, io.SEEK_END)
		protect_file_size = protect_file.tell()

		root_dir = normalize_path(_unicode_decode(root_dir,
			encoding=_encodings['fs'], errors='strict'))

		# Get pre image info
		container_tar_format, image_tar_format = \
			self._get_tar_format_from_stats(
				*self._check_pre_quickpkg_files(contents, root_dir))

		# GPKG container
		container = tarfile.TarFile(name=self.gpkg_file, mode='w',
			format=container_tar_format)

		# GPKG version
		gpkg_version_file = tarfile.TarInfo(self.gpkg_version)
		gpkg_version_file.mtime = datetime.utcnow().timestamp()
		container.addfile(gpkg_version_file)

		compression_cmd = self._get_compression_cmd()
		# Metadata
		self._add_metadata(container, metadata, compression_cmd)

		# Image
		if self.create_signature:
			checksum_info = checksum_helper(self.settings,
				gpg_operation=checksum_helper.SIGNING)
		else:
			checksum_info = checksum_helper(self.settings)

		paths = list(contents)
		paths.sort()
		image_tarinfo = self._create_tarinfo("image")
		image_tarinfo.mtime = datetime.utcnow().timestamp()
		with tar_stream_writer(image_tarinfo, container,
			image_tar_format, compression_cmd, checksum_info
			) as image_writer:
			with tarfile.open(mode='w|', fileobj=image_writer,
				format=image_tar_format) as image_tar:
				for path in paths:
					try:
						lst = os.lstat(path)
					except OSError as e:
						if e.errno != errno.ENOENT:
							raise
						del e
						continue
					contents_type = contents[path][0]
					if path.startswith(root_dir):
						arcname = "./" + path[len(root_dir):]
					else:
						raise ValueError("invalid root argument: '%s'" % root_dir)
					live_path = path
					if 'dir' == contents_type and \
						not stat.S_ISDIR(lst.st_mode) and \
						os.path.isdir(live_path):
						# Even though this was a directory in the original ${D}, it exists
						# as a symlink to a directory in the live filesystem.  It must be
						# recorded as a real directory in the tar file to ensure that tar
						# can properly extract it's children.
						live_path = os.path.realpath(live_path)
						lst = os.lstat(live_path)

					# Since os.lstat() inside TarFile.gettarinfo() can trigger a
					# UnicodeEncodeError when python has something other than utf_8
					# return from sys.getfilesystemencoding() (as in bug #388773),
					# we implement the needed functionality here, using the result
					# of our successful lstat call. An alternative to this would be
					# to pass in the fileobj argument to TarFile.gettarinfo(), so
					# that it could use fstat instead of lstat. However, that would
					# have the unwanted effect of dereferencing symlinks.

					tarinfo = image_tar.tarinfo(arcname)
					tarinfo.mode = lst.st_mode
					tarinfo.uid = lst.st_uid
					tarinfo.gid = lst.st_gid
					tarinfo.size = 0
					tarinfo.mtime = lst.st_mtime
					tarinfo.linkname = ""
					if stat.S_ISREG(lst.st_mode):
						inode = (lst.st_ino, lst.st_dev)
						if (lst.st_nlink > 1 and
							inode in image_tar.inodes and
							arcname != image_tar.inodes[inode]):
							tarinfo.type = tarfile.LNKTYPE
							tarinfo.linkname = image_tar.inodes[inode]
						else:
							image_tar.inodes[inode] = arcname
							tarinfo.type = tarfile.REGTYPE
							tarinfo.size = lst.st_size
					elif stat.S_ISDIR(lst.st_mode):
						tarinfo.type = tarfile.DIRTYPE
					elif stat.S_ISLNK(lst.st_mode):
						tarinfo.type = tarfile.SYMTYPE
						tarinfo.linkname = os.readlink(live_path)
					else:
						continue
					try:
						tarinfo.uname = pwd.getpwuid(tarinfo.uid)[0]
					except KeyError:
						pass
					try:
						tarinfo.gname = grp.getgrgid(tarinfo.gid)[0]
					except KeyError:
						pass

					if stat.S_ISREG(lst.st_mode):
						if protect and protect(path):
							protect_file.seek(0)
							tarinfo.size = protect_file_size
							image_tar.addfile(tarinfo, protect_file)
						else:
							path_bytes = _unicode_encode(path,
								encoding=_encodings['fs'],
								errors='strict')

							with open(path_bytes, 'rb') as f:
								image_tar.addfile(tarinfo, f)

					else:
						image_tar.addfile(tarinfo)

		image_tarinfo = container.getmember(image_tarinfo.name)
		self._record_checksum(checksum_info, image_tarinfo)

		if self.create_signature:
			self._add_signature(checksum_info, image_tarinfo, container)

		self._add_manifest(container)
		container.close()

	def _record_checksum(self, checksum_info, tarinfo):
		"""
		Record checksum result for the given file.
		Replace old checksum if already exists.
		"""
		for c in self.checksums:
			if c[1] == tarinfo.name:
				self.checksums.remove(c)
				break

		checksum_record = ["MANIFEST", tarinfo.name, str(tarinfo.size)]

		for c in checksum_info.libs:
			checksum_record.append(c)
			checksum_record.append(checksum_info.libs[c].hexdigest())

		self.checksums.append(checksum_record)

	def _add_manifest(self, container):
		"""
		Add Manifest to the container based on current checksums.
		Creare GPG signatue if needed.
		"""
		manifest = io.BytesIO()

		for m in self.checksums:
			manifest.write((" ".join(m) + "\n").encode("UTF-8"))

		manifest_tarinfo = tarfile.TarInfo("Manifest")
		manifest_tarinfo.size = manifest.tell()
		manifest_tarinfo.mtime = datetime.utcnow().timestamp()
		manifest.seek(0)
		container.addfile(manifest_tarinfo, manifest)

		if self.create_signature:
			checksum_info = checksum_helper(self.settings,
				gpg_operation=checksum_helper.SIGNING)
			checksum_info.update(manifest.getvalue())
			checksum_info.finish()
			self._add_signature(checksum_info, manifest_tarinfo, container)

		manifest.close()

	def _load_manifest(self, manifest_string):
		"""
		Check, load, and return manifest in a list by files
		"""
		manifest = []
		manifest_filenames = []

		for manifest_record in manifest_string.splitlines():
			if manifest_record == "":
				continue
			manifest_record = manifest_record.strip().split()

			if manifest_record[0] != "MANIFEST":
				raise DigestException("invalied Manifest")

			if manifest_record[1] in manifest_filenames:
				raise DigestException("Manifest duplicate file exists")

			try:
				int(manifest_record[2])
			except ValueError:
				raise DigestException("Manifest invalied file size")

			manifest.append(manifest_record)
			manifest_filenames.append(manifest_record[1])

		return manifest

	def _add_signature(self, checksum_info, tarinfo, container):
		"""
		Add GPG signature for the given tarinfo file.
		"""
		if checksum_info.gpg_output is None:
			raise GPGException("GPG signature is not exists")

		signature = io.BytesIO(checksum_info.gpg_output)
		signature_tarinfo = tarfile.TarInfo(tarinfo.name + ".sig")
		signature_tarinfo.size = len(signature.getvalue())
		signature_tarinfo.mtime = datetime.utcnow().timestamp()
		container.addfile(signature_tarinfo, signature)

		signature.close()

	def _verify_binpkg(self, metadata_only=False):
		"""
		Verify current GPKG file.
		"""
		# Check file path
		if self.gpkg_file is None:
			raise FileNotFound("no gpkg file provided")

		# Check if is file
		if not os.path.isfile(self.gpkg_file):
			raise FileNotFound(self.gpkg_file)

		# Check if is tar file
		with open(self.gpkg_file, 'rb') as container:
			container_tar_format = self._get_tar_format(container)
			if container_tar_format is None:
				raise InvalidBinaryPackageFormat('Cannot identify tar format')

		# Check container
		with tarfile.open(self.gpkg_file, 'r') as container:
			container_files = container.getnames()

			# Check gpkg header
			if self.gpkg_version not in container_files:
				raise InvalidBinaryPackageFormat("Invalid gpkg file.")

			# If any signature exists, we assume all files have signature.
			if any(f.endswith(".sig") for f in container_files):
				signature_exist = True
			else:
				signature_exist = False

			# Check if all files are unique to avoid same name attack
			container_files_unique = []
			for f in container_files:
				if f in container_files_unique:
					raise InvalidBinaryPackageFormat(
						"Duplicate file %s exist, potential attack?"
						% f)
				container_files_unique.append(f)

			del container_files_unique

			# Add all files to check list
			unverified_files = container_files.copy()
			unverified_files.remove(self.gpkg_version)

			# Check Manifest file
			if "Manifest" not in unverified_files:
				raise MissingSignature("Manifest not found")

			manifest_file = container.extractfile("Manifest")
			manifest_data = manifest_file.read()
			manifest_file.close()

			# Check Manifest signature if needed.
			# binpkg-ignore-signature can override this.
			if ((self.request_signature or signature_exist)
				and self.verify_signature):
				if "Manifest.sig" in unverified_files:
					signature_file = container.extractfile("Manifest.sig")
					signature = signature_file.read()
					signature_file.close()

					checksum_info = checksum_helper(self.settings,
						gpg_operation=checksum_helper.VERIFY,
						signature=signature)

					checksum_info.update(manifest_data)
					checksum_info.finish()

					unverified_files.remove("Manifest")
					unverified_files.remove("Manifest.sig")
				else:
					raise MissingSignature("Manifest signature not found")
			else:
				unverified_files.remove("Manifest")
				if "Manifest.sig" in unverified_files:
					unverified_files.remove("Manifest.sig")

			# Load manifest and create manifest check list
			manifest = self._load_manifest(manifest_data.decode("UTF-8"))
			unverified_manifest = manifest.copy()

			# Check all remaining files
			for f in unverified_files.copy():
				# Ignore signature file checksum
				if f.endswith(".sig"):
					continue

				f_signature = f + ".sig"

				# Find current file manifest record
				manifest_record = None
				for m in manifest:
					if m[1] == f:
						manifest_record = m

				if manifest_record is None:
					raise DigestException("%s checksum not found" % f)

				if int(manifest_record[2]) != int(container.getmember(f).size):
					raise DigestException("%s file size mismatched" % f)

				# Ignore image file and signature if not needed
				if (os.path.basename(f).startswith("image") and metadata_only):
					unverified_files.remove(f)
					unverified_manifest.remove(manifest_record)

					# And its signature
					if f_signature in unverified_files:
						unverified_files.remove(f_signature)
						for m in unverified_manifest:
							if m[1] == f_signature:
								unverified_manifest.remove(m)
								break
					continue

				# Verify current file signature if needed
				# binpkg-ignore-signature can override this.
				if ((self.request_signature or signature_exist)
					and self.verify_signature):
					if f_signature in unverified_files:
						signature_file = container.extractfile(f_signature)
						signature = signature_file.read()
						signature_file.close()
						checksum_info = checksum_helper(self.settings,
							gpg_operation=checksum_helper.VERIFY,
							signature=signature)
					else:
						raise MissingSignature("%s signature not found" % f)
				else:
					checksum_info = checksum_helper(self.settings)

				# Verify current file checksum
				f_io = container.extractfile(f)
				while True:
					buffer = f_io.read(HASHING_BLOCKSIZE)
					if buffer:
						checksum_info.update(buffer)
					else:
						checksum_info.finish()
						break
				f_io.close()

				# At least one supported checksum must be checked
				verified_hash_count = 0
				for c in checksum_info.libs:
					try:
						if (checksum_info.libs[c].hexdigest().lower() ==
							manifest_record[manifest_record.index(c) + 1].lower()):
							verified_hash_count += 1
						else:
							raise DigestException("%s checksum mismatched" % f)
					except KeyError:
						# Checksum method not supported
						pass

				if verified_hash_count < 1:
					raise DigestException("%s no supported checksum found" % f)

				# Current file verified
				unverified_files.remove(f)
				unverified_manifest.remove(manifest_record)
				if f_signature in unverified_files:
					unverified_files.remove(f_signature)
					for m in unverified_manifest:
						if m[1] == f_signature:
							unverified_manifest.remove(m)
							break

		# Check if any file IN Manifest but NOT IN binary package
		if len(unverified_manifest) != 0:
			raise DigestException("Missing files: %s"
				% str(unverified_manifest))

		# Check if any file NOT IN Manifest but IN binary package
		if len(unverified_files) != 0:
			raise DigestException("Unknown files exists: %s"
				% str(unverified_files))

	def _generate_metadata_from_dir(self, metadata_dir):
		"""
		read all files in metadata_dir and return as dict
		"""
		metadata = {}
		metadata_dir = normalize_path(_unicode_decode(metadata_dir,
			encoding=_encodings['fs'], errors='strict'))
		for parent, dirs, files in os.walk(metadata_dir):
			for f in files:
				try:
					f = _unicode_decode(f, encoding=_encodings['fs'], errors='strict')
				except UnicodeDecodeError:
					continue
				with open(os.path.join(parent, f), 'rb') as metafile:
					metadata[f] = metafile.read()
		return metadata


	def _get_binary_cmd(self, compression, mode):
		"""
		get command list form portage and try match compressor
		"""
		if compression not in _compressors:
			raise InvalidCompressionMethod(compression)

		compression = _compressors[compression]
		cmd = shlex_split(varexpand(compression[mode],
			mydict=self.settings))
		# Filter empty elements that make Popen fail
		cmd = [x for x in cmd if x != ""]

		if find_binary(cmd[0]) is None:
			raise CompressorNotFound(cmd[0])

		return cmd

	def _get_compression_cmd(self, compression=None):
		"""
		return compression command for Popen
		"""
		if compression is None:
			compression = self.compression
		if compression is None:
			return None
		else:
			return self._get_binary_cmd(compression, "compress")

	def _get_decompression_cmd(self, compression=None):
		"""
		return decompression command for Popen
		"""
		if compression is None:
			compression = self.compression
		if compression is None:
			return None
		else:
			return self._get_binary_cmd(compression, "decompress")

	def _get_tar_format(self, fileobj):
		"""
		Try to detect tar version
		"""
		old_position = fileobj.tell()
		fileobj.seek(0x101)
		magic = fileobj.read(8)
		fileobj.seek(0x9c)
		typeflag = fileobj.read(1)
		fileobj.seek(old_position)

		if magic == b'ustar  \x00':
			return tarfile.GNU_FORMAT
		elif magic == b'ustar\x0000':
			if typeflag == b'x' or typeflag == b'g':
				return tarfile.PAX_FORMAT
			else:
				return tarfile.USTAR_FORMAT

		return None

	def _get_tar_format_from_stats(self, image_max_path_length,
		image_max_file_size, image_total_size):
		"""
		Choose the corresponding tar format according to
		the image information
		"""
		# Max possible size in UStar is 8 GiB (8589934591 bytes)
		# stored in 11 octets
		# Use 8000000000, just in case we need add something extra

		# Total size > 8 GiB, container need use GNU tar format
		if image_total_size < 8000000000:
			container_tar_format = tarfile.USTAR_FORMAT
		else:
			container_tar_format = tarfile.GNU_FORMAT

		# Image at least one file > 8 GiB, image need use GNU tar format
		if image_max_file_size < 8000000000:
			image_tar_format = tarfile.USTAR_FORMAT
		else:
			image_tar_format = tarfile.GNU_FORMAT

		# UStar support max 253 bytes path but split into two parts by
		# directory, so the space usually not fully usable, reduce to 200 for
		# potential issues. However if any file name or directory too long,
		# it will still causes issues.
		if image_max_path_length > 200:
			image_tar_format = tarfile.GNU_FORMAT
		return container_tar_format, image_tar_format

	def _check_pre_image_files(self, root_dir):
		"""
		Check the pre image files size and path, return the longest
		path length, largest single file size, and total files size.
		"""
		root_dir = os.path.join(normalize_path(_unicode_decode(root_dir,
			encoding=_encodings['fs'], errors='strict')), "")
		root_dir_length = len(_unicode_encode(root_dir,
			encoding=_encodings['fs'], errors='strict'))

		image_max_path_length = 0
		image_max_file_size = 0
		image_total_size = 0

		for parent, dirs, files in os.walk(root_dir):
			parent = _unicode_decode(parent, encoding=_encodings['fs'],
				errors='strict')
			for d in dirs:
				try:
					_unicode_decode(d, encoding=_encodings['fs'],
						errors='strict')
				except UnicodeDecodeError as err:
					writemsg(colorize("BAD", "\n*** %s\n\n" % err), noiselevel=-1)
					raise

				d = os.path.join(parent, d)
				path_length = len(_unicode_encode(d, encoding=_encodings['fs'],
					errors='strict')) - root_dir_length

				if path_length > image_max_path_length:
					image_max_path_length = path_length

			for f in files:
				try:
					f = _unicode_decode(f, encoding=_encodings['fs'],
						errors='strict')
				except UnicodeDecodeError as err:
					writemsg(colorize("BAD", "\n*** %s\n\n" % err), noiselevel=-1)
					raise

				f = os.path.join(parent, f)
				path_length = len(_unicode_encode(f, encoding=_encodings['fs'],
					errors='strict')) - root_dir_length

				if path_length > image_max_path_length:
					image_max_path_length = path_length

				try:
					file_size = os.path.getsize(f)
				except FileNotFoundError:
					# Ignore file not found if symlink to non-existing file
					if os.path.islink(f):
						continue
					else:
						raise
				image_total_size += file_size
				if file_size > image_max_file_size:
					image_max_file_size = file_size

		return image_max_path_length, image_max_file_size, image_total_size

	def _check_pre_quickpkg_files(self, contents, root):
		"""
		Check the pre quickpkg files size and path, return the longest
		path length, largest single file size, and total files size.
		"""
		root_dir = os.path.join(normalize_path(_unicode_decode(root,
			encoding=_encodings['fs'], errors='strict')), "")
		root_dir_length = len(_unicode_encode(root_dir,
			encoding=_encodings['fs'], errors='strict'))

		image_max_path_length = 0
		image_max_file_size = 0
		image_total_size = 0

		paths = list(contents)
		for path in paths:
			try:
				_unicode_decode(path, encoding=_encodings['fs'],
					errors='strict')
			except UnicodeDecodeError as err:
				writemsg(colorize("BAD", "\n*** %s\n\n" % err), noiselevel=-1)
				raise

			path_length = len(_unicode_encode(path, encoding=_encodings['fs'],
				errors='strict')) - root_dir_length

			if path_length > image_max_path_length:
				image_max_path_length = path_length

			if os.path.isfile(path):
				try:
					file_size = os.path.getsize(path)
				except FileNotFoundError:
					# Ignore file not found if symlink to non-existing file
					if os.path.islink(path):
						continue
					else:
						raise
				image_total_size += file_size
				if file_size > image_max_file_size:
					image_max_file_size = file_size

		return image_max_path_length, image_max_file_size, image_total_size

	def _create_tarinfo(self, file_name):
		"""
		Create new tarinfo for the new file
		"""
		if self.compression is None:
			ext = ""
		elif self.compression in self.ext_list:
			ext = self.ext_list[self.compression]
		else:
			raise InvalidCompressionMethod(self.compression)

		data_tarinfo = tarfile.TarInfo(os.path.join(
			self.base_name, file_name + '.tar' + ext))
		return data_tarinfo

	def _extract_filename_compression(self, file_name):
		"""
		Extract the file basename and compression method
		"""
		file_name = os.path.basename(file_name)
		if file_name.endswith(".tar"):
			return file_name[:-4], None

		for compression in self.ext_list:
			if file_name.endswith(".tar" + self.ext_list[compression]):
				return file_name[:-len(".tar" + self.ext_list[compression])], \
					compression

		raise InvalidCompressionMethod(file_name)

	def _get_inner_tarinfo(self, tar, file_name):
		"""
		Get inner tarinfo from given container.
		Will try get file_name from correct basename first,
		if it fail, try any file that have same name as file_name, and
		return the first one.
		"""
		if self.gpkg_version not in tar.getnames():
			raise InvalidBinaryPackageFormat("Invalid gpkg file.")

		# Try get file with correct basename
		inner_tarinfo = None
		if self.base_name is None:
			base_name = ""
		else:
			base_name = self.base_name
		all_files = tar.getmembers()
		for f in all_files:
			if os.path.dirname(f.name) == base_name:
				try:
					f_name, f_comp = self._extract_filename_compression(f.name)
				except InvalidCompressionMethod:
					continue

				if f_name == file_name:
					return f, f_comp

		# If failed, try get any file name matched
		if inner_tarinfo is None:
			for f in all_files:
				try:
					f_name, f_comp = self._extract_filename_compression(f.name)
				except InvalidCompressionMethod:
					continue
				if f_name == file_name:
					if self.base_name is not None:
						writemsg(colorize("WARN",
							'Package basename mismatched, using ' + f.name))
					self.base_name_alt = os.path.dirname(f.name)
					return f, f_comp

		# Not found
		raise FileNotFound(file_name)
