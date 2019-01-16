# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import os

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'_emerge.PipeReader:PipeReader',
	'portage.util.futures:asyncio',
	'portage.util.futures.unix_events:_set_nonblocking',
)
from portage.util.futures.compat_coroutine import (
	coroutine,
	coroutine_return,
)

_DEFAULT_LIMIT = 2 ** 16  # 64 KiB


class StreamWriter(object):
	"""Wraps a Transport.

	This exposes write(), writelines(), [can_]write_eof(),
	get_extra_info() and close().  It adds drain() which returns an
	optional Future on which you can wait for flow control.  It also
	adds a transport property which references the Transport
	directly.
	"""

	def __init__(self, transport, protocol, reader, loop):
		self._transport = transport
		self._protocol = protocol
		# drain() expects that the reader has an exception() method
		assert reader is None or isinstance(reader, StreamReader)
		self._reader = reader
		self._loop = loop

	def write(self, data):
		self._transport.write(data)

	def close(self):
		return self._transport.close()

	@coroutine
	def drain(self):
		"""Flush the write buffer.

		The intended use is to write

		  w.write(data)
		  await w.drain()
		"""
		if self._reader is not None:
			exc = self._reader.exception()
			if exc is not None:
				raise exc
		if self._transport.is_closing():
			# Yield to the event loop so connection_lost() may be
			# called.  Without this, _drain_helper() would return
			# immediately, and code that calls
			#     write(...); await drain()
			# in a loop would never call connection_lost(), so it
			# would not see an error when the socket is closed.
			yield asyncio.sleep(0, loop=self._loop)
		yield self._protocol._drain_helper()


class StreamReader(object):
	def __init__(self, limit=_DEFAULT_LIMIT, loop=None):
		# The line length limit is  a security feature;
		# it also doubles as half the buffer limit.

		if limit <= 0:
			raise ValueError('Limit cannot be <= 0')

		self._limit = limit
		if loop is None:
			self._loop = asyncio.get_event_loop()
		else:
			self._loop = loop
		self._buffer = bytearray()
		self._eof = False    # Whether we're done.
		self._waiter = None  # A future used by _wait_for_data()
		self._exception = None
		self._transport = None
		self._paused = False

	@coroutine
	def _wait_for_data(self, func_name):
		"""Wait until feed_data() or feed_eof() is called.

		If stream was paused, automatically resume it.
		"""
		# StreamReader uses a future to link the protocol feed_data() method
		# to a read coroutine. Running two read coroutines at the same time
		# would have an unexpected behaviour. It would not possible to know
		# which coroutine would get the next data.
		if self._waiter is not None:
			raise RuntimeError(
				'{}() called while another coroutine is already waiting for incoming data'.format(func_name))

		assert not self._eof, '_wait_for_data after EOF'

		# Waiting for data while paused will make deadlock, so prevent it.
		# This is essential for readexactly(n) for case when n > self._limit.
		if self._paused:
			self._paused = False
			self._transport.resume_reading()

		self._waiter = self._loop.create_future()
		try:
			yield self._waiter
		finally:
			self._waiter = None

	@coroutine
	def read(self, n=-1):
		"""Read up to `n` bytes from the stream.

		If n is not provided, or set to -1, read until EOF and return all read
		bytes. If the EOF was received and the internal buffer is empty, return
		an empty bytes object.

		If n is zero, return empty bytes object immediately.

		If n is positive, this function try to read `n` bytes, and may return
		less or equal bytes than requested, but at least one byte. If EOF was
		received before any byte is read, this function returns empty byte
		object.

		Returned value is not limited with limit, configured at stream
		creation.

		If stream was paused, this function will automatically resume it if
		needed.
		"""

		if self._exception is not None:
			raise self._exception

		if n == 0:
			coroutine_return(b'')

		if n < 0:
			# This used to just loop creating a new waiter hoping to
			# collect everything in self._buffer, but that would
			# deadlock if the subprocess sends more than self.limit
			# bytes.  So just call self.read(self._limit) until EOF.
			blocks = []
			while True:
				block = yield self.read(self._limit)
				if not block:
					break
				blocks.append(block)
			coroutine_return(b''.join(blocks))

		if not self._buffer and not self._eof:
			yield self._wait_for_data('read')

		# This will work right even if buffer is less than n bytes
		data = bytes(self._buffer[:n])
		del self._buffer[:n]

		self._maybe_resume_transport()
		coroutine_return(data)

	@coroutine
	def readexactly(self, n):
		"""Read exactly `n` bytes.

		Raise an IncompleteReadError if EOF is reached before `n` bytes can be
		read. The IncompleteReadError.partial attribute of the exception will
		contain the partial read bytes.

		if n is zero, return empty bytes object.

		Returned value is not limited with limit, configured at stream
		creation.

		If stream was paused, this function will automatically resume it if
		needed.
		"""
		if n < 0:
			raise ValueError('readexactly size can not be less than zero')

		if self._exception is not None:
			raise self._exception

		if n == 0:
			coroutine_return(b'')

		while len(self._buffer) < n:
			if self._eof:
				incomplete = bytes(self._buffer)
				self._buffer.clear()
				raise IncompleteReadError(incomplete, n)

			yield self._wait_for_data('readexactly')

		if len(self._buffer) == n:
			data = bytes(self._buffer)
			self._buffer.clear()
		else:
			data = bytes(self._buffer[:n])
			del self._buffer[:n]
		self._maybe_resume_transport()
		coroutine_return(data)


