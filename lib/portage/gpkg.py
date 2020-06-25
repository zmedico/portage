# Copyright 2001-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import tarfile
import io
from datetime import datetime
import warnings
import threading
import subprocess
import errno
import pwd
import grp
import stat
import sys

from portage import os
from portage import shutil
from portage import normalize_path
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.exception import InvalidData, FileNotFound, \
	IncorrectParameter, InvalidBinaryPackageFormat, \
	InvalidCompressionMethod, CompressorNotFound, \
	CompressorOperationFailed
from portage.output import colorize
from portage.util._urlopen import urlopen
from portage.util import writemsg
from portage.util import ensure_dirs, shlex_split, varexpand
from portage.util.compression_probe import _compressors
from portage.process import find_binary


class tar_stream_writer(object):
	"""
	Helper function that return a file-like object which
	allowed streaming add new file to tar with optional external
	program compression, without prior knows the file size.

	Example:
	Add "bin/emerge" as "emerge.tar.gz" to portage.tar using gzip compression

	container = tarfile.open("portage.tar", "w")
	file_tarinfo = tarfile.TarInfo("emerge.tar.gz")
	with tar_stream_writer(file_tarinfo, container,
		tarfile.USTAR_FORMAT, ["gzip"]) as writer:
		with tarfile.open(mode='w|', fileobj=writer) as inner_tar:
			inner_tar.add("bin/emerge")
	"""
	def __init__(self, tarinfo, container, tar_format, cmd=None):
		"""
		tarinfo should be the to be added file info.
		container should be the exists container tarfile object.
		cmd is optional external compressor command.
		"""
		self.container = container
		self.tarinfo = tarinfo
		self.tar_format = tar_format
		self.closed = False

		# record container end position
		self.container.fileobj.seek(0, io.SEEK_END)
		self.begin_position = self.container.fileobj.tell()
		self.end_position = 0
		self.file_size = 0

		# write tar header without size
		tar_header = self.tarinfo.tobuf(self.tar_format,
			self.container.encoding,
			self.container.errors)
		self.header_size = len(tar_header)
		self.container.fileobj.write(tar_header)
		self.container.fileobj.flush()
		self.container.offset += self.header_size

		# start external compressor if needed
		if cmd is None:
			self.proc = None
			self.output = self.container.fileobj
		else:
			self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
				stdout=self.container.fileobj)
			self.output = self.proc.stdin

	def __del__(self):
		self.close()

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		self.close()

	def write(self, data):
		"""
		Write data to tarfile or external compressor stdin
		"""
		if self.closed:
			raise OSError("writer closed")
		else:
			self.output.write(data)

	def close(self):
		"""
		Update the new file tar header when close
		"""
		if self.closed:
			return

		# wait compressor exit
		if self.proc is not None:
			self.proc.stdin.close()
			if self.proc.wait() != os.EX_OK:
				raise CompressorOperationFailed("compression failed")

		# get container end position and calculate file size
		self.container.fileobj.seek(0, io.SEEK_END)
		self.end_position = self.container.fileobj.tell()
		self.file_size = self.end_position - self.begin_position \
			- self.header_size
		self.tarinfo.size = self.file_size

		# tar block is 512, need padding \0
		_, remainder = divmod(self.file_size, 512)
		if remainder > 0:
			padding_size = 512 - remainder
			self.container.fileobj.write(b'\0' * padding_size)
			self.container.offset += padding_size
			self.container.fileobj.flush()

		# update tar header
		tar_header = self.tarinfo.tobuf(self.tar_format,
			self.container.encoding,
			self.container.errors)
		self.container.fileobj.seek(self.begin_position)
		self.container.fileobj.write(tar_header)
		self.container.fileobj.seek(0, io.SEEK_END)
		self.container.fileobj.flush()
		self.container.offset = self.container.fileobj.tell()
		self.closed = True

		# add tarinfo to tarfile
		self.container.members.append(self.tarinfo)


