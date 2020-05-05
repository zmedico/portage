# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import argparse
import logging
import sys

import portage
from portage import os


def parse_args(args):
	description = "edistfetch - a fetch tool for gentoo distfiles"
	usage = "edistfetch [options] <action>"
	parser = argparse.ArgumentParser(description=description, usage=usage)

	actions = parser.add_argument_group('Actions')
	actions.add_argument("--version",
		action="store_true",
		help="display portage version and exit")

	common = parser.add_argument_group('Common options')
	common.add_argument("-v", "--verbose",
		dest="verbosity",
		action="count",
		default=0,
		help="verbosity")

	options, args = parser.parse_known_args(args)

	return (parser, options, args)

def edistfetch_main(args):

	# The calling environment is ignored, so the program is
	# completely controlled by commandline arguments.
	env = {}

	if not sys.stdout.isatty():
		portage.output.nocolor()
		env['NOCOLOR'] = 'true'

	parser, options, args = parse_args(args)

	if options.version:
		sys.stdout.write("Portage %s\n" % portage.VERSION)
		return os.EX_OK

	portage.util.initialize_logger()

	if options.verbose > 0:
		l = logging.getLogger()
		l.setLevel(l.getEffectiveLevel() - 10 * options.verbose)

	return 0
