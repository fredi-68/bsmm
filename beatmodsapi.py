#Unofficial beatmods.com API implementation for Python 3
#
#The API client code was reverse engineered from the webinterface's requests
#to beatmods.com/api/v1 so it may be incomplete. No guarantee is made for the
#returned information to be correct. Everything is subject to change.
#
#Copyright (c) fredi_68 2019
#All rights reserved.

__version__ = [2, 2, 0]

from urllib import request
import zlib
import json
import logging
import enum
import pathlib
import zipfile
import hashlib
import os

logger = logging.getLogger("beatmods.API")

API_URL = "https://beatmods.com/api/v1/"
APP_TYPE = "steam"
WBITS = 47 #Unsure what beatmods.com uses but 47 seems to work just fine

def validateFile(data, hash):

    """
    Validates a file using the MD5 algorithm.
    Returns True if the files MD5 hash signature matches
    the provided hexadecimal string, False otherwise.
    """

    h = hashlib.md5()
    h.update(data)

    return h.hexdigest().lower() == hash.lower()

def _getEndpoint(endpoint):

    """
    Get a urllib.request.Request object to access
    the specified API endpoint.

    Please specify the endpoint after https://beatmods.com/api/v1/

    The returned Request will have all required
    headers that are needed to get a response.
    """

    logger.debug("Requesting API endpoint %s" % endpoint)
    req = request.Request(API_URL + endpoint)
    req.add_header("user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.86 Safari/537.36")
    req.add_header("accept", "application/json")
    req.add_header("accept-encoding", "gzip")
    req.add_header("referer", "https://beatmods.com/")
    return req

def _parsePayload(data, is_compressed=True, comp_wbits=WBITS):

    """
    Parse the return payload from an API call.
    Supports zlib compression.
    """

    if is_compressed:
        logger.debug("Using ZLIB compression with %i wbits" % comp_wbits)
        data = zlib.decompress(data, wbits=comp_wbits)

    return json.loads(data)

def getBeatModsList(query="", sortBy="", status="approved", sortDir=1):

    """
    Search beatmods.com for BeatSaber mods.

    All arguments are optional and control how content is processed.
    If called without arguments, the default behavior is to return a
    list of all approved mods, sorted by last time updated.

    The return value is a list containing information about
    the different mods as dictionaries.
    """

    logger.debug("Searching mods...")
    req = _getEndpoint("mod?search=%s&status=%s&sort=%s&sortDirection=%i" % (query, status, sortBy, sortDir))
    res = request.urlopen(req)
    mods = _parsePayload(res.read(), True)
    logger.debug("Search query returned %i entries." % len(mods))
    return mods

def downloadMod(url):

    """
    Download a mod archive using a URL fragment as returned
    by the getBeatModsList() function.

    The returned value will be a http.client.HTTPResponse,
    which may be used as a file-like object.
    """

    logger.debug("Downloading...")
    req = request.Request("https://beatmods.com" + url)
    req.add_header("user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.86 Safari/537.36")
    return request.urlopen(req)

class ModCategories(enum.Enum):

    CORE = 0
    LIBRARY = 1
    COSMETIC = 2
    GAMEPLAY = 3
    UI = 4
    OTHER = 5

