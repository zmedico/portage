
from portage.util.futures.compat_coroutine import (
	coroutine,
)

class Server(object):

	def __init__(self, loop, sockets, protocol_factory, ssl_context, backlog, ssl_handshake_timeout):
		self._loop = loop
		self._sockets = sockets
		self._active_count = 0
		self._waiters = []
		self._protocol_factory = protocol_factory
		self._backlog = backlog
		self._ssl_context = ssl_context
		self._ssl_handshake_timeout = ssl_handshake_timeout
		self._serving = False
		self._serving_forever_fut = None

	def __repr__(self):
		return '<{} sockets={}>'.format(self.__class__.__name__, repr(self.sockets))

	def _attach(self):
		assert self._sockets is not None
		self._active_count += 1

	def _detach(self):
		assert self._active_count > 0
		self._active_count -= 1
		if self._active_count == 0 and self._sockets is None:
			self._wakeup()

	def _wakeup(self):
		waiters = self._waiters
		self._waiters = None
		for waiter in waiters:
			if not waiter.done():
				waiter.set_result(waiter)

	def _start_serving(self):
		if self._serving:
			return
		self._serving = True
		for sock in self._sockets:
			sock.listen(self._backlog)
			self._loop._start_serving(
				self._protocol_factory, sock, self._ssl_context,
				self, self._backlog, self._ssl_handshake_timeout)

	def get_loop(self):
		return self._loop

	def is_serving(self):
		return self._serving

	@property
	def sockets(self):
		if self._sockets is None:
			return []
		return list(self._sockets)

	def close(self):
		sockets = self._sockets
		if sockets is None:
			return
		self._sockets = None

		for sock in sockets:
			self._loop._stop_serving(sock)

		self._serving = False

		if (self._serving_forever_fut is not None and
				not self._serving_forever_fut.done()):
			self._serving_forever_fut.cancel()
			self._serving_forever_fut = None

		if self._active_count == 0:
			self._wakeup()

	@coroutine
	def start_serving(self):
		self._start_serving()
		# Skip one loop iteration so that all 'loop.add_reader'
		# go through.
		yield tasks.sleep(0, loop=self._loop)

	@coroutine
	def serve_forever(self):
		if self._serving_forever_fut is not None:
			raise RuntimeError(
				'server {} is already being awaited on serve_forever()'.format(repr(self)))
		if self._sockets is None:
			raise RuntimeError('server {} is closed'.format(repr(self)))

		self._start_serving()
		self._serving_forever_fut = self._loop.create_future()

		try:
			yield self._serving_forever_fut
		except futures.CancelledError:
			try:
				self.close()
				yield self.wait_closed()
			finally:
				raise
		finally:
			self._serving_forever_fut = None

	@coroutine
	def wait_closed(self):
		if self._sockets is None or self._waiters is None:
			return
		waiter = self._loop.create_future()
		self._waiters.append(waiter)
		yield waiter