@coroutine
def open_connection(host=None, port=None, loop=None, limit=_DEFAULT_LIMIT, **kwds):
	"""A wrapper for create_connection() returning a (reader, writer) pair.

	The reader returned is a StreamReader instance; the writer is a
	StreamWriter instance.

	The arguments are all the usual arguments to create_connection()
	except protocol_factory; most common are positional host and port,
	with various optional keyword arguments following.

	Additional optional keyword arguments are loop (to set the event loop
	instance to use) and limit (to set the buffer limit passed to the
	StreamReader).

	(If you want to customize the StreamReader and/or
	StreamReaderProtocol classes, just copy the code -- there's
	really nothing special here except some convenience.)
	"""
	if loop is None:
		loop = asyncio.get_event_loop()
	reader = StreamReader(limit=limit, loop=loop)
	protocol = StreamReaderProtocol(reader, loop=loop)
	transport, _ = (yield loop.create_connection(
		lambda: protocol, host, port, **kwds))
	writer = StreamWriter(transport, protocol, reader, loop)
	coroutine_return((reader, writer))


@coroutine
def start_unix_server(client_connected_cb, path=None, loop=None, limit=_DEFAULT_LIMIT, **kwds):
	"""Similar to `start_server` but works with UNIX Domain Sockets."""
	if not hasattr(loop, 'create_unix_server'):
		raise NotImplementedError
	if loop is None:
		loop = asyncio.get_event_loop()

	def factory():
		reader = StreamReader(limit=limit, loop=loop)
		protocol = StreamReaderProtocol(reader, client_connected_cb, loop=loop)
		return protocol

	result = (yield loop.create_unix_server(factory, path, **kwds))
	coroutine_return(result)


def _reader(input_file, loop=None):
	"""
	Asynchronously read a binary input file, and close it when
	it reaches EOF.

	@param input_file: binary input file descriptor
	@type input_file: file or int
	@param loop: asyncio.AbstractEventLoop (or compatible)
	@type loop: event loop
	@return: bytes
	@rtype: asyncio.Future (or compatible)
	"""
	loop = asyncio._wrap_loop(loop)
	future = loop.create_future()
	_Reader(future, input_file, loop)
	return future


class _Reader(object):
	def __init__(self, future, input_file, loop):
		self._future = future
		self._pipe_reader = PipeReader(
			input_files={'input_file':input_file}, scheduler=loop)

		self._future.add_done_callback(self._cancel_callback)
		self._pipe_reader.addExitListener(self._eof)
		self._pipe_reader.start()

	def _cancel_callback(self, future):
		if future.cancelled():
			self._cancel()

	def _eof(self, pipe_reader):
		self._pipe_reader = None
		self._future.set_result(pipe_reader.getvalue())

	def _cancel(self):
		if self._pipe_reader is not None and self._pipe_reader.poll() is None:
			self._pipe_reader.removeExitListener(self._eof)
			self._pipe_reader.cancel()
			self._pipe_reader = None


@coroutine
def _writer(output_file, content, loop=None):
	"""
	Asynchronously write bytes to output file, and close it when
	done. If an EnvironmentError other than EAGAIN is encountered,
	which typically indicates that the other end of the pipe has
	close, the error is raised. This function is a coroutine.

	@param output_file: output file descriptor
	@type output_file: file or int
	@param content: content to write
	@type content: bytes
	@param loop: asyncio.AbstractEventLoop (or compatible)
	@type loop: event loop
	"""
	fd = output_file if isinstance(output_file, int) else output_file.fileno()
	_set_nonblocking(fd)
	loop = asyncio._wrap_loop(loop)
	try:
		while content:
			waiter = loop.create_future()
			loop.add_writer(fd, lambda: waiter.set_result(None))
			try:
				yield waiter
				while content:
					try:
						content = content[os.write(fd, content):]
					except EnvironmentError as e:
						if e.errno == errno.EAGAIN:
							break
						else:
							raise
			finally:
				loop.remove_writer(fd)
	except GeneratorExit:
		raise
	finally:
		os.close(output_file) if isinstance(output_file, int) else output_file.close()
