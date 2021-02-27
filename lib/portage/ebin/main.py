#!/usr/bin/python -b
# Copyright 2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import argparse
import logging
import os
import sys

import portage

from .regen import regen


def main(argv=None):
	common = argparse.ArgumentParser(prog="ebin")
	common.add_argument("-v", "--verbose",
		action="count", default=0,
		help="increase verbosity")

	subparsers = common.add_subparsers(help="sub-command help")

	regen_command = subparsers.add_parser("regen", help="regenerate ebins as needed")
	regen_command.add_argument(
		"--config-root", action="store", help="config root used to generate ebins"
	)
	regen_command.add_argument(
		"--dest-repo", action="store", help="destination ebuild repo for ebins"
	)
	regen_command.add_argument(
		"--dest-distdir",
		action="store",
		help="destination distdir for prebuilt content bundles",
	)
	regen_command.add_argument(
		"--layout-conf", action="store", help="substitute layout.conf file for distdir"
	)
	regen_command.add_argument(
		"--source-dir",
		action="append",
		help="source dir (either PKGDIR or image dir with var/db/pkg)",
	)
	regen_command.set_defaults(func=regen)

	args = common.parse_args(args=portage._decode_argv(argv or sys.argv)[1:])
	if args.config_root is not None:
		os.environ["PORTAGE_CONFIGROOT"] = args.config_root
	portage.util.initialize_logger(logging.WARNING + (logging.INFO - logging.WARNING) * args.verbose)
	args.func(args)
