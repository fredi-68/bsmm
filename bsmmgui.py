#Unofficial beatmods.com mod downloader & patcher (GUI)
#
#Copyright (c) fredi_68 2019
#All rights reserved.

import json
import logging
import os
import subprocess
import zipfile
import pathlib
import sys

from tkinter import *
from tkinter.ttk import *
from tkinter import messagebox
from tkinter import filedialog

import beatmodsapi
from beatmodsapi import APP_TYPE

class ModView(Frame):

    COLUMNS = [
        "Name",
        "Version",
        "Status",
        "Source",
        "Game Version"
        ]

    TAGS = {
        "green": {"foreground": "lime", "background": "grey"},
        "red": {"foreground": "red"},
        "orange": {"foreground": "orange"}
        }

    logger = logging.getLogger("bsmmgui.ModView")

    def __init__(self, master=None):

        super().__init__(master)
        self.tree = Treeview(self, columns=self.COLUMNS, displaycolumns="#all", show="headings", selectmode="browse")

        self.specCache = {}
        self._prepare()

        self.tree.pack(fill="both")

    def _prepare(self):

        for tag, opts in self.TAGS.items():
            self.tree.tag_configure(tag, **opts)

        for col in self.COLUMNS:
            self.tree.heading(col, text=col)

    def _add(self, spec):

        tags = []

        #Show dependencies
        source = getattr(spec, "_source", "")
        if source:
            source = "from "+source.name
        
        #Display current package status
        if spec.need_install:
            status = "install"
            tags.append("green")
        elif spec.is_remote and not spec.is_local:
            status = "not installed"
        elif spec.is_local:
            #installed
            if spec.need_update:
                status = "update pending"
                tags.append("orange")
            elif spec.need_uninstall:
                status = "uninstall"
                tags.append("red")
            else:
                status = "installed"
        else:
            status = ""

        version = ".".join(map(str, spec.version))
        gameVersion = ".".join(map(str, spec.gameVersion))

        iid = self.tree.insert("", END, values=[spec.name, version, status, source, gameVersion], tags=tags)
        self.specCache[iid] = spec #keep a reference for the event handlers

    def clear(self):

        for item in self.tree.get_children(""):
            self.tree.delete(item)

    def updateView(self, specs):

        """
        Reload the view from the provided list of ModSpecs.
        """

        self.specCache.clear()
        self.clear()
        for mod in specs:
            self._add(mod)

    def getSelected(self):

        """
        Return the selected item
        """

        x = self.tree.focus()
        self.logger.debug("Selected item is %s" % str(x))
        if x == ():
            return None
        if isinstance(x, (tuple, list)):
            x = x[0]
        return self.specCache.get(x, None)