class tar_stream_reader(object):
	"""
	Helper function that return a file-like object which
	allowed stream reading file in tar with optional external
	program decompression.

	Example:
	Extract "bin/emerge" from "emerge.tar.gz" in portage.tar 
	using gzip decompression

	container = tarfile.open("portage.tar", "r")
	with tar_stream_reader(container, ["gzip", "-d"]) as reader:
		with tarfile.open(mode='r|', fileobj=reader) as inner_tar:
			inner_tar.extract("bin/emerge")
	"""
	def __init__(self, fileobj, cmd=None):
		"""
		fileobj should be a file-like object that have read().
		cmd is optional external decompressor command.
		"""
		self.fileobj = fileobj
		self.closed = False
		self.cmd = cmd
		self.killed = False

		if cmd is None:
			self.read_io = fileobj
			self.proc = None
		else:
			# start external decompressor
			self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
				stdout=subprocess.PIPE)
			self.read_io = self.proc.stdout
			# start stdin block writing thread
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
			self.proc.stdin.write(self.fileobj.read())
			self.proc.stdin.flush()
		except BrokenPipeError:
			if self.killed is False:
				raise CompressorOperationFailed("PIPE broken")

		# close stdin after finished
		self.proc.stdin.close()

	def kill(self):
		# kill proc if any error happened in python
		if self.proc is not None:
			self.killed = True
			self.proc.kill()
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
		if self.closed:
			return

		if self.proc is not None:
			self.thread.join()
			self.proc.stdout.close()
			if self.proc.wait() != os.EX_OK:
				raise CompressorOperationFailed("decompression failed")
		self.closed = True