class ModSpec():

    """
    Class representing a mod specification.

    This is a dataclass containing all information about a mod
    package. Data can be (de)serialized to and from JSON files for
    persistency and automatic version/dependency tracking.

    Supports parsing from beatmods.com JSON blobs

    This class supports ordering by mod name to enable alphabetical
    sorting.

    File format specification:

    {
    "id": str,
    "name": str,
    "version": list[int],
    "url": str,
    "config": {
        "ignore": int,
        "is_local": int,
        "is_remote": int,
        "need_update": int,
        "need_install": int,
        "need_uninstall": int
        }
    "dependencies": list[str],
    "files": [
        {
            "hash": str,
            "file": str
            }
        ]
    }
    """

    logger = logging.getLogger("beatmods.ModSpec")

    def __init__(self, id, name, version, url, files=[], dependencies=[], category=ModCategories.OTHER, gameVersion=(1, 0, 0)):

        """
        Create a new ModSpec instance.

        Users will normally not interface with this constructor directly
        but instead use the provided classmethods fromSpecFile() and
        fromBeatMods()
        """

        self._archive = ""

        self.id = id
        self.name = name
        self.version = version
        self.gameVersion = gameVersion
        self.dependencies = dependencies
        self.category = category
        self.url = url
        self.files = files
        self.ignore = False
        self.is_local = False
        self.is_remote = False
        self.need_update = False
        self.need_install = False
        self.need_uninstall = False

    @classmethod
    def fromSpecFile(cls, f):

        """
        Create a ModSpec from a local file.

        f should be a file-like object containing JSON data. 
        """

        d = json.load(f)
        id = d["id"]
        name = d["name"]
        version = d["version"]
        url = d["url"]
        dependencies = d["dependencies"]
        files = d["files"]

        obj = ModSpec(id, name, version, url, files, dependencies)

        config = d["config"]
        obj.ignore = config["ignore"]
        obj.is_local = config["is_local"]
        obj.is_remote = config["is_remote"]
        obj.need_update = config["need_update"]
        obj.need_install = config["need_install"]
        obj.need_uninstall = config["need_uninstall"]

        return obj

    @classmethod
    def fromBeatMods(cls, d, type=APP_TYPE):

        """
        Create a ModSpec from a JSON blob.

        d should be the dictionary containing the parsed JSON data from
        beatmods.com
        """

        id = d["_id"]
        name = d["name"]
        try:
            version = list(map(int, d["version"].split(".")))
        except:
            version = [0, 0, 0]
        gameVersion = list(map(int, d["gameVersion"].split(".")))

        c = d["category"]
        if c == "Core":
            cat = ModCategories.CORE
        elif c == "Libraries":
            cat = ModCategories.LIBRARY
        elif c == "Cosmetic":
            cat = ModCategories.COSMETIC
        elif c == "UI Enhancements":
            cat = ModCategories.UI
        elif c == "Gameplay":
            cat = ModCategories.GAMEPLAY
        else:
            cat = ModCategories.OTHER

        downloads = {}
        for i in d["downloads"]:
            downloads[i["type"]] = i

        dl_spec = None
        if type in downloads:
            dl_spec = downloads[type]
        elif not "universal" in downloads:
            raise RuntimeError("No version found for application type '%s'" % type)
        else:
            dl_spec = downloads["universal"]

        url = dl_spec["url"]
        
        obj = ModSpec(id, name, version, url, dl_spec["hashMd5"], d["dependencies"], cat, gameVersion)
        obj.is_remote = True

        return obj

    @classmethod
    def fromArchive(cls, f):

        """
        Construct a ModSpec from an archive file.
        This loader is intended to be used with zipfile.ZipFile objects,
        however, other archiving libraries using a similar interface
        should work just fine.
        This method will first try to locate a file named "spec.json" in
        the root directory of the archive. If this file is present, it should
        either contain:
            1) a serialized ModSpec OR
            2) a JSON blob containing information on the mod package as
                returned by beatmods.com

        If this file is not present or could not be loaded for some reason, the
        loader will attempt to construct a ModSpec from the archive directly.
        This will include all files present in the archive in the ModSpec instance,
        however, archive verification and automated dependency resolution will not
        be supported.
        """

        try:
            spec = f.open("spec.json", "r")
        except KeyError:
            spec = None

        if spec:
            cls.logger.debug("Attempting to create ModSpec from archive spec file...")
            try:
                s = ModSpec.fromSpecFile(spec)
                cls.logger.debug("Successfully loaded ModSpec from archive spec file.")
                return s
            except:
                pass
            try:
                s = ModSpec.fromBeatMods(json.load(f))
                cls.logger.debug("Successfully loaded ModSpec from archive beatmods file.")
                return s
            except:
                pass

        cls.logger.debug("No archive mod spec found, creating ModSpec from archive...")
        cls.logger.debug("Creating mod package key...")
        h = hashlib.md5()
        entries = list(f.namelist())
        for name in entries:
            h.update(name.encode("utf-8"))
        id = h.hexdigest()
        cls.logger.debug("Archive key is '%s'." % id)
        cls.logger.debug("Processing %i entries..." % len(entries))
        hashes = []
        for name in entries:
            with f.open(name, "r") as e:
                #calculate "bogus hashes" to ensure
                #the patcher doesn't have a heart attack
                md5 = hashlib.md5()
                md5.update(e.read())
                hashes.append({"file": name, "hash": md5.hexdigest()})

        modName = pathlib.Path(f.filename).name
        cls.logger.debug("Package name is '%s'." % modName)
        cls.logger.debug("Creating ModSpec...")
        spec = ModSpec(id, modName, [1, 0, 0], "local", hashes, [])
        spec._archive = pathlib.Path(f.filename)
        cls.logger.debug("Success!")
        return spec

    def writeSpecFile(self, f):

        """
        Serialize this ModSpec to a JSON file.

        f should be a file-like object.
        """

        config = {}
        config["ignore"] = int(self.ignore)
        config["is_local"] = int(self.is_local)
        config["is_remote"] = int(self.is_remote)
        config["need_update"] = int(self.need_update)
        config["need_install"] = int(self.need_install)
        config["need_uninstall"] = int(self.need_uninstall)

        d = {"config": config}
        d["id"] = self.id
        d["name"] = self.name
        d["version"] = self.version
        d["url"] = self.url
        d["files"] = self.files
        d["dependencies"] = self.dependencies

        json.dump(d, f)

        return f

    def __lt__(self, other):

        if isinstance(other, ModSpec):
            return self.name < other.name
        raise NotImplementedError

