#!/usr/bin/env python
# SOCKSv5 proxy server for network-sandbox
# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import asyncio
import errno
import functools
import logging
import os
import socket
import struct
import sys

#if hasattr(asyncio, 'ensure_future'):
#	# Python >=3.4.4.
#	asyncio_ensure_future = asyncio.ensure_future
#else:
#	# getattr() necessary because async is a keyword in Python >=3.7.
#	asyncio_ensure_future = getattr(asyncio, 'async')

try:
	current_task = asyncio.current_task
except AttributeError:
	# Deprecated since Python 3.7
	current_task = asyncio.Task.current_task

from portage.util.futures import asyncio
from portage.util.futures.unix_events import _set_nonblocking

asyncio_ensure_future = asyncio.ensure_future

if not hasattr(asyncio, 'coroutine'):
	import asyncio as _real_asyncio
	asyncio.coroutine = _real_asyncio.coroutine
	asyncio.start_server = _real_asyncio.start_server
	asyncio.start_unix_server = _real_asyncio.start_unix_server
	asyncio.open_connection = _real_asyncio.open_connection


class Socks5Server(object):
	"""
	An asynchronous SOCKSv5 server.
	"""

	@asyncio.coroutine
	def handle_proxy_conn(self, reader, writer):
		"""
		Handle incoming client connection. Perform SOCKSv5 request
		exchange, open a proxied connection and start relaying.

		@param reader: Read side of the socket
		@type reader: asyncio.StreamReader
		@param writer: Write side of the socket
		@type writer: asyncio.StreamWriter
		"""

		try:
			# SOCKS hello
			data = yield from reader.readexactly(2)
			vers, method_no = struct.unpack('!BB', data)

			if vers != 0x05:
				# disconnect on invalid packet -- we have no clue how
				# to reply in alien :)
				writer.close()
				return

			# ...and auth method list
			data = yield from reader.readexactly(method_no)
			for method in data:
				if method == 0x00:
					break
			else:
				# no supported method
				method = 0xFF

			# auth reply
			repl = struct.pack('!BB', 0x05, method)
			writer.write(repl)
			yield from writer.drain()
			if method == 0xFF:
				writer.close()
				return

			# request
			data = yield from reader.readexactly(4)
			vers, cmd, rsv, atyp = struct.unpack('!BBBB', data)

			if vers != 0x05 or rsv != 0x00:
				# disconnect on malformed packet
				self.close()
				return

			# figure out if we can handle it
			rpl = 0x00
			if cmd != 0x01:  # CONNECT
				rpl = 0x07  # command not supported
			elif atyp == 0x01:  # IPv4
				data = yield from reader.readexactly(4)
				addr = socket.inet_ntoa(data)
			elif atyp == 0x03:  # domain name
				data = yield from reader.readexactly(1)
				addr_len, = struct.unpack('!B', data)
				addr = yield from reader.readexactly(addr_len)
				try:
					addr = addr.decode('idna')
				except UnicodeDecodeError:
					rpl = 0x04  # host unreachable

			elif atyp == 0x04:  # IPv6
				data = yield from reader.readexactly(16)
				addr = socket.inet_ntop(socket.AF_INET6, data)
			else:
				rpl = 0x08  # address type not supported

			# try to connect if we can handle it
			if rpl == 0x00:
				data = yield from reader.readexactly(2)
				port, = struct.unpack('!H', data)

				try:
					# open a proxied connection
					proxied_reader, proxied_writer = yield from asyncio.open_connection(
							addr, port)
				except (socket.gaierror, socket.herror):
					# DNS failure
					rpl = 0x04  # host unreachable
				except OSError as e:
					# connection failure
					if e.errno in (errno.ENETUNREACH, errno.ENETDOWN):
						rpl = 0x03  # network unreachable
					elif e.errno in (errno.EHOSTUNREACH, errno.EHOSTDOWN):
						rpl = 0x04  # host unreachable
					elif e.errno in (errno.ECONNREFUSED, errno.ETIMEDOUT):
						rpl = 0x05  # connection refused
					else:
						raise
				else:
					# get socket details that we can send back to the client
					# local address (sockname) in particular -- but we need
					# to ask for the whole socket since Python's sockaddr
					# does not list the family...
					sock = proxied_writer.get_extra_info('socket')
					addr = sock.getsockname()
					if sock.family == socket.AF_INET:
						host, port = addr
						bin_host = socket.inet_aton(host)

						repl_addr = struct.pack('!B4sH',
								0x01, bin_host, port)
					elif sock.family == socket.AF_INET6:
						# discard flowinfo, scope_id
						host, port = addr[:2]
						bin_host = socket.inet_pton(sock.family, host)

						repl_addr = struct.pack('!B16sH',
								0x04, bin_host, port)

			if rpl != 0x00:
				# fallback to 0.0.0.0:0
				repl_addr = struct.pack('!BLH', 0x01, 0x00000000, 0x0000)

			# reply to the request
			repl = struct.pack('!BBB', 0x05, rpl, 0x00)
			writer.write(repl + repl_addr)
			yield from writer.drain()

			# close if an error occured
			if rpl != 0x00:
				writer.close()
				return

			# otherwise, start two loops:
			# remote -> local...
			t = asyncio_ensure_future(self.handle_proxied_conn(
					proxied_reader, writer, current_task()))

			# and local -> remote...
			try:
				try:
					while True:
						data = yield from reader.read(4096)
						if data == b'':
							# client disconnected, stop relaying from
							# remote host
							t.cancel()
							break

						proxied_writer.write(data)
						yield from proxied_writer.drain()
				except OSError:
					# read or write failure
					t.cancel()
				except:
					t.cancel()
					raise
			finally:
				# always disconnect in the end :)
				proxied_writer.close()
				writer.close()

		except (OSError, asyncio.IncompleteReadError, asyncio.CancelledError):
			writer.close()
			return
		except:
			writer.close()
			raise

	@asyncio.coroutine
	def handle_proxied_conn(self, proxied_reader, writer, parent_task):
		"""
		Handle the proxied connection. Relay incoming data
		to the client.

		@param reader: Read side of the socket
		@type reader: asyncio.StreamReader
		@param writer: Write side of the socket
		@type writer: asyncio.StreamWriter
		"""

		try:
			try:
				while True:
					data = yield from proxied_reader.read(4096)
					if data == b'':
						break

					writer.write(data)
					yield from writer.drain()
			finally:
				parent_task.cancel()
		except (OSError, asyncio.CancelledError):
			return