class gpkg(object):
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

		# compression is the compression algorithm, if set to None will 
		# not use compression.
		self.compression = self.settings.get("BINPKG_COMPRESS", None)
		if self.compression in ["", "none"]:
			self.compression = None

		self.compresslevel = self.settings.get("BINPKG_COMPRESS_LEVEL", 9)
		try:
			self.compresslevel = int(self.compresslevel)
		except ValueError:
			self.compresslevel = 9

		# create_signature is whether create signature for the package or not.
		self.create_signature = self.settings.get("BINPKG_CREATE_SIGNING", False)
		if not isinstance(self.create_signature, bool):
			self.create_signature = self.create_signature.lower()
			if self.create_signature in ["", "false", "0"]:
				self.create_signature = False
			elif self.create_signature in ["1", "true"]:
				self.create_signature = True
			else:
				raise IncorrectParameter("Invalid BINPKG_CREATE_SIGNING flag: "
					+ self.create_signature)

		# request_signature is whether signature files are mandatory.
		# If set true, any missing signature file will cause reject processing.
		self.request_signature = self.settings.get("BINPKG_REQUEST_SIGNING", False)
		if not isinstance(self.request_signature, bool):
			self.request_signature = self.request_signature.lower()
			if self.request_signature in ["", "false", "0"]:
				self.request_signature = False
			elif self.request_signature in ["1", "true"]:
				self.request_signature = True
			else:
				raise IncorrectParameter("Invalid BINPKG_REQUEST_SIGNING flag: "
					+ self.request_signature)

		# verify_signature is whether verify package signature or not,
		# In rare case user may want to ignore signature,
		# E.g. package with expired signature.
		self.verify_signature = self.settings.get("BINPKG_VERIFY_SIGNING", True)
		if not isinstance(self.verify_signature, bool):
			self.verify_signature = self.verify_signature.lower()
			if self.verify_signature in ["false", "0"]:
				self.verify_signature = False
			elif self.verify_signature in ["", "1", "true"]:
				self.verify_signature = True
			else:
				raise IncorrectParameter("Invalid BINPKG_VERIFY_SIGNING flag: "
					+ self.verify_signature)

		self.ext_list = {"gzip": ".gz", "bzip2": ".bz2", "lz4": ".lz4",
			"lzip": ".lz", "lzop": ".lzo", "xz": ".xz", "zstd": ".zst"}

	def unpack_metadata(self, dest_dir=None):
		"""
		Unpack metadata to dest_dir.
		If dest_dir is None, return files and values in dict.
		The dict key will be UTF-8, not bytes.
		"""
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
		"""
		# the init download file head size
		init_size = 51200

		# load remote container
		container_file = io.BytesIO(urlopen(url, headers={
			'Range': 'bytes=0-' + str(init_size)}).read())

		# check gpkg and metadata
		with tarfile.open(mode='r', fileobj=container_file) as container:
			if self.gpkg_version not in container.getnames():
				raise InvalidBinaryPackageFormat("Invalid gpkg file.")

			metadata_tarinfo, metadata_comp = self._get_inner_tarinfo(
				container, 'metadata')

			end_size = metadata_tarinfo.offset_data \
				+ metadata_tarinfo.size + 2048
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

		# reload and process full metadata
		with tarfile.open(mode='r', fileobj=container_file) as container:
			metadata_tarinfo, metadata_comp = self._get_inner_tarinfo(
				container, 'metadata')

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

		if self.create_signature:
			pass

		# image
		image_tarinfo = self._create_tarinfo("image")
		image_tarinfo.mtime = datetime.utcnow().timestamp()
		with tar_stream_writer(image_tarinfo, container,
			image_tar_format, compression_cmd) as image_writer:
			with tarfile.open(mode='w|', fileobj=image_writer,
				format=image_tar_format) as image_tar:
				image_tar.add(root_dir, ".", recursive=True)

		container.close()

	def decompress(self, decompress_dir):
		"""
		decompress current gpkg to decompress_dir
		"""
		decompress_dir = normalize_path(_unicode_decode(decompress_dir,
			encoding=_encodings['fs'], errors='strict'))

		if self.gpkg_file is None:
			raise FileNotFound("no gpkg file provided")

		with tarfile.open(self.gpkg_file, 'r') as container:
			image_tarinfo, image_comp = \
				self._get_inner_tarinfo(container, 'image')

			with tar_stream_reader(container.extractfile(image_tarinfo),
				self._get_decompression_cmd()) as image_tar:

				with tarfile.open(mode='r|', fileobj=image_tar) as image:
					try:
						image.extractall(decompress_dir)
					finally:
						image_tar.kill()

	def update_metadata(self, metadata):
		"""
		Update metadata in the gpkg file.
		"""
		if self.gpkg_file is None:
			raise FileNotFound("no gpkg file provided")

		if not os.path.isfile(self.gpkg_file):
			raise FileNotFound(self.gpkg_file)

		with tarfile.open(self.gpkg_file, 'r') as container:
			if self.gpkg_version not in container.getnames():
				raise InvalidBinaryPackageFormat("Invalid gpkg file.")

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

			if self.create_signature:
				pass

			# reuse image
			with tarfile.open(self.gpkg_file, 'r') \
				as container_old:
				image_old_tarinfo, image_old_comp = \
					self._get_inner_tarinfo(container_old, 'image')
				
				container.addfile(image_old_tarinfo,
					container_old.extractfile(image_old_tarinfo))

				image_sign_old_name = image_old_tarinfo.name + ".sig"
				if image_sign_old_name in container_old.getnames():
					image_sign_tarinfo = container_old.getmember(
						image_sign_old_name)
					container.addfile(image_sign_tarinfo,
						container_old.extractfile(image_sign_tarinfo))

		shutil.move(tmp_gpkg_file_name, self.gpkg_file)

	def _add_metadata(self, container, metadata, compression_cmd):
		"""
		add metadata to container
		"""
		if metadata is None:
			metadata = {}
		metadata_tarinfo = self._create_tarinfo('metadata')
		metadata_tarinfo.mtime = datetime.utcnow().timestamp()

		with tar_stream_writer(metadata_tarinfo, container,
			tarfile.USTAR_FORMAT, compression_cmd) as metadata_writer:
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
		paths = list(contents)
		paths.sort()
		image_tarinfo = self._create_tarinfo("image")
		image_tarinfo.mtime = datetime.utcnow().timestamp()
		with tar_stream_writer(image_tarinfo, container,
			image_tar_format, compression_cmd) as image_writer:
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
		container.close()

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

		return(cmd)

	def _get_compression_cmd(self, compression=None):
		"""
		return compression command for Popen
		"""
		if compression is None:
			compression = self.compression
		if compression is None:
			return(None)
		else:
			return self._get_binary_cmd(compression, "compress")

	def _get_decompression_cmd(self, compression=None):
		"""
		return decompression command for Popen
		"""
		if compression is None:
			compression = self.compression
		if compression is None:
			return(None)
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
			return(tarfile.GNU_FORMAT)
		elif magic == b'ustar\x0000':
			if typeflag == b'x' or typeflag == b'g':
				return(tarfile.PAX_FORMAT)
			else:
				return(tarfile.USTAR_FORMAT)

		return(None)

	def _get_tar_format_from_stats(self, image_max_path_length, 
		image_max_file_size, image_total_size):
		"""
		Choose the corresponding tar format according to 
		the image information
		"""
		# max possible size in UStar is 8 GiB (8589934591 bytes)
		# stored in 11 octets
		# use 8000000000, just in case we need add something extra

		# total size > 8 GiB, container need use GNU tar format
		if image_total_size < 8000000000:
			container_tar_format = tarfile.USTAR_FORMAT
		else:
			container_tar_format = tarfile.GNU_FORMAT

		# image at least one file > 8 GiB, image need use GNU tar format
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
					# ignore file not found if symlink to non-existing file
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
					# ignore file not found if symlink to non-existing file
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
		return(data_tarinfo)

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

		# try get file with correct basename
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

		# if failed, try get any file name matched
		if inner_tarinfo is None:
			for f in all_files: 
				try:
					f_name, f_comp = self._extract_filename_compression(f.name)
				except InvalidCompressionMethod:
					continue
				if f_name == file_name:
					if self.base_name is not None:
						warnings.warn('Package basename mismatched, using ' +
							f.name, RuntimeWarning)
					self.base_name_alt = os.path.dirname(f.name)
					return f, f_comp

		# not found
		raise FileNotFound(file_name)
