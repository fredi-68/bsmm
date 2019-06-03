import logging
import argparse
import json
import sys

from beatmodsapi import Patcher, APP_TYPE

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("bsmm.cli")

def getStatusMsg(spec):

    if spec.need_install:
        status = "install"
    elif spec.is_remote and not spec.is_local:
        status = "not installed"
    elif spec.is_local:
        #installed
        if spec.need_update:
            status = "update pending"
        elif spec.need_uninstall:
            status = "uninstall"
        else:
            status = "installed"
    else:
        status = ""

    return status

def getPath():

    with open("config.json", "r") as f:
        d = json.load(f)
    return d["application_path"]

def searchMods(args):

    global patcher

    logger.debug("Fetching remote listing...")
    patcher.getRemote(args.query)
    print("Search results:\n")
    for spec in patcher.remote:

        print("%s (v%s)" % (spec.name, ".".join(map(str, spec.version))))

def listMods(args):

    global patcher

    logger.debug("Fetching local listing...")
    patcher.getLocal()
    print("Installed mods:\n")
    for spec in patcher.local:

        status = getStatusMsg(spec)
        print("%s (v%s) %s" % (spec.name, ".".join(map(str, spec.version)), status))

def installMods(args):

    global patcher

    mod = args.name
    logger.debug("Installing mod '%s'..." % mod)
    patcher.refreshMods(False)
    for s in patcher.remote:
        if s.name == mod:
            spec = s
            break
    else:
        raise RuntimeError("Unable to install mod '%s': Package not found in remote repository." % mod)

    patcher.addMod(spec)
    print("The following packages will be installed:")
    for mod in patcher.need_install:
        print("    "+mod.name)
    cont = input("Do you wish to continue? (y/n) [y]: ")
    if cont.lower() == n:
        return

    patcher.patch()

def uninstallMods(args):

    global patcher

    mod = args.name
    logger.debug("Uninstalling mod '%s'..." % mod)
    patcher.getLocal()

    for s in patcher.local:
        if s.name == mod:
            spec = s
            break
    else:
        raise RuntimeError("Unable to uninstall mod '%s': Package not found in local repository." % mod)

    patcher.removeMod(spec, args.force)
    patcher.patch()

parser = argparse.ArgumentParser(description="Command line utility for managing BeatSaber mods.")
parser.add_argument("--launch", action="store_true", help="Launch the game after executing the command.")
parser.add_argument("--update", action="store_true", help="Update all mods before executing the command.")
parser.add_argument("--path", action="store", help="Specify the path to the BeatSaber installation.")
parser.add_argument("--app_type", action="store", help="Specify the application type, typicaly 'steam' or 'oculus'.")
operations = parser.add_subparsers()

search = operations.add_parser("search", help="Search beatmods.com for mod packages.")
search.add_argument("query", nargs="?", default="")
search.set_defaults(func=searchMods)

install = operations.add_parser("install", help="Install a package.")
install.add_argument("name")
install.add_argument("--nodep", action="store_true", help="Don't install dependencies.")
install.set_defaults(func=installMods)

remove = operations.add_parser("remove", help="Uninstall a package.")
remove.add_argument("name")
remove.add_argument("--force", action="store_true", help="Force uninstall.")
remove.set_defaults(func=uninstallMods)

list = operations.add_parser("list", help="List installed mods.")
list.set_defaults(func=listMods)

args = parser.parse_args()

path = args.path
if not path:
    try:
        path = getPath()
    except (OSError, KeyError):
        logger.fatal("Unable to load configuration file, must specify a path!")
        sys.exit(1)

app_type = args.app_type or APP_TYPE

patcher = Patcher(path, app_type)
if args.update:
    patcher.refreshMods()
    patcher.patch()

try:
    args.func(args)
except AttributeError:
    pass #No action specified, just exit

if args.launch:
    #TODO: launch the game
    pass