class App(Frame):

    logger = logging.getLogger("bsmmgui.app")

    def __init__(self, master = None, cnf = {}, **kw):
        
        super().__init__(master)

        self.loadSettings()

        self.pathLabel = Label(self, text="BeatSaber installation path:")
        self.pathLabel.pack()
        self.pathEntry = Entry(self)
        self.pathEntry.insert(0, self.settings.get("application_path", ""))
        self.pathEntry.pack(fill="x")

        self.btnPanel = Frame(self)
        self.btnRefresh = Button(self.btnPanel, text="Refresh", command=self.refreshModList)
        self.btnRefresh.pack(anchor="w", side="left")
        self.btnReinstall = Button(self.btnPanel, text="Reinstall", command=self.reinstallAll)
        self.btnReinstall.pack(anchor="w", side="left")
        self.btnLocal = Button(self.btnPanel, text="Add archive...", command=self.addLocalPackage)
        self.btnLocal.pack(anchor="w", side="left")
        self.btnPatch = Button(self.btnPanel, text="Patch", command=self.patchMods)
        self.btnPatch.pack(anchor="w", side="left")
        self.btnStart = Button(self.btnPanel, text="Start BeatSaber...", command=self.start)
        self.btnStart.pack(anchor="w", side="left")
        self.btnExit = Button(self.btnPanel, text="Exit", command=self.quit)
        self.btnExit.pack(anchor="w", side="left")
        self.btnPanel.pack(fill="x")

        self.modListFrame = Frame(self)
        self.mlLabel = Label(self.modListFrame, text="Available mods:")
        self.mlLabel.pack()
        self.modListView = ModView(self.modListFrame)
        self.modListView.pack(fill="both")
        self.btnMoveToInstall = Button(self.modListFrame, text="Install", command=self.addToList)
        self.btnMoveToInstall.pack(side="right")
        self.modListFrame.pack(fill="both")

        self.installListFrame = Frame(self)
        self.ilLabel = Label(self.installListFrame, text="Installed mods:")
        self.ilLabel.pack()
        self.installListView = ModView(self.installListFrame)
        self.installListView.pack(fill="both")
        self.btnMoveToAvailable = Button(self.installListFrame, text="Uninstall", command=self.removeFromList)
        self.btnMoveToAvailable.pack(side="right")
        self.installListFrame.pack(fill="both")

        self.pack(fill="both")

        self.initPatcher()

    def loadSettings(self):

        self.settings = {}
        try:
            with open("config.json", "rb") as f:
                self.settings = json.load(f)
        except:
            print("WARNING: Unable to load settings")

        logging.basicConfig(level=self.settings.get("log_level", logging.INFO))

    def updateViews(self):

        self.modListView.updateView(self.patcher.remote)
        self.installListView.updateView(self.patcher.local)

    def initPatcher(self):

        """
        Inits the patcher system.
        This method will (re)load the patcher instance, sync with
        remote and update the listviews.
        """

        path = self.pathEntry.get()
        if not path:
            messagebox.showinfo("Missing Game Directory", "Please specify your BeatSaber installation directory.")
            path = filedialog.askdirectory()
            if not path:
                return
            self.pathEntry.delete(0, END)
            self.pathEntry.insert(0, path)
        self.patcher = beatmodsapi.Patcher(path, APP_TYPE)
        self.patcher.refreshMods()
        self.updateViews()

    def refreshModList(self, event=None):

        self.initPatcher()

    def patchMods(self, event=None):

        self.patcher.patch()
        self.updateViews()
        messagebox.showinfo("Patch Successfull", "The game was successfully patched.")

    def addToList(self, event=None):

        s = self.modListView.getSelected()
        if not s:
            return
        self.patcher.addMod(s)
        self.updateViews()

    def removeFromList(self, event=None):
        
        s = self.installListView.getSelected()
        if not s:
            return
        try:
            self.patcher.removeMod(s)
        except RuntimeError as e:
            msg = "%s\n\nDo you wish to uninstall this package regardless? This may break other mods."
            again = messagebox.askyesno("Dependency Warning", msg % str(e))
            if again:
                self.patcher.removeMod(s, True) #Force deinstallation
        self.updateViews()

    def start(self, event=None):

        path = pathlib.Path(os.path.join(self.pathEntry.get(), "Beat Saber.exe"))
        if path.is_file():
            try:
                subprocess.Popen(path)
            except OSError:
                self.logger.exception("Unable to launch executable: ")

    def addLocalPackage(self, event=None):

        p = filedialog.askopenfilename(initialdir=os.getcwd())
        try:
            f = zipfile.ZipFile(p, mode="r")
        except Exception as e:
            messagebox.showerror("Unable to load mod from archive", "Opening archive failed: %s" % str(e))
            return

        spec = beatmodsapi.ModSpec.fromArchive(f)
        self.patcher.addMod(spec)
        self.updateViews()

    def reinstallAll(self, event=None):

        msg = """This will reinstall all mods currently managed by BSMM. Depending on your mods, your machine and your internet connection, this may take a while.
Do you wish to continue?"""

        cont = messagebox.askyesno("Clean Reinstall/Repair", msg)
        if not cont:
            return
        self.patcher.cleanInstall()
        self.updateViews()
        messagebox.showinfo("Success", "Successfully reinstalled all mods.")

    def quit(self):

        self.logger.debug("Saving config...")
        
        self.settings["application_path"] = self.pathEntry.get()

        try:
            with open("config.json", "w") as f:
                json.dump(self.settings, f)
        except:
            self.logger.warn("Failed to save config.")
        return super().quit()

if __name__ == "__main__":

    if "-debug" in sys.argv:
        logging.basicConfig(level=logging.DEBUG)
        logging.debug("Debug mode has been enabled.")

    tk = Tk()
    tk.minsize(500, 200)
    tk.title("fredi_68's Unofficial beatmods.com Mod Downloader & Patcher v%s (GUI)" % ".".join(map(str, beatmodsapi.__version__)))
    app = App(tk)
    tk.mainloop()
