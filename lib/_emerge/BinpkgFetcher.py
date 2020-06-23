# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools

from _emerge.AsynchronousLock import AsynchronousLock
from _emerge.CompositeTask import CompositeTask
from _emerge.SpawnProcess import SpawnProcess
from urllib.parse import urlparse as urllib_parse_urlparse
import stat
import sys
import portage
from portage import os
from portage.const import (SUPPORTED_XPAK_EXTENSIONS,
	SUPPORTED_GPKG_EXTENSIONS)
from portage.exception import InvalidBinaryPackageFormat
from portage.util._async.AsyncTaskFuture import AsyncTaskFuture
from portage.util._pty import _create_pty_or_pipe


class BinpkgFetcher(CompositeTask):

	__slots__ = ("pkg", "pretend", "logfile", "pkg_path",
		"binpkg_format", "binpkg_format_pending", "retry")

	def __init__(self, **kwargs):
		CompositeTask.__init__(self, **kwargs)
		self.binpkg_format_pending = ["xpak", "gpkg"]
		self.retry = True

		pkg = self.pkg
		bintree = pkg.root_config.trees["bintree"]
		settings = bintree.settings
		self.binpkg_format = settings.get("BINPKG_FORMAT", "xpak")
		binpkg_path = None

		if bintree._remote_has_index:
			instance_key = bintree.dbapi._instance_key(pkg.cpv)
			binpkg_path = bintree._remotepkgs[instance_key].get("PATH")
			if binpkg_path:
				# use binhost index format, and do not try other formats
				self.pkg_path = os.path.basename(binpkg_path) + ".partial"
				self.retry = False

		if not binpkg_path:
			# try use local default format
			self.pkg_path = pkg.root_config.trees["bintree"].getname(
				pkg.cpv, binpkg_format=self.binpkg_format) + ".partial"
			self.binpkg_format_pending.remove(self.binpkg_format)

	def _start(self):
		fetcher = _BinpkgFetcherProcess(background=self.background,
			binpkg_format=self.binpkg_format,
			logfile=self.logfile, pkg=self.pkg, pkg_path=self.pkg_path,
			pretend=self.pretend, scheduler=self.scheduler)

		if not self.pretend:
			portage.util.ensure_dirs(os.path.dirname(self.pkg_path))
			if "distlocks" in self.pkg.root_config.settings.features:
				self._start_task(
					AsyncTaskFuture(future=fetcher.async_lock()),
					functools.partial(self._start_locked, fetcher))
				return

		self._start_task(fetcher, self._fetcher_exit)

	def _start_locked(self, fetcher, lock_task):
		self._assert_current(lock_task)
		if lock_task.cancelled:
			self._default_final_exit(lock_task)
			return

		lock_task.future.result()
		self._start_task(fetcher, self._fetcher_exit)

	def _fetcher_exit(self, fetcher):
		self._assert_current(fetcher)
		if not self.pretend and fetcher.returncode == os.EX_OK:
			fetcher.sync_timestamp()
		if fetcher.locked:
			self._start_task(
				AsyncTaskFuture(future=fetcher.async_unlock()),
				functools.partial(self._fetcher_exit_unlocked, fetcher))
		else:
			self._fetcher_exit_unlocked(fetcher)

	def _fetcher_exit_unlocked(self, fetcher, unlock_task=None):
		if not self.pretend and fetcher.returncode != os.EX_OK:
			if self.retry and len(self.binpkg_format_pending) > 0:
				# try other formats if current fetcher failed
				self.binpkg_format = self.binpkg_format_pending.pop()
				self.pkg_path = pkg.root_config.trees["bintree"].getname(
					self.pkg.cpv, 
					binpkg_format=self.binpkg_format) + ".partial"
				self._start()
				return

		if unlock_task is not None:
			self._assert_current(unlock_task)
			if unlock_task.cancelled:
				self._default_final_exit(unlock_task)
				return

			unlock_task.future.result()

		self._current_task = None
		self.returncode = fetcher.returncode
		self._async_wait()


