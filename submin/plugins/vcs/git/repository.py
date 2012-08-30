import os
import glob
import commands
from submin.models import options
from submin.models.repository import DoesNotExistError, PermissionError

display_name = "Git"

def list():
	"""Returns a list of repositories"""
	repositories = []
	repository_names = _repositoriesOnDisk()
	repository_names.sort()

	for repos in repository_names:
		status = "ok"
		r = None
		try:
			r = Repository(repos)
		except DoesNotExistError:
			pass
		except PermissionError:
			status = "permission denied"

		repositories.append({"name": r.display_name(), "status": status})

	return repositories

def _repositoriesOnDisk():
	reposdir = options.env_path('git_dir')
	reps = glob.glob(str(reposdir + '*.git'))
	repositories = []
	for rep in reps:
		if os.path.isdir(rep):
			name = rep[rep.rfind('/') + 1:]
			repositories.append(unicode(name, 'utf-8'))

	return repositories

def add(name):
	"""Create a new repository with name *name*"""
	if not name.endswith(".git"):
		name += ".git"
	reposdir = options.env_path('git_dir') + name
	# FIXME: reposdir encoding?
	if os.path.exists(str(reposdir)):
		raise PermissionError("Could not create %s, already exists." % name)

	from submin.plugins.vcs.git import remote
	try:
		remote.execute("create %s" % name)
	except remote.NonZeroExitStatus, e:
		raise PermissionError(
			"External command 'GIT_DIR=\"%s\" git --bare init' failed: %s" % \
					(name, e))

class Repository(object):
	"""Internally, this class uses unicode to represent files and directories.
It is converted to UTF-8 (or other?) somewhere in the dispatcher."""

	def __init__(self, name):
		self.name = name
		if not self.name.endswith(".git"):
			self.name += ".git"
		self.signature = "### SUBMIN AUTOCONFIG, DO NOT ALTER FOLLOWING LINE ###\n"

		reposdir = options.env_path('git_dir')
		# FIXME: reposdir encoding?
		self.dir = reposdir + self.name
		self.url = str(reposdir + self.name)

		if not os.path.exists(str(self.dir)):
			raise DoesNotExistError(str(self.dir))

		self.initialized = False
		self.dirs = self.branches()
		self.initialized = True

	def display_name(self):
		return self.name[:-4]

	def branches(self):
		dirname = str(self.dir + "refs" + "heads" + "*")
		for path in glob.glob(dirname):
			if os.path.isfile(path):
				yield {"name": unicode(os.path.basename(path), 'utf-8'), "has_subdirs": False}
		return

	def subdirs(self, subdir):
		"""Get a list of subdirs of subdir *subdir* (root is "")
		Each dir is a dict with at least a property 'name'.
		
		Note: Git support in submin only returns branches, and only when
		      requesting subdirs for the root ("")
		"""
		if str(subdir) == "":
			return self.branches()
		return [] # not supported for git

	def remove(self):
		"""Removes repository *name*"""
		if not self.dir.absolute:
			raise Exception("Error, repository path is relative, this should be fixed")

		if not self.dir.exists():
			raise Exception("Repository %s does not exist." % self.name)

		from submin.plugins.vcs.git import remote
		try:
			remote.execute("remove %s" % self.name)
		except remote.NonZeroExitStatus, e:
			raise PermissionError(
				"External command 'remove %s' failed: %s" % \
						(self.name, e))

	def enableCommitEmails(self, enable):
		"""Enables sending of commit messages if *enable* is True."""
		pass

	def commitEmailsEnabled(self):
		"""Returns True if sendinf of commit messages is enabled."""
		pass

	def __str__(self):
		return self.display_name()
