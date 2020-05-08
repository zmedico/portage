# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from __future__ import unicode_literals

import argparse
import logging
import os
import pickle
import shelve
import shutil
import sys
import tempfile
import time
import unittest

import portage
from portage.util._ShelveUnicodeWrapper import ShelveUnicodeWrapper


def open_shelve(db_file, flag='r'):
	"""
	The optional flag parameter has the same interpretation as the flag
	parameter of dbm.open()
	"""
	try:
		db = shelve.open(db_file, flag=flag)
	except ImportError as e:
		# ImportError has different attributes for python2 vs. python3
		if (getattr(e, 'name', None) == 'bsddb' or
			getattr(e, 'message', None) in ('No module named bsddb', 'No module named _bsddb')):
			from bsddb3 import dbshelve
			db = dbshelve.open(db_file)
		else:
			raise

	if sys.hexversion < 0x3000000:
		db = ShelveUnicodeWrapper(db)

	return db


class ShelveUtilsTestCase(unittest.TestCase):

	TEST_DATA = (
		# distfiles_db
		{
			'portage-2.3.89.tar.bz2': 'sys-apps/portage-2.3.89',
			'portage-2.3.99.tar.bz2': 'sys-apps/portage-2.3.99',
		},
		# deletion_db
		{
			'portage-2.3.89.tar.bz2': time.time(),
			'portage-2.3.99.tar.bz2': time.time(),
		},
		# recycle_db
		{
			'portage-2.3.89.tar.bz2': (0, time.time()),
			'portage-2.3.99.tar.bz2': (0, time.time()),
		},
	)

	def test_dump_restore(self):
		for data in self.TEST_DATA:
			tmpdir = tempfile.mkdtemp()
			try:
				dump_args = argparse.Namespace(
					src=os.path.join(tmpdir, 'shelve_file'),
					dest=os.path.join(tmpdir, 'pickle_file'),
				)
				db = open_shelve(dump_args.src, flag='c')
				for k, v in data.items():
					db[k] = v
				db.close()
				dump(dump_args)

				os.unlink(dump_args.src)
				restore_args = argparse.Namespace(
					dest=dump_args.src,
					src=dump_args.dest,
				)
				restore(restore_args)

				db = open_shelve(restore_args.dest, flag='r')
				for k, v in data.items():
					self.assertEqual(db[k], v)
				db.close()
			finally:
				shutil.rmtree(tmpdir)


def dump(args):
	src = open_shelve(args.src, flag='r')
	try:
		with open(args.dest, 'wb') as dest:
			for key in src:
				try:
					value = src[key]
				except KeyError:
					logging.exception(key)
					continue
				pickle.dump((key, value), dest)
	finally:
		src.close()


def restore(args):
	dest = open_shelve(args.dest, flag='c')
	try:
		with open(args.src, 'rb') as src:
			while True:
				try:
					k, v = pickle.load(src)
				except EOFError:
					break
				else:
					dest[k] = v
	finally:
		dest.close()


def _test(args):
	unittest.main(argv=['test'], verbosity=2)


def main(argv=None):
	parser = argparse.ArgumentParser(prog='shelve-utils')
	subparsers = parser.add_subparsers(help='sub-command help')

	dump_command = subparsers.add_parser('dump', help='dump shelve database')
	dump_command.add_argument('src', help='input shelve file')
	dump_command.add_argument('dest', help='output pickle file')
	dump_command.set_defaults(func=dump)

	restore_command = subparsers.add_parser('restore', help='restore shelve database')
	restore_command.add_argument('src', help='input pickle file')
	restore_command.add_argument('dest', help='output shelve file')
	restore_command.set_defaults(func=restore)

	test_command = subparsers.add_parser('test', help='run unit tests')
	test_command.set_defaults(func=_test)

	args = parser.parse_args(args=portage._decode_argv(argv or sys.argv)[1:])
	args.func(args)


if __name__ == '__main__':
	portage.util.initialize_logger()
	main(argv=sys.argv)
