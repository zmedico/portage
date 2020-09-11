# Copyright 2001-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import subprocess
import sys
import threading
import time

from portage import os
from portage.exception import GPGException
from portage.output import colorize
from portage.util import shlex_split, varexpand, writemsg, writemsg_stdout

class GPG:
	"""
	Unlock GPG, must call dircetly from main program for get correct TTY
	"""
	def __init__(self, settings):
		"""
		Portage settings are needed to run GPG unlock command.
		"""
		self.settings = settings
		self.thread = None
		self.GPG_unlock_command = self.settings.get(
			"BINPKG_GPG_UNLOCK_COMMAND", None)
		if "gpg-keepalive" in self.settings.features:
			self.keepalive = True
		else:
			self.keepalive = False

	def unlock(self):
		"""
		Set GPG_TTY and run GPG unlock command.
		If gpg-keepalive is set, start keepalive thread.
		"""
		if (self.GPG_unlock_command
			and (self.settings.get("BINPKG_FORMAT", "xpak") == "gpkg")):
			try:
				os.environ["GPG_TTY"] = os.ttyname(sys.stdout.fileno())
			except OSError as e:
				# When run with no input/output tty, this will fail.
				# However, if the password is given by command,
				# GPG does not need to ask password, so can be ignored.
				writemsg(colorize("WARN", str(e)) + '\n')

			return_code = os.system(self.GPG_unlock_command)

			if return_code == os.EX_OK:
				writemsg_stdout(colorize("GOOD", "unlocked") + '\n')
				sys.stdout.flush()
			else:
				raise GPGException("GPG unlock failed")

			if self.keepalive:
				self.GPG_unlock_command = shlex_split(
					varexpand(self.GPG_unlock_command, mydict=self.settings))
				self.thread = threading.Thread(target=self.gpg_keepalive,
					daemon=True)
				self.thread.start()

	def stop(self):
		"""
		Stop keepalive thread.
		"""
		if self.thread is not None:
			self.keepalive = False

	def gpg_keepalive(self):
		"""
		Call GPG unlock command every 5 mins to avoid the passphrase expired.
		"""
		count = 0
		while self.keepalive:
			if count < 5:
				time.sleep(60)
				count += 1
				continue
			else:
				count = 0

			proc = subprocess.Popen(self.GPG_unlock_command,
				stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
				stderr=subprocess.STDOUT)
			if proc.wait() != os.EX_OK:
				raise GPGException("GPG keepalive failed")
