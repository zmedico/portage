# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop


class RunUntilCompleteTestCase(TestCase):

	def testRunUntilComplete(self):
		event_loop = global_event_loop()
		finished = event_loop.create_future()
		event_loop.call_soon(finished.set_result, True)
		event_loop.run_until_complete(finished)
		self.assertTrue(finished.done())

	def testPrematureStop(self):
		event_loop = global_event_loop()
		event_loop.call_soon(event_loop.stop)
		try:
			event_loop.run_until_complete(event_loop.create_future())
		except RuntimeError:
			# RuntimeError: Event loop stopped before Future completed
			pass
		else:
			self.assertFalse(True)

	def testRecursiveRun(self):
		event_loop = global_event_loop()
		handle = event_loop.call_soon(event_loop.run_forever)
		try:
			event_loop.run_until_complete(event_loop.create_future())
		except RuntimeError:
			# RuntimeError: This event loop is already running
			pass
		else:
			self.assertFalse(True)
		finally:
			handle.cancel()
		self.assertFalse(event_loop.is_running())