class _BinpkgFetcherProcess(SpawnProcess):

	__slots__ = ("pkg", "pretend", "locked", "pkg_path", "_lock_obj",
		"binpkg_format")

	def _start(self):
		pkg = self.pkg
		pretend = self.pretend
		bintree = pkg.root_config.trees["bintree"]
		settings = bintree.settings
		pkg_path = self.pkg_path
		binpkg_format = self.binpkg_format
		if binpkg_format not in ("xpak", "gpkg"):
			raise InvalidBinaryPackageFormat(binpkg_format)

		exists = os.path.exists(pkg_path)
		resume = exists and os.path.basename(pkg_path) in bintree.invalids
		if not (pretend or resume):
			# Remove existing file or broken symlink.
			try:
				os.unlink(pkg_path)
			except OSError:
				pass

		# urljoin doesn't work correctly with
		# unrecognized protocols like sftp
		if bintree._remote_has_index:
			instance_key = bintree.dbapi._instance_key(pkg.cpv)
			rel_uri = bintree._remotepkgs[instance_key].get("PATH")
			if not rel_uri:
				if binpkg_format == "xpak":
					rel_uri = pkg.cpv + ".tbz2"
				elif binpkg_format == "gpkg":
					rel_uri = pkg.cpv + ".gpkg.tar"
			remote_base_uri = bintree._remotepkgs[
				instance_key]["BASE_URI"]
			uri = remote_base_uri.rstrip("/") + "/" + rel_uri.lstrip("/")
		else:
			if binpkg_format == "xpak":
				uri = settings["PORTAGE_BINHOST"].rstrip("/") + \
					"/" + pkg.pf + ".tbz2"
			elif binpkg_format == "gpkg":
				uri = settings["PORTAGE_BINHOST"].rstrip("/") + \
					"/" + pkg.pf + ".gpkg.tar"

		if pretend:
			portage.writemsg_stdout("\n%s\n" % uri, noiselevel=-1)
			self.returncode = os.EX_OK
			self._async_wait()
			return

		protocol = urllib_parse_urlparse(uri)[0]
		fcmd_prefix = "FETCHCOMMAND"
		if resume:
			fcmd_prefix = "RESUMECOMMAND"
		fcmd = settings.get(fcmd_prefix + "_" + protocol.upper())
		if not fcmd:
			fcmd = settings.get(fcmd_prefix)

		fcmd_vars = {
			"DISTDIR" : os.path.dirname(pkg_path),
			"URI"     : uri,
			"FILE"    : os.path.basename(pkg_path)
		}

		for k in ("PORTAGE_SSH_OPTS",):
			v = settings.get(k)
			if v is not None:
				fcmd_vars[k] = v

		fetch_env = dict(settings.items())
		fetch_args = [portage.util.varexpand(x, mydict=fcmd_vars) \
			for x in portage.util.shlex_split(fcmd)]

		if self.fd_pipes is None:
			self.fd_pipes = {}
		fd_pipes = self.fd_pipes

		# Redirect all output to stdout since some fetchers like
		# wget pollute stderr (if portage detects a problem then it
		# can send it's own message to stderr).
		fd_pipes.setdefault(0, portage._get_stdin().fileno())
		fd_pipes.setdefault(1, sys.__stdout__.fileno())
		fd_pipes.setdefault(2, sys.__stdout__.fileno())

		self.args = fetch_args
		self.env = fetch_env
		if settings.selinux_enabled():
			self._selinux_type = settings["PORTAGE_FETCH_T"]
		self.log_filter_file = settings.get('PORTAGE_LOG_FILTER_FILE_CMD')
		SpawnProcess._start(self)

	def _pipe(self, fd_pipes):
		"""When appropriate, use a pty so that fetcher progress bars,
		like wget has, will work properly."""
		if self.background or not sys.__stdout__.isatty():
			# When the output only goes to a log file,
			# there's no point in creating a pty.
			return os.pipe()
		stdout_pipe = None
		if not self.background:
			stdout_pipe = fd_pipes.get(1)
		got_pty, master_fd, slave_fd = \
			_create_pty_or_pipe(copy_term_size=stdout_pipe)
		return (master_fd, slave_fd)

	def sync_timestamp(self):
			# If possible, update the mtime to match the remote package if
			# the fetcher didn't already do it automatically.
			bintree = self.pkg.root_config.trees["bintree"]
			if bintree._remote_has_index:
				remote_mtime = bintree._remotepkgs[
					bintree.dbapi._instance_key(
					self.pkg.cpv)].get("_mtime_")
				if remote_mtime is not None:
					try:
						remote_mtime = int(remote_mtime)
					except ValueError:
						pass
					else:
						try:
							local_mtime = os.stat(self.pkg_path)[stat.ST_MTIME]
						except OSError:
							pass
						else:
							if remote_mtime != local_mtime:
								try:
									os.utime(self.pkg_path,
										(remote_mtime, remote_mtime))
								except OSError:
									pass

	def async_lock(self):
		"""
		This raises an AlreadyLocked exception if lock() is called
		while a lock is already held. In order to avoid this, call
		unlock() or check whether the "locked" attribute is True
		or False before calling lock().
		"""
		if self._lock_obj is not None:
			raise self.AlreadyLocked((self._lock_obj,))

		result = self.scheduler.create_future()

		def acquired_lock(async_lock):
			if async_lock.wait() == os.EX_OK:
				self.locked = True
				result.set_result(None)
			else:
				result.set_exception(AssertionError(
					"AsynchronousLock failed with returncode %s"
					% (async_lock.returncode,)))

		self._lock_obj = AsynchronousLock(path=self.pkg_path,
			scheduler=self.scheduler)
		self._lock_obj.addExitListener(acquired_lock)
		self._lock_obj.start()
		return result

	class AlreadyLocked(portage.exception.PortageException):
		pass

	def async_unlock(self):
		if self._lock_obj is None:
			raise AssertionError('already unlocked')
		result = self._lock_obj.async_unlock()
		self._lock_obj = None
		self.locked = False
		return result
