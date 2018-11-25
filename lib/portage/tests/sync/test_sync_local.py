# Copyright 2014-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import datetime
import subprocess
import sys
import textwrap
import time

import portage
from portage import os, shutil, _shell_quote
from portage import _unicode_decode
from portage.const import PORTAGE_PYM_PATH, TIMESTAMP_FORMAT
from portage.process import find_binary
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.util import ensure_dirs

class SyncLocalTestCase(TestCase):
	"""
	Test sync with rsync and git, using file:// sync-uri.
	"""

	def _must_skip(self):
		if find_binary("rsync") is None:
			return "rsync: command not found"
		if find_binary("git") is None:
			return "git: command not found"

	def testSyncLocal(self):
		debug = True

		skip_reason = self._must_skip()
		if skip_reason:
			self.portage_skip = skip_reason
			self.assertFalse(True, skip_reason)
			return

		repos_conf = textwrap.dedent("""
			[DEFAULT]
			%(default_keys)s
			[test_repo]
			location = %(EPREFIX)s/var/repositories/test_repo
			sync-type = %(sync-type)s
			sync-depth = %(sync-depth)s
			sync-uri = file://%(EPREFIX)s/var/repositories/test_repo_sync
			sync-rcu = %(sync-rcu)s
			sync-rcu-store-dir = %(EPREFIX)s/var/repositories/test_repo_rcu_storedir
			auto-sync = %(auto-sync)s
			sync-user = %(sync-user)s
			%(repo_extra_keys)s
		""")

		profile = {
			"eapi": ("5",),
			"package.use.stable.mask": ("dev-libs/A flag",)
		}

		ebuilds = {
			"dev-libs/A-0": {}
		}

		user_config = {
			'make.conf': ('FEATURES="metadata-transfer"',)
		}

		playground = ResolverPlayground(ebuilds=ebuilds,
			profile=profile, user_config=user_config, debug=debug)
		settings = playground.settings
		eprefix = settings["EPREFIX"]
		eroot = settings["EROOT"]
		homedir = os.path.join(eroot, "home")
		distdir = os.path.join(eprefix, "distdir")
		repo = settings.repositories["test_repo"]
		metadata_dir = os.path.join(repo.location, "metadata")
		portage.util.apply_permissions(os.path.dirname(repo.location),
			uid=int(portage.data.portage_uid),
			gid=int(portage.data.portage_gid))

		cmds = {}
		for cmd in ("emerge", "emaint"):
			for bindir in (self.bindir, self.sbindir):
				path = os.path.join(bindir, cmd)
				if os.path.exists(path):
					cmds[cmd] =  (portage._python_interpreter,
						"-b", "-Wd", path)
					break
			else:
				raise AssertionError('%s binary not found in %s or %s' %
					(cmd, self.bindir, self.sbindir))

		git_binary = find_binary("git")
		git_cmd = (git_binary,)

		committer_name = "Gentoo Dev"
		committer_email = "gentoo-dev@gentoo.org"

		def repos_set_conf(sync_type, dflt_keys=None, xtra_keys=None,
			auto_sync="yes", sync_rcu=False, sync_depth=None, sync_user=None):
			env["PORTAGE_REPOSITORIES"] = repos_conf % {\
				"EPREFIX": eprefix, "sync-type": sync_type,
				"sync-depth": 0 if sync_depth is None else sync_depth,
				"sync-rcu": "yes" if sync_rcu else "no",
				"auto-sync": auto_sync,
				"default_keys": "" if dflt_keys is None else dflt_keys,
				"repo_extra_keys": "" if xtra_keys is None else xtra_keys,
				"sync-user": os.environ.get("PORTAGE_USERNAME", "portage") if sync_user is None else sync_user}

		def alter_ebuild():
			with open(os.path.join(repo.location + "_sync",
				"dev-libs", "A", "A-0.ebuild"), "a") as f:
				f.write("\n")
			bump_timestamp()

		def bump_timestamp():
			bump_timestamp.timestamp += datetime.timedelta(seconds=1)
			with open(os.path.join(repo.location + '_sync', 'metadata', 'timestamp.chk'), 'w') as f:
				f.write(bump_timestamp.timestamp.strftime('%s\n' % TIMESTAMP_FORMAT,))

		bump_timestamp.timestamp = datetime.datetime.utcnow()

		bump_timestamp_cmds = (
			(homedir, bump_timestamp),
		)

		sync_cmds = (
			(homedir, cmds["emerge"] + ("--sync",)),
			(homedir, lambda: self.assertTrue(os.path.exists(
				os.path.join(repo.location, "dev-libs", "A")
				), "dev-libs/A expected, but missing")),
			(homedir, cmds["emaint"] + ("sync", "-A")),
		)

		sync_cmds_auto_sync = (
			(homedir, lambda: repos_set_conf("rsync", auto_sync="no")),
			(homedir, cmds["emerge"] + ("--sync",)),
			(homedir, lambda: self.assertFalse(os.path.exists(
				os.path.join(repo.location, "dev-libs", "A")
				), "dev-libs/A found, expected missing")),
			(homedir, lambda: repos_set_conf("rsync", auto_sync="yes")),
		)

		rename_repo = (
			(homedir, lambda: os.rename(repo.location,
				repo.location + "_sync")),
		)

		rsync_opts_repos = (
			(homedir, alter_ebuild),
			(homedir, lambda: repos_set_conf("rsync", None,
				"sync-rsync-extra-opts = --backup --backup-dir=%s" %
				_shell_quote(repo.location + "_back"))),
			(homedir, cmds['emerge'] + ("--sync",)),
			(homedir, lambda: self.assertTrue(os.path.exists(
				repo.location + "_back"))),
			(homedir, lambda: shutil.rmtree(repo.location + "_back")),
			(homedir, lambda: repos_set_conf("rsync")),
		)

		rsync_opts_repos_default = (
			(homedir, alter_ebuild),
			(homedir, lambda: repos_set_conf("rsync",
					"sync-rsync-extra-opts = --backup --backup-dir=%s" %
					_shell_quote(repo.location+"_back"))),
			(homedir, cmds['emerge'] + ("--sync",)),
			(homedir, lambda: self.assertTrue(os.path.exists(repo.location + "_back"))),
			(homedir, lambda: shutil.rmtree(repo.location + "_back")),
			(homedir, lambda: repos_set_conf("rsync")),
		)

		rsync_opts_repos_default_ovr = (
			(homedir, alter_ebuild),
			(homedir, lambda: repos_set_conf("rsync",
				"sync-rsync-extra-opts = --backup --backup-dir=%s" %
				_shell_quote(repo.location + "_back_nowhere"),
				"sync-rsync-extra-opts = --backup --backup-dir=%s" %
				_shell_quote(repo.location + "_back"))),
			(homedir, cmds['emerge'] + ("--sync",)),
			(homedir, lambda: self.assertTrue(os.path.exists(repo.location + "_back"))),
			(homedir, lambda: shutil.rmtree(repo.location + "_back")),
			(homedir, lambda: repos_set_conf("rsync")),
		)

		rsync_opts_repos_default_cancel = (
			(homedir, alter_ebuild),
			(homedir, lambda: repos_set_conf("rsync",
				"sync-rsync-extra-opts = --backup --backup-dir=%s" %
				_shell_quote(repo.location + "_back_nowhere"),
				"sync-rsync-extra-opts = ")),
			(homedir, cmds['emerge'] + ("--sync",)),
			(homedir, lambda: self.assertFalse(os.path.exists(repo.location + "_back"))),
			(homedir, lambda: repos_set_conf("rsync")),
		)

		delete_repo_location = (
			(homedir, lambda: shutil.rmtree(repo.user_location)),
			(homedir, lambda: os.mkdir(repo.user_location)),
		)

		revert_rcu_layout = (
			(homedir, lambda: os.rename(repo.user_location, repo.user_location + '.bak')),
			(homedir, lambda: os.rename(os.path.realpath(repo.user_location + '.bak'), repo.user_location)),
			(homedir, lambda: os.unlink(repo.user_location + '.bak')),
			(homedir, lambda: shutil.rmtree(repo.user_location + '_rcu_storedir')),
		)

		upstream_git_commit = (
			(
				repo.location + "_sync",
				git_cmd + ('commit', '--allow-empty', '-m', 'test empty commit'),
			),
			(
				repo.location + "_sync",
				git_cmd + ('commit', '--allow-empty', '-m', 'test empty commit 2'),
			),
		)

		delete_sync_repo = (
			(homedir, lambda: shutil.rmtree(
				repo.location + "_sync")),
		)

		git_repo_create = (
			(repo.location, git_cmd +
				("config", "--global", "user.name", committer_name,)),
			(repo.location, git_cmd +
				("config", "--global", "user.email", committer_email,)),
			(repo.location, git_cmd + ("init-db",)),
			(repo.location, git_cmd + ("add", ".")),
			(repo.location, git_cmd +
				("commit", "-a", "-m", "add whole repo")),
		)

		sync_type_git = (
			(homedir, lambda: repos_set_conf("git")),
		)

		sync_type_git_shallow = (
			(homedir, lambda: repos_set_conf("git", sync_depth=1)),
		)

		sync_rsync_rcu = (
			(homedir, lambda: repos_set_conf("rsync", sync_rcu=True)),
			(homedir, lambda: ensure_dirs(os.path.join(eprefix, 'var/repositories/test_repo_rcu_storedir'),
								uid=int(portage.data.portage_uid),
								gid=int(portage.data.portage_gid))),

		)

		pythonpath =  os.environ.get("PYTHONPATH")
		if pythonpath is not None and not pythonpath.strip():
			pythonpath = None
		if pythonpath is not None and \
			pythonpath.split(":")[0] == PORTAGE_PYM_PATH:
			pass
		else:
			if pythonpath is None:
				pythonpath = ""
			else:
				pythonpath = ":" + pythonpath
			pythonpath = PORTAGE_PYM_PATH + pythonpath

		env = {
			"PORTAGE_OVERRIDE_EPREFIX" : eprefix,
			"DISTDIR" : distdir,
			"FEATURES": "usersync",
			"GENTOO_COMMITTER_NAME" : committer_name,
			"GENTOO_COMMITTER_EMAIL" : committer_email,
			"HOME" : homedir,
			"PATH" : os.environ["PATH"],
			"PORTAGE_GRPNAME" : os.environ.get("PORTAGE_GRPNAME", "portage"),
			"PORTAGE_USERNAME" : os.environ.get("PORTAGE_USERNAME", "portage"),
			"PYTHONDONTWRITEBYTECODE" : os.environ.get("PYTHONDONTWRITEBYTECODE", ""),
			"PYTHONPATH" : pythonpath,
		}
		repos_set_conf("rsync")

		if os.environ.get("SANDBOX_ON") == "1":
			# avoid problems from nested sandbox instances
			env["FEATURES"] += " -sandbox -usersandbox"

		dirs = [homedir, metadata_dir]
		try:
			for d in dirs:
				ensure_dirs(d)

			timestamp_path = os.path.join(metadata_dir, 'timestamp.chk')
			with open(timestamp_path, 'w') as f:
				f.write(bump_timestamp.timestamp.strftime('%s\n' % TIMESTAMP_FORMAT,))

			if debug:
				# The subprocess inherits both stdout and stderr, for
				# debugging purposes.
				stdout = None
			else:
				# The subprocess inherits stderr so that any warnings
				# triggered by python -Wd will be visible.
				stdout = subprocess.PIPE

			for cwd, cmd in rename_repo + sync_cmds_auto_sync + sync_cmds + \
				rsync_opts_repos + rsync_opts_repos_default + \
				rsync_opts_repos_default_ovr + rsync_opts_repos_default_cancel + \
				bump_timestamp_cmds + sync_rsync_rcu + sync_cmds + revert_rcu_layout + \
				delete_repo_location + sync_cmds + sync_cmds + \
				bump_timestamp_cmds + sync_cmds + revert_rcu_layout + \
				delete_sync_repo + git_repo_create + sync_type_git + \
				rename_repo + sync_cmds + upstream_git_commit + sync_cmds + \
				sync_type_git_shallow + upstream_git_commit + sync_cmds:

				if hasattr(cmd, '__call__'):
					cmd()
					continue

				abs_cwd = os.path.join(repo.location, cwd)
				proc = subprocess.Popen(cmd,
					cwd=abs_cwd, env=env, stdout=stdout)

				if debug:
					proc.wait()
				else:
					output = proc.stdout.readlines()
					proc.wait()
					proc.stdout.close()
					if proc.returncode != os.EX_OK:
						for line in output:
							sys.stderr.write(_unicode_decode(line))

				self.assertEqual(os.EX_OK, proc.returncode,
					"%s failed in %s" % (cmd, cwd,))


		finally:
			playground.cleanup()
