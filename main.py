"""
Pro Note - a modern, tabbed notepad built with Python's standard library (tkinter).

Run:  python pro_note.py [file1 file2 ...]
Requires: Python 3.8+ (no third-party packages)
"""
import os
import sys
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox, simpledialog, font as tkfont

APP_NAME = "Pro Note"
MOD = "Command" if sys.platform == "darwin" else "Control"
FILETYPES = [("Text files", "*.txt"), ("Markdown", "*.md"), ("Python", "*.py"), ("All files", "*.*")]

THEMES = {
    "light": dict(bg="#ffffff", fg="#1f2328", chrome="#f3f4f6", gutter="#f9fafb", muted="#9ca3af",
                  select="#bfdbfe", line="#f1f5f9", found="#fde68a", accent="#2563eb"),
    "dark": dict(bg="#1e1f22", fg="#e5e7eb", chrome="#2b2d31", gutter="#232427", muted="#6b7280",
                 select="#264f78", line="#26282c", found="#854d0e", accent="#60a5fa"),
}


def default_mono():
    if sys.platform.startswith("win"):
        return "Consolas"
    if sys.platform == "darwin":
        return "Menlo"
    return "DejaVu Sans Mono"


class EditorTab(ttk.Frame):
    """One document: text area + line-number gutter + scrollbars."""

    def __init__(self, master, app, path=None):
        super().__init__(master)
        self.app, self.path, self.dirty = app, path, False

        self.text = tk.Text(self, undo=True, maxundo=-1, borderwidth=0, highlightthickness=0,
                            padx=10, pady=8, wrap="word" if app.wrap.get() else "none",
                            font=app.font, insertwidth=2, spacing1=1, spacing3=1)
        self.gutter = tk.Canvas(self, width=50, highlightthickness=0, borderwidth=0)
        self.vsb = ttk.Scrollbar(self, command=self.text.yview)
        self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=self._yscroll, xscrollcommand=self.hsb.set)

        self.gutter.grid(row=0, column=0, sticky="ns")
        self.text.grid(row=0, column=1, sticky="nsew")
        self.vsb.grid(row=0, column=2, sticky="ns")
        self.hsb.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        self.text.bind("<<Modified>>", self._modified)
        self.text.bind("<KeyRelease>", self._cursor_moved)
        self.text.bind("<ButtonRelease-1>", self._cursor_moved)
        self.text.bind("<Configure>", lambda e: self.redraw_gutter())
        self.text.bind("<Tab>", self._insert_spaces)
        self.text.bind(f"<{MOD}-MouseWheel>", lambda e: self.app.zoom(1 if e.delta > 0 else -1) or "break")
        self.text.bind(f"<{MOD}-Button-4>", lambda e: self.app.zoom(1) or "break")
        self.text.bind(f"<{MOD}-Button-5>", lambda e: self.app.zoom(-1) or "break")
        for seq, func in app.shortcuts.items():
            self.text.bind(seq, lambda e, f=func: (f(), "break")[1])
        self.apply_theme()

    # ---- theming / drawing -------------------------------------------------
    def apply_theme(self):
        t = self.app.theme
        self.text.configure(bg=t["bg"], fg=t["fg"], insertbackground=t["fg"],
                            selectbackground=t["select"], selectforeground=t["fg"])
        self.text.tag_configure("current_line", background=t["line"])
        self.text.tag_configure("found", background=t["found"], foreground=t["fg"])
        self.text.tag_raise("sel")
        self.gutter.configure(bg=t["gutter"])
        self.redraw_gutter()

    def redraw_gutter(self):
        t = self.app.theme
        self.gutter.delete("all")
        last_line = int(self.text.index("end-1c").split(".")[0])
        width = self.app.font.measure("0") * max(3, len(str(last_line))) + 22
        if int(self.gutter.cget("width")) != width:
            self.gutter.configure(width=width)
        cur = int(self.text.index("insert").split(".")[0])
        idx = self.text.index("@0,0")
        while True:
            info = self.text.dlineinfo(idx)
            if info is None:
                break
            line = int(idx.split(".")[0])
            self.gutter.create_text(width - 10, info[1] + info[3] // 2, anchor="e", text=str(line),
                                    font=self.app.font, fill=t["fg"] if line == cur else t["muted"])
            nxt = self.text.index(f"{idx}+1line")
            if nxt == idx:
                break
            idx = nxt

    def highlight_line(self):
        self.text.tag_remove("current_line", "1.0", "end")
        self.text.tag_add("current_line", "insert linestart", "insert lineend+1c")

    # ---- events --------------------------------------------------------------
    def _yscroll(self, first, last):
        self.vsb.set(first, last)
        self.redraw_gutter()

    def _modified(self, _=None):
        if self.text.edit_modified():
            self.dirty = True
            self.text.edit_modified(False)
            self.app.refresh_titles()
            self._cursor_moved()

    def _cursor_moved(self, _=None):
        self.highlight_line()
        self.redraw_gutter()
        self.app.update_status()

    def _insert_spaces(self, _):
        self.text.insert("insert", " " * 4)
        return "break"


