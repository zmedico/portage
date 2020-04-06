# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from collections import deque
import sys

from portage.util.futures import asyncio
from portage.util.futures.compat_coroutine import coroutine
from portage.util.SlotObject import SlotObject

class SequentialTaskQueue(SlotObject):

	__slots__ = ("max_jobs", "running_tasks") + \
		("_scheduling", "_task_queue")

	def __init__(self, **kwargs):
		SlotObject.__init__(self, **kwargs)
		self._task_queue = deque()
		self.running_tasks = set()
		if self.max_jobs is None:
			self.max_jobs = 1

	def add(self, task):
		self._task_queue.append(task)
		self.schedule()

	def addFront(self, task):
		self._task_queue.appendleft(task)
		self.schedule()

	def schedule(self):

		if self._scheduling:
			# Ignore any recursive schedule() calls triggered via
			# self._task_exit().
			return

		self._scheduling = True
		try:
			while self._task_queue and (self.max_jobs is True or
				len(self.running_tasks) < self.max_jobs):
				task = self._task_queue.popleft()
				cancelled = getattr(task, "cancelled", None)
				if not cancelled:
					self.running_tasks.add(task)
					future = asyncio.ensure_future(self._task_coroutine(task), loop=task.scheduler)
					future.add_done_callback(lambda future: future.cancelled() or future.result())
					# This callback will be invoked as soon as the task
					# exits (before the future's done callback is called),
					# and this is required in order for bool(self) to have
					# an updated value for Scheduler._schedule to base
					# assumptions upon. Delayed updates to bool(self) is
					# what caused Scheduler to hang as in bug 709746.
					#task.addExitListener(self._task_exit)
		finally:
			self._scheduling = False

	@coroutine
	def _task_coroutine(self, task):
		try:
			yield task.async_start()
			yield task.async_wait()
		except asyncio.CancelledError:
			self._task_exit(task)
			raise
		self._task_exit(task)

	def _task_exit(self, task):
		"""
		Since we can always rely on exit listeners being called, the set of
 		running tasks is always pruned automatically and there is never any need
		to actively prune it.
		"""
		self.running_tasks.remove(task)
		if self._task_queue:
			self.schedule()

	def clear(self):
		"""
		Clear the task queue and asynchronously terminate any running tasks.
		"""
		for task in self._task_queue:
			task.cancel()
		self._task_queue.clear()

		for task in list(self.running_tasks):
			task.cancel()

	def wait(self):
		"""
		Synchronously wait for all running tasks to exit.
		"""
		while self.running_tasks:
			next(iter(self.running_tasks)).wait()

	def __bool__(self):
		return bool(self._task_queue or self.running_tasks)

	if sys.hexversion < 0x3000000:
		__nonzero__ = __bool__

	def __len__(self):
		return len(self._task_queue) + len(self.running_tasks)
