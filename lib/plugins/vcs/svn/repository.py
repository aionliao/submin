# -*- coding: utf-8 -*-
from path.path import Path
import os
from unicode import uc_str, uc_to_svn, uc_from_svn
import commands
import exceptions
from models.options import Options

from models.repository import DoesNotExistError, PermissionError, VersionError, VCSImportError

def list(session_user):
	o = Options()
	repositories = []
	repository_names = repositoriesOnDisk()
	repository_names.sort()
	
	for repos in repository_names:
		try:
			r = Repository(repos)
			status = "ok"
		except DoesNotExist:
			pass
		except PermissionDenied:
			status = "permission denied"
		except WrongVersion:
			status = "wrong version"

		if session_user.is_admin:
			repositories.append({"name": repos, "status": status})
		else:
			if r.userHasReadPermissions(session_user):
				repositories.append({"name": repos, "status": status})

	return repositories

def repositoriesOnDisk():
	"""Returns all repositories that are found on disk"""
	import glob, os.path
	o = Options()
	reposdir = o.env_path('dir_svn')
	reps = glob.glob(str(reposdir + '*'))
	repositories = []
	for rep in reps:
		if os.path.isdir(rep):
			repositories.append(rep[rep.rfind('/') + 1:])

	return repositories

class Repository(object):
	"""Internally, this class uses unicode to represent files and directories.
It is converted to UTF-8 (or other?) somewhere in the dispatcher."""

	def __init__(self, name):
		try:
			global fs, repos, core, SubversionException
			from svn import fs, repos, core
			from svn.core import SubversionException
		except ImportError:
			raise VCSImportError("Failed to import python 'svn' module, please install")

		o = Options()

		self.name = name
		self.signature = "### SUBMIN AUTOCONFIG, DO NOT ALTER FOLLOWING LINE ###\n"

		reposdir = o.env_path('dir_svn')
		self.url = str(reposdir + self.name)

		self.dirs = self.getsubdirs("")

	def getsubdirs(self, path):
		'''Return subdirs (not recursive) of 'path' relative to our reposdir
		Subdirs are returned as a hash with two entities: 'name' and 
		'has_subdirs', which should be self-explanatory.'''

		files = self.get_entries(path)
		dirs = []
		for f in files:
			if f['kind'] == 'dir':
				hassubdirs = self.hassubdirs(os.path.join(path, f['name']))
				entry = {}
				entry['name'] = f['name']
				entry['has_subdirs'] = hassubdirs
				dirs.append(entry)

		dirs.sort(lambda a, b: cmp(unicode.lower(a['name']), unicode.lower(b['name'])))
		return dirs

	def get_entries(self, path):
		# lots of conversions from and to utf-8
		root_path_utf8 = repos.svn_repos_find_root_path(self.url)
		if root_path_utf8 is None or not os.path.exists(root_path_utf8):
			raise DoesNotExistError

		try:
			repository = repos.svn_repos_open(root_path_utf8)
		except SubversionException, e:
			# check for messages like the following:
			# "Expected FS Format 'x'; found format 'y'"
			# there are different errorcodes for each version, so do a string
			# match instead of errorcode match
			errstr = str(e)
			if "Expected" in errstr and "format" in errstr and "found" in errstr:
				raise self.VersionError

			raise PermissionError

		fs_ptr = repos.svn_repos_fs(repository)

		path_utf8 = uc_to_svn(uc_str(path))
		youngest_revision_number = fs.youngest_rev(fs_ptr)
		try:
			root = fs.revision_root(fs_ptr, youngest_revision_number)
		except SubversionException, e:
			raise self.PermissionDenied

		entries = fs.dir_entries(root, path_utf8)

		dirs = []
		for entry in entries.keys():
			d = {}
			node_type = fs.check_path(root, os.path.join(path_utf8, entry))
			if (node_type == core.svn_node_dir):
				d['kind'] = 'dir'
			elif (node_type == core.svn_node_file):
				d['kind'] = 'file'
			else:
				d['kind'] = 'unknown'
			d['name'] = uc_from_svn(entry)
			dirs.append(d)

		return dirs

	def hassubdirs(self, path):
		import os

		files = self.get_entries(path)
		for f in files:
			if f['kind'] == 'dir':
				return True # only one is enough

		return False

	def notificationsEnabled(self):
		import os

		reposdir = self.config.getpath('svn', 'repositories')
		hook = reposdir + self.name + 'hooks' + 'post-commit'
		try:
			f = open(str(hook), 'r')
		except IOError:
			return False # assume it does not exist
		
		# if we find the signature, assume it is installed
		if self.signature in f.readlines():
			return True
		return False

	def changeNotifications(self, enable=True):
		"""Add or remove our script to/from the post-commit hook"""
		import os
		config = Config()

		line_altered = False
		reposdir = self.config.getpath('svn', 'repositories')
		hook = reposdir + self.name + 'hooks' + 'post-commit'
		bindir = self.config.getpath('backend', 'bindir')
		fullpath = bindir + 'post-commit.py'
		# XXX ugly code :(
		if config.version == 1:
			config_file = os.environ['SUBMIN_CONF']
		else:
			config_file = os.environ['SUBMIN_ENV']

		new_hook = '/usr/bin/python %s "%s" "$1" "$2"\n' % \
				(str(fullpath), config_file)

		f = open(str(hook), 'a+')
		f.seek(0, 2) # seek to end of file, not all systems do this

		if f.tell() != 0:
			f.seek(0)
			alter_line = False
			new_file_content = []
			for line in f.readlines():
				if alter_line:
					if enable:
						new_file_content.append(new_hook)
					alter_line = False
					line_altered = True
					continue # filter out command

				if line == self.signature:
					alter_line = True
					if not enable:
						continue # filter out signature

				new_file_content.append(line)

			f.truncate(0)
			f.writelines(new_file_content)
		else:
			if enable:
				f.write("#!/bin/sh\n")

		if not line_altered and enable:
			f.write(self.signature)
			f.write(new_hook)
		f.close()
		os.chmod(str(hook), 0755)

	def remove(self):
		o = Options()
		reposdir = o.env_path('dir_svn')
		newrepos = reposdir + self.name
		if not newrepos.absolute:
			raise Exception("Error, repository path is relative, this should be fixed")

		cmd = 'rm -rf "%s"' % newrepos
		(exitstatus, outtext) = commands.getstatusoutput(cmd)
		if exitstatus != 0:
			raise Exception("could not remove repository %s" % self.name)

	def __str__(self):
		return self.name