class FindReplace(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Find & Replace")
        self.transient(app)
        self.resizable(False, False)
        self.find_var, self.repl_var = tk.StringVar(), tk.StringVar()
        self.case_var, self.regex_var = tk.BooleanVar(), tk.BooleanVar()
        self.msg = tk.StringVar()

        f = ttk.Frame(self, padding=14)
        f.grid()
        ttk.Label(f, text="Find").grid(row=0, column=0, sticky="w", pady=4)
        self.find_entry = ttk.Entry(f, textvariable=self.find_var, width=32)
        self.find_entry.grid(row=0, column=1, columnspan=2, padx=8)
        ttk.Label(f, text="Replace").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(f, textvariable=self.repl_var, width=32).grid(row=1, column=1, columnspan=2, padx=8)
        ttk.Checkbutton(f, text="Match case", variable=self.case_var).grid(row=2, column=1, sticky="w")
        ttk.Checkbutton(f, text="Regex", variable=self.regex_var).grid(row=2, column=2, sticky="w")
        bar = ttk.Frame(f)
        bar.grid(row=3, column=0, columnspan=3, pady=(10, 0))
        for i, (label, cmd) in enumerate([("Previous", lambda: self.find(False)), ("Next", lambda: self.find(True)),
                                          ("Replace", self.replace), ("Replace All", self.replace_all)]):
            ttk.Button(bar, text=label, command=cmd).grid(row=0, column=i, padx=3)
        ttk.Label(f, textvariable=self.msg).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self.find_entry.bind("<Return>", lambda e: self.find(True))
        self.bind("<Escape>", lambda e: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.find_entry.focus_set()

    def close(self):
        tab = self.app.current()
        if tab:
            tab.text.tag_remove("found", "1.0", "end")
        self.app.find_dialog = None
        self.destroy()

    def _search(self, text, start, forward=True, stop=None):
        count = tk.IntVar()
        try:
            pos = text.search(self.find_var.get(), start, stopindex=stop, forwards=forward,
                              nocase=not self.case_var.get(), regexp=self.regex_var.get(), count=count)
        except tk.TclError as e:
            self.msg.set(f"Invalid pattern: {e}")
            return None, 0
        return pos, count.get()

    def find(self, forward=True):
        tab = self.app.current()
        if not tab or not self.find_var.get():
            return
        text = tab.text
        text.tag_remove("found", "1.0", "end")
        if forward:
            start = text.index("sel.last") if text.tag_ranges("sel") else text.index("insert")
        else:
            start = text.index("sel.first") if text.tag_ranges("sel") else text.index("insert")
        pos, n = self._search(text, start, forward)
        if not pos:  # wrap around
            pos, n = self._search(text, "1.0" if forward else "end", forward)
        if not pos:
            self.msg.set("No matches found")
            return
        end = f"{pos}+{max(n, 1)}c"
        text.tag_remove("sel", "1.0", "end")
        text.tag_add("sel", pos, end)
        text.mark_set("insert", end if forward else pos)
        text.see(pos)
        self.msg.set("")
        tab._cursor_moved()

    def replace(self):
        tab = self.app.current()
        if not tab:
            return
        if tab.text.tag_ranges("sel"):
            sel = tab.text.get("sel.first", "sel.last")
            flags = 0 if self.case_var.get() else 2  # re.IGNORECASE
            import re
            pattern = self.find_var.get() if self.regex_var.get() else re.escape(self.find_var.get())
            try:
                if re.fullmatch(pattern, sel, flags):
                    tab.text.delete("sel.first", "sel.last")
                    tab.text.insert("insert", self.repl_var.get())
            except re.error:
                pass
        self.find(True)

    def replace_all(self):
        tab = self.app.current()
        if not tab or not self.find_var.get():
            return
        text, idx, total = tab.text, "1.0", 0
        text.edit_separator()
        while True:
            pos, n = self._search(text, idx, True, stop="end")
            if not pos or n == 0:
                break
            text.delete(pos, f"{pos}+{n}c")
            text.insert(pos, self.repl_var.get())
            idx = f"{pos}+{len(self.repl_var.get())}c"
            total += 1
        text.edit_separator()
        self.msg.set(f"Replaced {total} occurrence(s)")


class ProNote(tk.Tk):
    def __init__(self, files=()):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1000x680")
        self.minsize(520, 360)

        self.dark = tk.BooleanVar(value=False)
        self.wrap = tk.BooleanVar(value=True)
        self.show_status = tk.BooleanVar(value=True)
        self.font = tkfont.Font(family=default_mono(), size=12)
        self.theme = THEMES["light"]
        self.untitled_count = 0
        self.find_dialog = None

        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.shortcuts = {
            f"<{MOD}-n>": self.new_tab, f"<{MOD}-o>": self.open_file, f"<{MOD}-s>": self.save,
            f"<{MOD}-Shift-S>": lambda: self.save(save_as=True), f"<{MOD}-w>": self.close_tab,
            f"<{MOD}-f>": self.open_find, f"<{MOD}-h>": self.open_find, f"<{MOD}-g>": self.goto_line,
            f"<{MOD}-a>": self.select_all, f"<{MOD}-z>": lambda: self._edit("<<Undo>>"),
            f"<{MOD}-y>": lambda: self._edit("<<Redo>>"), f"<{MOD}-equal>": lambda: self.zoom(1),
            f"<{MOD}-plus>": lambda: self.zoom(1), f"<{MOD}-minus>": lambda: self.zoom(-1),
            f"<{MOD}-0>": lambda: self.zoom(0), "<F5>": self.insert_datetime,
        }

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self._tab_changed())
        self.notebook.bind("<Button-2>", self._middle_click_close)

        self.status = ttk.Frame(self, padding=(12, 4))
        self.status_left = ttk.Label(self.status, text="Ready")
        self.status_right = ttk.Label(self.status, text="")
        self.status_left.pack(side="left")
        self.status_right.pack(side="right")
        self.status.pack(fill="x", side="bottom")

        self._build_menu()
        for seq, func in self.shortcuts.items():
            self.bind(seq, lambda e, f=func: (f(), "break")[1])
        self.protocol("WM_DELETE_WINDOW", self.quit_app)

        self.apply_theme()
        for path in files:
            self.open_file(path)
        if not self.notebook.tabs():
            self.new_tab()

    # ---- UI construction -------------------------------------------------------
    def _build_menu(self):
        bar = tk.Menu(self)
        self.menus = [bar]

        def menu(label):
            m = tk.Menu(bar, tearoff=False)
            bar.add_cascade(label=label, menu=m)
            self.menus.append(m)
            return m

        acc = "Cmd" if MOD == "Command" else "Ctrl"
        m = menu("File")
        m.add_command(label="New Tab", accelerator=f"{acc}+N", command=self.new_tab)
        m.add_command(label="Open...", accelerator=f"{acc}+O", command=self.open_file)
        m.add_command(label="Save", accelerator=f"{acc}+S", command=self.save)
        m.add_command(label="Save As...", accelerator=f"{acc}+Shift+S", command=lambda: self.save(save_as=True))
        m.add_separator()
        m.add_command(label="Close Tab", accelerator=f"{acc}+W", command=self.close_tab)
        m.add_command(label="Exit", command=self.quit_app)

        m = menu("Edit")
        m.add_command(label="Undo", accelerator=f"{acc}+Z", command=lambda: self._edit("<<Undo>>"))
        m.add_command(label="Redo", accelerator=f"{acc}+Y", command=lambda: self._edit("<<Redo>>"))
        m.add_separator()
        m.add_command(label="Cut", accelerator=f"{acc}+X", command=lambda: self._edit("<<Cut>>"))
        m.add_command(label="Copy", accelerator=f"{acc}+C", command=lambda: self._edit("<<Copy>>"))
        m.add_command(label="Paste", accelerator=f"{acc}+V", command=lambda: self._edit("<<Paste>>"))
        m.add_command(label="Select All", accelerator=f"{acc}+A", command=self.select_all)
        m.add_separator()
        m.add_command(label="Find & Replace...", accelerator=f"{acc}+F", command=self.open_find)
        m.add_command(label="Go to Line...", accelerator=f"{acc}+G", command=self.goto_line)
        m.add_command(label="Insert Date/Time", accelerator="F5", command=self.insert_datetime)

        m = menu("View")
        m.add_checkbutton(label="Dark Mode", variable=self.dark, command=self.apply_theme)
        m.add_checkbutton(label="Word Wrap", variable=self.wrap, command=self.toggle_wrap)
        m.add_checkbutton(label="Status Bar", variable=self.show_status, command=self.toggle_status)
        m.add_separator()
        m.add_command(label="Zoom In", accelerator=f"{acc}++", command=lambda: self.zoom(1))
        m.add_command(label="Zoom Out", accelerator=f"{acc}+-", command=lambda: self.zoom(-1))
        m.add_command(label="Reset Zoom", accelerator=f"{acc}+0", command=lambda: self.zoom(0))

        m = menu("Help")
        m.add_command(label=f"About {APP_NAME}", command=lambda: messagebox.showinfo(
            APP_NAME, f"{APP_NAME} 1.0\nA fast, modern, tabbed notepad built with Python & tkinter."))
        self.config(menu=bar)

    def apply_theme(self):
        self.theme = t = THEMES["dark" if self.dark.get() else "light"]
        s = self.style
        s.configure(".", background=t["chrome"], foreground=t["fg"], bordercolor=t["chrome"], focuscolor=t["chrome"])
        s.configure("TFrame", background=t["chrome"])
        s.configure("TLabel", background=t["chrome"], foreground=t["fg"])
        s.configure("TCheckbutton", background=t["chrome"], foreground=t["fg"])
        s.configure("TEntry", fieldbackground=t["bg"], foreground=t["fg"])
        s.configure("TButton", background=t["bg"], foreground=t["fg"], padding=(10, 4), borderwidth=1)
        s.map("TButton", background=[("active", t["select"])])
        s.configure("TNotebook", background=t["chrome"], borderwidth=0, tabmargins=(8, 6, 8, 0))
        s.configure("TNotebook.Tab", background=t["chrome"], foreground=t["muted"], padding=(16, 7), borderwidth=0)
        s.map("TNotebook.Tab", background=[("selected", t["bg"])], foreground=[("selected", t["fg"])])
        for orient in ("Vertical", "Horizontal"):
            s.configure(f"{orient}.TScrollbar", background=t["muted"], troughcolor=t["gutter"],
                        bordercolor=t["gutter"], arrowcolor=t["fg"], relief="flat")
        self.configure(bg=t["chrome"])
        for m in self.menus:
            m.configure(bg=t["chrome"], fg=t["fg"], activebackground=t["accent"], activeforeground="#ffffff")
        for tab in self.tabs():
            tab.apply_theme()

    # ---- helpers ----------------------------------------------------------------
    def tabs(self):
        return [self.nametowidget(w) for w in self.notebook.tabs()]

    def current(self):
        sel = self.notebook.select()
        return self.nametowidget(sel) if sel else None

    def tab_name(self, tab):
        return os.path.basename(tab.path) if tab.path else tab.untitled_name

    def refresh_titles(self):
        for tab in self.tabs():
            self.notebook.tab(tab, text=self.tab_name(tab) + ("  ●" if tab.dirty else ""))
        tab = self.current()
        if tab:
            self.title(f"{'*' if tab.dirty else ''}{self.tab_name(tab)} — {APP_NAME}")

    def update_status(self):
        tab = self.current()
        if not tab:
            return
        ln, col = tab.text.index("insert").split(".")
        content = tab.text.get("1.0", "end-1c")
        zoom = round(self.font.cget("size") / 12 * 100)
        self.status_left.config(text=tab.path or "Unsaved document")
        self.status_right.config(text=f"Ln {ln}, Col {int(col) + 1}   |   {len(content.split())} words   |   "
                                      f"{len(content)} chars   |   UTF-8   |   {zoom}%")

    def _tab_changed(self):
        self.refresh_titles()
        self.update_status()
        tab = self.current()
        if tab:
            tab.text.focus_set()
            tab.highlight_line()
            tab.redraw_gutter()

    def _edit(self, event_name):
        tab = self.current()
        if tab:
            try:
                tab.text.event_generate(event_name)
            except tk.TclError:
                pass

    def select_all(self):
        tab = self.current()
        if tab:
            tab.text.tag_add("sel", "1.0", "end-1c")
            tab.text.mark_set("insert", "end-1c")

    def _middle_click_close(self, event):
        try:
            idx = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        self.close_tab(self.tabs()[idx])

    # ---- file operations --------------------------------------------------------
    def new_tab(self, path=None):
        tab = EditorTab(self.notebook, self, path)
        self.untitled_count += 1
        tab.untitled_name = f"Untitled {self.untitled_count}"
        self.notebook.add(tab, text=tab.untitled_name)
        self.notebook.select(tab)
        return tab

    def open_file(self, path=None):
        if not path:
            paths = filedialog.askopenfilenames(filetypes=FILETYPES)
            for p in paths:
                self.open_file(p)
            return
        path = os.path.abspath(path)
        for tab in self.tabs():
            if tab.path == path:
                self.notebook.select(tab)
                return
        try:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(path, "r", encoding="latin-1") as f:
                    content = f.read()
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Could not open file:\n{e}")
            return
        cur = self.current()
        if cur and not cur.path and not cur.dirty and not cur.text.get("1.0", "end-1c"):
            tab = cur  # reuse the empty untitled tab
            tab.path = path
        else:
            tab = self.new_tab(path)
        tab.text.insert("1.0", content)
        tab.text.edit_reset()
        tab.text.edit_modified(False)
        tab.dirty = False
        tab.text.mark_set("insert", "1.0")
        self.refresh_titles()
        self.update_status()

    def save(self, tab=None, save_as=False):
        tab = tab if isinstance(tab, EditorTab) else self.current()
        if not tab:
            return False
        path = tab.path
        if save_as or not path:
            path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=FILETYPES,
                                                initialfile=self.tab_name(tab))
            if not path:
                return False
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(tab.text.get("1.0", "end-1c"))
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Could not save file:\n{e}")
            return False
        tab.path, tab.dirty = path, False
        self.refresh_titles()
        self.update_status()
        return True

    def confirm_close(self, tab):
        """Return True if it is OK to discard/close this tab."""
        if not tab.dirty:
            return True
        self.notebook.select(tab)
        ans = messagebox.askyesnocancel(APP_NAME, f"Save changes to {self.tab_name(tab)}?")
        if ans is None:
            return False
        return self.save(tab) if ans else True

    def close_tab(self, tab=None):
        tab = tab if isinstance(tab, EditorTab) else self.current()
        if not tab or not self.confirm_close(tab):
            return
        self.notebook.forget(tab)
        tab.destroy()
        if not self.notebook.tabs():
            self.new_tab()

    def quit_app(self):
        for tab in self.tabs():
            if not self.confirm_close(tab):
                return
        self.destroy()

    # ---- editing / view features --------------------------------------------------
    def open_find(self):
        if self.find_dialog and self.find_dialog.winfo_exists():
            self.find_dialog.lift()
            self.find_dialog.find_entry.focus_set()
            return
        self.find_dialog = FindReplace(self)
        tab = self.current()
        if tab and tab.text.tag_ranges("sel"):
            self.find_dialog.find_var.set(tab.text.get("sel.first", "sel.last"))

    def goto_line(self):
        tab = self.current()
        if not tab:
            return
        total = int(tab.text.index("end-1c").split(".")[0])
        n = simpledialog.askinteger("Go to Line", f"Line number (1-{total}):", minvalue=1, maxvalue=total, parent=self)
        if n:
            tab.text.mark_set("insert", f"{n}.0")
            tab.text.see(f"{n}.0")
            tab._cursor_moved()

    def insert_datetime(self):
        tab = self.current()
        if tab:
            tab.text.insert("insert", datetime.now().strftime("%Y-%m-%d %H:%M"))

    def toggle_wrap(self):
        for tab in self.tabs():
            tab.text.configure(wrap="word" if self.wrap.get() else "none")
            tab.redraw_gutter()

    def toggle_status(self):
        if self.show_status.get():
            self.status.pack(fill="x", side="bottom")
        else:
            self.status.pack_forget()

    def zoom(self, delta):
        size = 12 if delta == 0 else max(6, min(48, self.font.cget("size") + delta))
        self.font.configure(size=size)
        for tab in self.tabs():
            tab.redraw_gutter()
        self.update_status()


if __name__ == "__main__":
    ProNote(sys.argv[1:]).mainloop()M