def start_server(handle_proxy_conn, host, port, loop):
	sockets = []
	addrs = set()

	for addrinfo in socket.getaddrinfo(
		host, port,
		family=socket.AF_INET, type=socket.SOCK_STREAM,
		proto=socket.IPPROTO_TCP, flags=socket.AI_PASSIVE):

		# Validate structures returned from getaddrinfo(),
		# since they may be corrupt (especially if python
		# has IPv6 support disabled).
		if len(addrinfo) != 5:
			continue
		family, sock_type, proto, canonname, sockaddr = addrinfo
		print('\n\n\n******* addrinfo', addrinfo, flush=True)
		if len(sockaddr) < 2:
			continue
		if not isinstance(sockaddr[0], str):
			continue
		if sockaddr in addrs:
			print('\n\n\n******* duplicate addr', sockaddr, flush=True)
			continue

		sock = None
		try:
			logging.debug('family=%s type=%s proto=%s addr=%s',
				family, sock_type, proto, sockaddr)
			sock = socket.socket(
				family=family, type=sock_type, proto=proto)
			sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			if (hasattr(socket, 'AF_INET6') and
				hasattr(socket, 'IPV6_V6ONLY') and
				family == socket.AF_INET6):
				# Avoid EADDRINUSE with dual ipv4/ipv6 stack.
				print('\n\n************* IPV6_V6ONLY', flush=True)
				sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
			print('\n\n************* begin bind', sockaddr, host, flush=True)
			sock.bind(sockaddr)
			sock.listen(socket.SOMAXCONN)
			_set_nonblocking(sock.fileno())
			print('\n\n************* bind complete', sockaddr, flush=True)
			#import pdb
			#pdb.set_trace()
		except Exception as e:
			# errno.EADDRINUSE
			logging.exception(e)
			if sock is not None:
				sock.close()
			continue
		else:
			sockets.append((sock, sockaddr))
			addrs.add(sockaddr)
			#break

	if not sockets:
		raise AssertionError('could not bind socket(s)')

	class server_cls(object):

		def __init__(self, sockets, loop):
			self._sockets = sockets
			self._done = loop.create_future()
			self._loop = loop
			self._connections = {}
			for sock, addr in sockets:
				print('\n\n************* add reader *****\n', flush=True)
				#sock.bind(addr)
				#sock.listen(self._args.backlog)
				loop.add_reader(sock.fileno(), self._read_handler)

		def close(self):
			for s, addr in self._sockets:
				s.close()
			del self._sockets[:]

		def wait_closed(self):
			waiter = loop.create_future()
			self._done.add_done_callback(waiter.set_result)
			yield from waiter

		def _read_handler(self):
			print('\n\n************* accept *****\n', flush=True)
			conn, addr = conn_addr = sock.accept()
			self._connections[conn.fileno()] = conn_addr
			self._loop.add_reader(sock.fileno(),
				functools.partial(self._conn_read_handler, conn, addr))

		def _conn_read_handler(self, conn, addr):
			print('\n\n************* _conn_read_handler *****\n', flush=True)
			handle_proxy_conn(None, None)

            #self._loop.add_reader(sock.fileno(),
            #    functools.partial(self._socket_read_handler, con, addr))
			#if not self._done.done():
			#	self._done.set_result(None)
			#handle_proxy_conn()

	return server_cls(sockets, loop)


if __name__ == '__main__':
	if len(sys.argv) != 2:
		print('Usage: %s <socket-path>' % sys.argv[0])
		sys.exit(1)

	loop = asyncio.get_event_loop()
	#host = '127.0.0.1'
	host = 'localhost'
	s = Socks5Server()
	try:
		server = loop.run_until_complete(
			asyncio.start_server(s.handle_proxy_conn, host=host, port=9050,
			loop=getattr(loop, '_asyncio_wrapper', loop)))
	except NotImplementedError:
		server = start_server(s.handle_proxy_conn, host, 9050,
			loop)

	ret = 0
	try:
		try:
			print('\n\n************* loop.run_forever() *****\n', flush=True)
			loop.run_forever()
		except KeyboardInterrupt:
			#pass
			raise
		except:
			ret = 1
	finally:
		loop.run_until_complete(server.wait_closed())
		server.close()
		loop.close()
		if sys.argv[1].startswith('/'):
			os.unlink(sys.argv[1])
		print('\n\n************* loop exit *****\n', flush=True)
	print('\n\n************* loop success *****\n', flush=True)