class Patcher():

    """
    This class implements a fully functional patcher for
    BeatSaber mods. It keeps track of installed mods as
    well as the repository on beatmods.com and provides
    features such as automatic dependency and version
    checking and automatic updates.

    You can get started by calling the refreshMods() method.
    This will refresh local and remote caches.
    Information about mods can now be retrieved using the
    lists Patcher.local and Patcher.remote .
    Additionally, the lists Patcher.need_install,
    Patcher.need_uninstall and Patcher.need_update keep track
    of actions that are queued for mod packages.

    Mods are managed using ModSpecs, which contain all
    required information about a mod package, such as its ID
    or its dependencies. You can pass these ModSpecs to
    addMod(), removeMod() or ignoreMod() respectively to queue
    up actions for the patcher.
    Once everything is ready, calling the patch() method will
    queue up all actions and execute them in order. After
    patching is complete, all installed mods will now be
    tracked by the patcher and automatically queued for
    installation once a new version is available.
    """

    logger = logging.getLogger("beatmods.Patcher")

    def __init__(self, path, app_type=APP_TYPE):

        """
        Create a new Patcher instance.

        path should be a string or pathlib.Path instance
        pointing to the root directory of your BeatSaber
        installation. Usually this is located in
        C:/Program Files (x86)/Steam/steamapps/common/Beat Saber/
        on Windows machines, although this may be different for
        users with additional/alternative Steam library paths
        or Oculus users.

        app_type should be set to either "steam" or "oculus" depending
        on the type of your installation.
        This will allow BSMM to correctly download the mods and libraries
        compiled for your version.
        The default is "steam".
        """

        self.setPath(path)

        self.app_type= app_type
        self.remote = []
        self.local = []
        self.need_install = []
        self.need_uninstall = []
        self.need_update = []

    def setPath(self, path):

        """
        Sets the path of the BeatSaber installation.

        This will also create the directories needed by
        BSMM if they don't exist already.

        BSMM stores all data alongside the game in a folder
        called ".bsmm" located in the root directory. If you
        wish to remove all data collected by the application,
        simply delete this folder.
        """

        self.path = pathlib.Path(path)
        self.app_dir = self.path / ".bsmm"
        self.download_cache = self.app_dir / "cache"
        self.manifest_cache = self.app_dir / "meta"

        self.logger.debug("Application path is now %s" % self.path)

        #setup paths
        os.makedirs(self.download_cache, exist_ok=True)
        os.makedirs(self.manifest_cache, exist_ok=True)

        self.logger.debug("Created temporary directory %s" % self.app_dir)

    def refreshMods(self, doUpdate=True):

        """
        Resets the trackers and reloads local and
        remote mod lists.
        """

        self.need_install.clear()
        self.need_uninstall.clear()
        self.need_update.clear()

        self.getLocal()
        self.getRemote()

        if not doUpdate:
            return

        self.logger.info("Checking for updates...")
        for spec in self.local:
            for rspec in self.remote:
                if spec.name == rspec.name:
                    rspec.is_local = True
                    if spec.version < rspec.version:
                        self.logger.debug("Mod '%s' is out of date, staged for automatic upate." % spec.name)
                        spec.need_update = True
                        self.need_update.append(spec)

    def getLocal(self, sort=True):

        """
        Populates the local mod list using
        the cached mod manifests.

        Mods set to ignore will not be considered.
        """

        self.local.clear()
        for path in self.manifest_cache.iterdir():
            if str(path).endswith(".json"):
                with open(path, "r") as f:
                    spec = ModSpec.fromSpecFile(f)
                    if not spec.ignore:
                        self.local.append(spec)

        self.local.sort()

    def getRemote(self, query="", sortBy="name_lower", sortDir=1):

        """
        Populates the remote mod list using
        the beatmods.com API.
        """

        self.remote.clear()
        mods = getBeatModsList(query, sortBy, sortDir=sortDir)
        for mod in mods:
            spec = ModSpec.fromBeatMods(mod, self.app_type)
            self.remote.append(spec)

    def _installMod(self, spec):

        """
        Patches a mod into BeatSaber.

        spec must be a ModSpec instance.
        The mod must be downloaded into the local
        cache directory.
        """

        #TODO: Only install files covered by the spec file

        p1 = spec._archive
        if not p1:
            p1 = self.download_cache / self._getArchiveName(spec)
        
        if not p1.exists():
            raise RuntimeError("Missing archive.")

        try:
            archive = zipfile.ZipFile(p1, "r")
        except (OSError, zipfile.error):
            raise RuntimeError("Unable to open file '%s', probably bad download." % p1)

        for member in archive.infolist():
            if member.is_dir():
                logger.debug("Member '%s' is a directory, skipping..." % member.filename)
                continue
            p2 = self.path / member.filename

            logger.info("Creating file '%s'..." % p2)
            parent = p2.parent
            os.makedirs(parent, exist_ok=True)
            with open(p2, "wb") as f:
                f.write(archive.read(member))

        archive.close()

        #Create local spec file
        spec.is_remote = False
        spec.is_local = True
        spec.need_install = False
        self._writeSpec(spec)

    def _uninstallMod(self, spec):

        """
        Removes all files belonging to this mod.

        spec must be a ModSpec instance.
        """

        if not spec.is_local:
            raise RuntimeError("This mod is not currently installed.")

        for file in spec.files:
            name = file["file"]

            path = self.path / name
            self.logger.debug("Removing file '%s'..." % path)
            try:
                os.remove(path)
            except OSError as e:
                self.logger.error("Unable to remove file '%s': %s" % (path, str(e)))
                continue

        #Remove spec file
        try:
            os.remove(self.manifest_cache / self._getSpecFileName(spec))
        except:
            self.logger.exception("An error occured while attempting to remove the manifest file: ")

    def _getSpecFileName(self, spec):

        """
        Return a filename suitable for serialized ModSpec files.
        """

        return "%s_%s.json" % (spec.name, ".".join(map(str, spec.version)))

    def _writeSpec(self, spec):

        """
        Write a ModSpec to the local manifest cache.
        """

        with open(self.manifest_cache / self._getSpecFileName(spec), "w") as f:
            spec.writeSpecFile(f)

    def _getArchiveName(self, spec):

        """
        Return a filename suitable for mod downloads.
        """

        return "%s_%s.zip" % (spec.name, ".".join(map(str, spec.version)))

    def _verifyArchive(self, spec, path):

        """
        Verify the integrity of the downloaded mod archive
        by comparing the files inside with the provided MD5
        hashes.
        """

        self.logger.debug("Verifying download...")

        hashes = {}
        for i in spec.files:
            hashes[i["file"]] = i["hash"]

        try:
            archive = zipfile.ZipFile(path, "r")
        except (OSError, zipfile.error):
            self.logger.error("Unable to open file '%s', probably bad download." % path)
            return False

        for member in archive.infolist():
            if member.is_dir():
                self.logger.debug("Member '%s' is a directory, skipping..." % member.filename)
                continue
        
            #We're relying on the fact here that no errors occur while copying
            #the files from the archive to the disk. I trust the operating
            #system to be capable of ensuring that data is written in a
            #way that ensures integrity. The main risk comes from incomplete
            #dowloads or drive-by malware, which would be caught by a simple
            #hash for each archive. For some reason though, the guys over at
            #beatmods.com decided to include a separate hash for each archive
            #member instead.
            if not member.filename in hashes:
                logger.warn("No hash entry found for file '%s', bad archive?" % member.filename)    
                
            else:
                logger.debug("Validating file '%s'..." % member.filename)
                if not validateFile(archive.read(member.filename), hashes[member.filename]):
                    raise RuntimeError("MD5 mismatch for file '%s'." % member.filename)

        archive.close()
        return True

    def _downloadMod(self, spec):

        """
        Downloads a mod from a spec.

        spec must be a ModSpec instance.
        """

        self.logger.debug("Downloading mod '%s'..." % spec.name)
        f = downloadMod(spec.url)
        name = self._getArchiveName(spec)
        p = self.download_cache / name
        with open(p, "wb") as f2:
            f2.write(f.read())

        spec._archive = p
        self._verifyArchive(spec, p)

        return True

    def patch(self):

        """
        Runs the patcher.

        This method will first uninstall all mods that are marked to be removed
        as well as those that will be updated to prevent incompatibilities due
        to dead code from older versions.

        Next, all core mods that need to be updated or installed will be patched.
        After this, all other mods are patched in order of first in first out.
        """

        self.logger.info("Uninstalling mods...")
        uninstall = []
        uninstall.extend(self.need_uninstall)
        uninstall.extend(self.need_update) #Uninstall mods that need to be updated

        for mod in uninstall:
            try:
                self._uninstallMod(mod)
            except Exception as e:
                self.logger.exception("Uninstalling mod '%s' failed:" % mod.name)

        self.logger.info("Preparing installation...")

        install = []
        for mod in self.need_update:
            #We need to substitute local mods for remotes here because
            #the local version still has the outdated download link and
            #version number.
            #We don't need bother removing the old local version from the list as its
            #spec file is automatically deleted and everything will be
            #reloaded after the patch is complete.
            for remote in self.remote:
                if remote.name == mod.name:
                    install.append(remote)
                    break
            else:
                self.logger.warn("Unable to find remote spec for mod '%s', skipping" % mod.name)
        install.extend(self.need_install)

        self.logger.info("Downloading mods...")
        for mod in install[:]:
            if mod._archive:
                self.logger.info("Skipping package '%s' download, found local copy at '%s'." % (mod.name, mod._archive))
                continue
            try:
                self._downloadMod(mod)
            except Exception as e:
                self.logger.exception("Downloading mod '%s' failed:" % mod.name)
                #here we are removing mods that have failed downloading
                #to speed up installation and prevent errors down the line
                install.remove(mod)

        #Install core mods first, then everything else.
        #Technically this shouldn't be necessary because of how
        #IPA works, but we'll do it just in case.
        #This way we can guarantee all core mods to be installed and
        #their files to be available to other mods.

        #inefficient list management lol
        core_install = []
        generic_install = []

        for mod in install:
            if mod.category == ModCategories.CORE:
                core_install.append(mod)
            else:
                generic_install.append(mod)

        self.logger.info("Installing core mods...")
        for mod in core_install:
            try:
                self._installMod(mod)
            except Exception as e:
                self.logger.exception("Installing mod '%s' failed:" % mod.name)

        self.logger.info("Installing generic mods...")
        for mod in generic_install:
            try:
                self._installMod(mod)
            except Exception as e:
                self.logger.exception("Installing mod '%s' failed:" % mod.name)

        self.logger.info("Cleaning up...")
        for i in list(self.download_cache.iterdir()):
            try:
                os.remove(i)
            except OSError:
                pass

        self.logger.info("Done!")

    def cleanInstall(self):

        """
        Runs the patcher twice, removing and subsequently re-adding all
        installed mod packages.
        Use this to resolve issues with corrupted mod installations.
        """

        specs = []
        for spec in self.remote:
            if spec.is_local:
                specs.append(spec)

        self.logger.info("Removing all mods...")
        for mod in specs:
            self.removeMod(mod, True)

        self.patch()
        self.refreshMods()

        self.logger.info("Reinstalling all mods...")
        for mod in specs:
            self.addMod(mod)

        self.patch()

        self.logger.info("Clean installation completed.")

    def addMod(self, spec, fromSpec=None):

        """
        Add a mod to the patch list.

        This method will automatically queue up this mod and
        all its dependencies to be installed/updated when patching.
        If this mod or one of its dependencies are already installed and
        up to date, the respective packages will be ignored.
        """

        if fromSpec:
            self.logger.info("Installing mod '%s' from dependency '%s'..." % (spec.name, fromSpec.name))

        #Step one: check if package is already installed:
        for mod in self.local:
            if mod.name == spec.name:
                if mod.need_uninstall:
                    #package is installed but marked for uninstallation, remove marker
                    self.logger.info("Package '%s' is marked for uninstallation, readding..." % mod.name)
                    try:
                        self.need_uninstall.remove(mod)
                    except:
                        pass
                    mod.need_uninstall = False
                    return
                elif mod.need_install:
                    #mod already marked for install, skip silently
                    return
                else:
                    self.logger.info("Mod package '%s' is already installed, skipping." % spec.name)
                    return

        #Step two: get remote package
        for mod in self.remote:
            if mod.name == spec.name:
                spec = mod
                break
        else:
            self.logger.warn("Mod package '%s' isn't in the remote repository, installing in local only mode." % spec.name)

        if fromSpec:
            spec._source = fromSpec

        #Step three: Mark for install
        spec.need_install = True
        self.local.append(spec)
        self.need_install.append(spec)

        #Step four: Process dependencies
        for depend in spec.dependencies:
            dep = depend["name"]
            self.logger.debug("Searching for local package '%s'..." % dep)
            
            for mod in self.local:
                if mod.name == dep:
                    self.logger.debug("Found installation for package on local machine, skipping")
                    break
            else:
                self.logger.debug("Searching for remote package '%s'..." % dep)
                for mod in self.remote:
                    if mod.name == dep:
                        self.addMod(mod, spec)
                        break
                else:
                    self.logger.warn("Unable to install dependency package '%s' for mod '%s': Package not found." % (dep, spec.name))

        self.logger.info("Mod package '%s' staged for installation." % spec.name)
        return True

    def removeMod(self, spec, force=False):

        """
        Remove a mod from the patch list.

        By default this method will raise an exception if this mod is
        a dependency for other mods. If force is set to True, the mod
        will be deinstalled regardless.
        """

        #Step one: Make sure the mod is installed:
        if spec.need_install:
            #If the mod is marked for install, we can immediately remove it from the list,
            #since it isn't actually installed yet.
            self.need_install.remove(spec)
            spec.need_install = False
            self.local.remove(spec)
            self.logger.info("Unstaging mod '%s' from installation." % spec.name)
            return True
        elif not spec.is_local:
            self.logger.warn("Cannot remove mod '%s': This package is not currently installed." % spec.name)
            return False

        #Step two: Do any other mods depend on this package?
        deps = []
        for mod in self.local:
            for dep in mod.dependencies:
                if dep["name"] == spec.name:
                    self.logger.warn("The mod '%s' is a dependency for package '%s'" % (spec.name, mod.name))
                    deps.append(mod.name)
        if deps and not force:
            raise RuntimeError("Other mods depend on this package. Uninstall the following mods first: " + ", ".join(deps))

        #Step three: Mark for uninstallation
        if spec in self.need_update:
            self.need_update.remove(spec)

        spec.need_uninstall = True
        spec.need_install = False
        spec.need_update = False

        self.need_uninstall.append(spec)

        self.logger.info("Mod '%s' staged for deinstallation." % spec.name)
        return True

    def ignoreMod(self, spec):

        """
        Mark a mod as ignored.

        This method will permanently remove a (local) mod from the list
        of tracked mods. This means it will no longer be updated and no
        dependency checks will be made. It also means that the mod cannot
        be uninstalled using the patcher. Be aware that reinstalling the
        mod through the patcher deactivates this behavior.
        """

        #TODO: Implement
        pass