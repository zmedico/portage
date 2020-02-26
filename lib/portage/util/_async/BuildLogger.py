# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'_emerge.SpawnProcess:SpawnProcess',
)

from portage import os
from portage.util import shlex_split
from _emerge.CompositeTask import CompositeTask
from portage.util._async.AsyncTaskFuture import AsyncTaskFuture
from portage.util._async.PipeLogger import PipeLogger
from portage.util.futures import asyncio
from portage.util.futures.compat_coroutine import coroutine


class BuildLogger(CompositeTask):
	"""
	Write to a log file, with compression support provided by PipeLogger.
	If the log_filter_file parameter is specified, then it is interpreted
	as a command to execute which filters log output (see the
	PORTAGE_LOG_FILTER_FILE variable in make.conf(5)). The stdin property
	provides access to a binary file object (refers to a pipe) that log
	content should be written to (usually redirected from subprocess
	stdout and stderr streams).
	"""

	__slots__ = ('env', 'log_path', 'log_filter_file', '_pipe_logger', '_filter_proc', '_stdin')

	@property
	def stdin(self):
		return self._stdin

	def _start(self):
		self.scheduler.run_until_complete(self._async_start())

	@coroutine
	def _async_start(self):
		if self.log_path is not None:
			log_filter_file = self.log_filter_file
			if log_filter_file is not None:
				split_value = shlex_split(log_filter_file)
				log_filter_file = split_value if split_value else None
			if log_filter_file:
				filter_input, stdin = os.pipe()
				log_input, filter_output = os.pipe()
				self._filter_proc = SpawnProcess(
					args=log_filter_file,
					env=self.env,
					fd_pipes={0: filter_input, 1: filter_output, 2: filter_output},
					scheduler=self.scheduler)
				try:
					yield self._filter_proc.async_start()
				except portage.exception.CommandNotFound:
					self._filter_proc._unregister()
					self._filter_proc = None
					os.close(filter_input)
					os.close(stdin)
					os.close(log_input)
					os.close(filter_output)
				else:
					self._stdin = os.fdopen(stdin, 'wb', 0)
					os.close(filter_input)
					os.close(filter_output)
					# Create a PipeLogger instance to read output from
					# self._filter_proc and log it. Set background=True
					# so that this instance does not log to stdout.
					self._pipe_logger = PipeLogger(background=True,
						scheduler=self.scheduler, input_fd=log_input,
						log_file_path=self.log_path)
					yield self._pipe_logger.async_start()
					self._start_task(AsyncTaskFuture(future=self._pipe_logger_wait()), self._pipe_logger_exit)

		if self._stdin is None:
			# Since log_filter_file is unspecified or refers to a file that
			# was not found, create a pipe that logs directly to a PipeLogger
			# instance.
			log_input, stdin = os.pipe()
			self._stdin = os.fdopen(stdin, 'wb', 0)
			self._pipe_logger = PipeLogger(background=True,
				scheduler=self.scheduler, input_fd=log_input,
				log_file_path=self.log_path)
			yield self._pipe_logger.async_start()
			self._start_task(AsyncTaskFuture(future=self._pipe_logger_wait()), self._pipe_logger_exit)

	def _cancel(self):
		if self._pipe_logger is not None and self._pipe_logger.poll() is None:
			self._pipe_logger.cancel()
		if self._filter_proc is not None and self._filter_proc.poll() is None:
			self._filter_proc.cancel()
		CompositeTask._cancel(self)

	@coroutine
	def _pipe_logger_wait(self):
		yield self._pipe_logger.async_wait()
		if self._filter_proc is not None:
			yield self._filter_proc.async_wait()

	def _pipe_logger_exit(self, pipe_logger):
		try:
			pipe_logger.future.result()
		except asyncio.CancelledError:
			self.cancel()
			self._was_cancelled()
		self._pipe_logger = None
		self.returncode = self.returncode or 0
		self._async_wait()

