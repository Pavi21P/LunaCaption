"""Native Windows caption workspace; all Tk operations stay on the UI thread."""

from __future__ import annotations

import ntpath
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .batch import CaptionResult, run_batch
from .branding import (
    CARD,
    DANGER,
    LINE,
    MIST,
    MUTED,
    NIGHT,
    PLUM,
    SOFT,
    VIOLET,
    WASH,
    app_icon,
    logo_mark,
)
from .engine import DEVICES, LENGTHS, CaptionEngine, CaptionOptions
from .exporting import export_results
from .images import MAX_BATCH, SUPPORTED_SUFFIXES, ImageInputError, collect_images, load_image
from .recovery import RecoveryStore, default_recovery_directory
from .sessions import Session, load_session, save_session

FONT = "Segoe UI"
HEADING = "Segoe UI Semibold"
DISABLED_TEXT = "#a49cc4"
EDITOR_BG = "#f7f4fc"
SESSION_TYPES = [
    ("LunaCaption session", "*.lunacaption.json *.lumacaption.json"),
    ("JSON", "*.json"),
]
AUTOSAVE_DELAY_MS = 1000


class CaptionApp:
    def __init__(
        self,
        root: tk.Tk,
        *,
        offline: bool = False,
        device: str = "cpu",
        recovery_dir: Path | None = None,
        autosave: bool = True,
    ) -> None:
        if device not in DEVICES:
            raise ValueError("Choose cpu or cuda.")
        self.root = root
        self.rows: dict[str, CaptionResult] = {}
        self.current: str | None = None
        self.preview_photo = None
        self.preview_source: Image.Image | None = None
        self.events: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.engine: CaptionEngine | None = None
        self.busy = False
        self.dirty = False
        self.session_path: Path | None = None
        self.image_errors: dict[str, str] = {}
        self.beams = 3
        self.recovery: RecoveryStore | None = None
        self.autosave_after: str | None = None
        self.autosave_status = tk.StringVar(value="Automatic recovery is off.")
        self.closed = False
        self.batch_finished = 0
        self.batch_total = 0
        self.batch_error = False
        self.status = tk.StringVar(value="Add photos to begin. Your images stay on this computer.")
        self.summary = tk.StringVar(value="0 images")
        self.length = tk.StringVar(value="Standard")
        self.offline = tk.BooleanVar(value=offline)
        self.device = tk.StringVar(value=device)
        self.compute_status = tk.StringVar(value=f"LOCAL AI / {device.upper()} requested")
        self.recursive = tk.BooleanVar(value=False)
        self._build()
        for variable in (self.length, self.offline, self.recursive):
            variable.trace_add("write", self._settings_changed)
        if autosave:
            self._initialize_recovery(recovery_dir or default_recovery_directory())
        self.device.trace_add("write", self._device_changed)
        self.root.after(100, self._poll)
        self.root.after_idle(self._initial_focus)

    def _build(self) -> None:
        self.root.title("LunaCaption")
        self.root.geometry("1160x780")
        self.root.minsize(960, 680)
        self.root.configure(bg=MIST)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._apply_theme()
        self.icon_images = [
            ImageTk.PhotoImage(app_icon(size), master=self.root) for size in (16, 32, 48, 64)
        ]
        self.root.iconphoto(True, *self.icon_images)
        self.logo_image = ImageTk.PhotoImage(logo_mark(42), master=self.root)
        self.empty_image = ImageTk.PhotoImage(logo_mark(88), master=self.root)
        # A 1x1 transparent stand-in keeps the placeholder in pixel sizing when the
        # logo is hidden, so the label still requests no space of its own.
        self.blank_image = tk.PhotoImage(master=self.root, width=1, height=1)

        header = tk.Frame(self.root, bg=CARD, padx=24, pady=10)
        header.pack(fill="x")
        tk.Frame(self.root, bg=LINE, height=1).pack(fill="x")
        tk.Label(header, image=self.logo_image, bg=CARD).pack(side="left")
        tk.Label(header, text="LunaCaption", bg=CARD, fg=NIGHT, font=(FONT, 19, "bold")).pack(
            side="left", padx=(12, 0)
        )

        toolbar = ttk.Frame(self.root, padding=(24, 12, 24, 10))
        toolbar.pack(fill="x")
        self.add_button = ttk.Button(toolbar, text="+ Add images", command=self._add_files)
        self.add_button.pack(side="left")
        self.folder_button = ttk.Button(toolbar, text="Open folder", command=self._add_folder)
        self.folder_button.pack(side="left", padx=8)
        self.recursive_check = ttk.Checkbutton(
            toolbar, text="Include subfolders", variable=self.recursive
        )
        self.recursive_check.pack(side="left", padx=8)
        self.clear_button = ttk.Button(toolbar, text="Clear workspace", command=self._clear)
        self.clear_button.pack(side="right")

        sessions = ttk.Frame(self.root, padding=(24, 0, 24, 12))
        sessions.pack(fill="x")
        self.open_session_button = ttk.Button(
            sessions, text="Open session", command=self._open_session
        )
        self.open_session_button.pack(side="left")
        self.save_session_button = ttk.Button(
            sessions, text="Save session", command=self._save_session
        )
        self.save_session_button.pack(side="left", padx=8)
        ttk.Label(
            sessions, text="Save your queue, captions, and settings.", style="Muted.TLabel"
        ).pack(side="left", padx=8)

        self.relink_button = ttk.Button(sessions, text="Relink image...", command=self._relink)
        self.relink_button.pack(side="right")

        body = ttk.Frame(self.root, padding=(24, 0, 24, 10))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=2, minsize=300)
        body.columnconfigure(1, weight=3, minsize=430)
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body, style="Panel.TFrame", padding=14)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)
        queue_header = ttk.Frame(left, style="Card.TFrame")
        queue_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(queue_header, text="IMAGE QUEUE", style="Section.TLabel").pack(side="left")
        ttk.Label(queue_header, textvariable=self.summary, style="CardMuted.TLabel").pack(
            side="right"
        )

        tree_frame = ttk.Frame(left, style="Card.TFrame")
        tree_frame.grid(row=2, column=0, sticky="nsew")
        self.tree = ttk.Treeview(
            tree_frame, columns=("image", "state"), show="headings", selectmode="browse", height=11
        )
        self.tree.heading("image", text="Image")
        self.tree.heading("state", text="Status")
        self.tree.column("image", width=150, minwidth=110)
        self.tree.column("state", width=80, minwidth=75, stretch=False)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self._select)
        self.tree.tag_configure("error", foreground=DANGER)
        self.tree.tag_configure("done", foreground=VIOLET)

        options = ttk.Frame(left, style="Card.TFrame", padding=(0, 10, 0, 0))
        options.grid(row=3, column=0, sticky="ew")
        options.columnconfigure(1, weight=1)
        ttk.Label(options, text="Caption length", style="Card.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.length_box = ttk.Combobox(
            options, textvariable=self.length, values=list(LENGTHS), state="readonly", width=12
        )
        self.length_box.grid(row=0, column=1, sticky="e")
        ttk.Label(options, text="Compute device", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        self.device_box = ttk.Combobox(
            options, textvariable=self.device, values=DEVICES, state="readonly", width=12
        )
        self.device_box.grid(row=1, column=1, sticky="e", pady=(6, 0))
        self.offline_check = ttk.Checkbutton(
            left,
            text="Offline — use downloaded model only",
            variable=self.offline,
            style="Card.TCheckbutton",
        )
        self.offline_check.grid(row=4, column=0, sticky="w", pady=(10, 4))
        model_note = ttk.Label(
            left,
            text="First use downloads about 1 GB. No API key needed.",
            style="CardMuted.TLabel",
            wraplength=340,
        )
        model_note.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        # Wrap to the column so the note stays readable at the minimum window size.
        model_note.bind("<Configure>", lambda event: model_note.configure(wraplength=event.width))
        self.generate_button = ttk.Button(
            left, text="Generate captions", style="Primary.TButton", command=self._start
        )
        self.generate_button.grid(row=6, column=0, sticky="ew")
        actions = ttk.Frame(left, style="Card.TFrame")
        actions.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        self.retry_button = ttk.Button(actions, text="Retry errors", command=self._retry)
        self.retry_button.pack(side="left")
        self.cancel_button = ttk.Button(
            actions, text="Cancel batch", command=self._cancel, state="disabled"
        )
        self.cancel_button.pack(side="right")

        right = ttk.Frame(body, style="Panel.TFrame", padding=14)
        right.grid(row=0, column=1, sticky="nsew")
        ttk.Label(right, text="PREVIEW & CAPTION", style="Section.TLabel").pack(
            anchor="w", pady=(0, 10)
        )
        self.preview = tk.Label(
            right,
            text="A little context for every photo.\nAdd images to start.",
            image=self.empty_image,
            compound="top",
            bg=SOFT,
            fg=MUTED,
            font=(FONT, 12),
            wraplength=420,
            # Request no size of its own (pixels while an image shows): the preview
            # takes leftover space so caption controls stay visible at the minimum size.
            width=1,
            height=1,
        )
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<Configure>", lambda _: self._draw_preview())
        self.filename = ttk.Label(
            right,
            text="No image selected",
            style="Card.TLabel",
            wraplength=460,
            font=(HEADING, 11),
        )
        self.filename.pack(anchor="w", pady=(12, 2))
        self.detail = ttk.Label(
            right,
            text="Review and edit generated text before sharing.",
            style="CardMuted.TLabel",
            wraplength=460,
        )
        self.detail.pack(anchor="w", pady=(0, 8))
        ttk.Label(right, text="Caption text (editable)", style="Card.TLabel").pack(anchor="w")
        self.editor = tk.Text(
            right,
            height=4,
            wrap="word",
            bg=EDITOR_BG,
            fg=NIGHT,
            insertbackground=VIOLET,
            selectbackground=WASH,
            selectforeground=NIGHT,
            inactiveselectbackground=WASH,
            highlightthickness=2,
            highlightcolor=VIOLET,
            highlightbackground=LINE,
            relief="flat",
            padx=12,
            pady=10,
            font=(FONT, 12),
            undo=True,
            state="disabled",
        )
        self.editor.pack(fill="x")
        self.editor.bind("<FocusOut>", lambda _: self._save_edit())
        self.editor.bind("<KeyRelease>", lambda _: self._save_edit())
        self.editor.bind("<<Modified>>", self._editor_modified)
        caption_actions = ttk.Frame(right, style="Card.TFrame")
        caption_actions.pack(fill="x", pady=(10, 0))
        self.copy_button = ttk.Button(caption_actions, text="Copy caption", command=self._copy)
        self.copy_button.pack(side="left")
        self.restore_button = ttk.Button(
            caption_actions, text="Restore AI text", command=self._restore
        )
        self.restore_button.pack(side="left", padx=8)
        self.export_button = ttk.Button(
            caption_actions, text="Export results", command=self._export
        )
        self.export_button.pack(side="right")

        footer = ttk.Frame(self.root, padding=(24, 0, 24, 14))
        footer.pack(fill="x", side="bottom", before=body)
        self.progress = ttk.Progressbar(footer, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 7))
        self.help_button = ttk.Button(
            footer, text="Keyboard shortcuts (F1)", command=self._keyboard_help
        )
        self.help_button.pack(side="right", padx=(12, 0))
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel", wraplength=1060).pack(
            anchor="w"
        )
        ttk.Label(
            footer, textvariable=self.autosave_status, style="Muted.TLabel", wraplength=1060
        ).pack(anchor="w", pady=(3, 0))
        self._bind_keyboard()
        self._update_controls()

    def _apply_theme(self) -> None:
        """Lavender-and-violet theme matching the LunaCaption logo."""
        self.root.option_add("*Font", (FONT, 10))
        self.root.option_add("*TCombobox*Listbox.background", CARD)
        self.root.option_add("*TCombobox*Listbox.foreground", NIGHT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", WASH)
        self.root.option_add("*TCombobox*Listbox.selectForeground", NIGHT)
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            ".",
            font=(FONT, 10),
            background=MIST,
            foreground=NIGHT,
            bordercolor=LINE,
            lightcolor=MIST,
            darkcolor=MIST,
            troughcolor=WASH,
            focuscolor=VIOLET,
            selectbackground=WASH,
            selectforeground=NIGHT,
        )
        style.configure("TFrame", background=MIST)
        style.configure("Card.TFrame", background=CARD)
        style.configure(
            "Panel.TFrame", background=CARD, bordercolor=LINE, relief="solid", borderwidth=1
        )
        style.configure("TLabel", background=MIST, foreground=NIGHT)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Card.TLabel", background=CARD, foreground=NIGHT)
        style.configure("CardMuted.TLabel", background=CARD, foreground=MUTED)
        style.configure("Section.TLabel", background=CARD, foreground=PLUM, font=(HEADING, 9))

        style.configure(
            "TButton",
            padding=(14, 8),
            background=SOFT,
            foreground=NIGHT,
            bordercolor=LINE,
            lightcolor=SOFT,
            darkcolor=SOFT,
            focuscolor=VIOLET,
        )
        style.map(
            "TButton",
            background=[("disabled", MIST), ("pressed", LINE), ("active", WASH)],
            lightcolor=[("disabled", MIST), ("pressed", LINE), ("active", WASH)],
            darkcolor=[("disabled", MIST), ("pressed", LINE), ("active", WASH)],
            foreground=[("disabled", DISABLED_TEXT)],
            bordercolor=[("focus", VIOLET)],
        )
        style.configure(
            "Primary.TButton",
            font=(HEADING, 10),
            background=VIOLET,
            foreground="white",
            bordercolor=VIOLET,
            lightcolor=VIOLET,
            darkcolor=VIOLET,
            focuscolor="white",
        )
        style.map(
            "Primary.TButton",
            background=[("disabled", WASH), ("pressed", NIGHT), ("active", PLUM)],
            lightcolor=[("disabled", WASH), ("pressed", NIGHT), ("active", PLUM)],
            darkcolor=[("disabled", WASH), ("pressed", NIGHT), ("active", PLUM)],
            bordercolor=[("disabled", WASH), ("focus", NIGHT)],
            foreground=[("disabled", DISABLED_TEXT)],
        )

        for name, surface in (("TCheckbutton", MIST), ("Card.TCheckbutton", CARD)):
            style.configure(
                name,
                background=surface,
                foreground=NIGHT,
                indicatorbackground=CARD,
                indicatorforeground="white",
                focuscolor=VIOLET,
            )
            style.map(
                name,
                background=[("active", surface)],
                indicatorbackground=[("disabled", MIST), ("selected", VIOLET), ("pressed", WASH)],
                foreground=[("disabled", DISABLED_TEXT)],
            )
        style.configure(
            "TCombobox",
            padding=(8, 4),
            fieldbackground=CARD,
            background=SOFT,
            foreground=NIGHT,
            arrowcolor=PLUM,
            bordercolor=LINE,
            lightcolor=CARD,
            darkcolor=CARD,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("disabled", MIST), ("readonly", CARD)],
            background=[("active", WASH)],
            foreground=[("disabled", DISABLED_TEXT)],
            selectbackground=[("readonly", CARD)],
            selectforeground=[("readonly", NIGHT)],
            bordercolor=[("focus", VIOLET)],
            arrowcolor=[("disabled", DISABLED_TEXT)],
        )

        style.configure(
            "Treeview",
            rowheight=32,
            background=CARD,
            fieldbackground=CARD,
            foreground=NIGHT,
            bordercolor=LINE,
            lightcolor=CARD,
            darkcolor=CARD,
        )
        style.map("Treeview", background=[("selected", WASH)], foreground=[("selected", NIGHT)])
        style.configure(
            "Treeview.Heading",
            font=(HEADING, 9),
            background=SOFT,
            foreground=PLUM,
            bordercolor=LINE,
            lightcolor=SOFT,
            darkcolor=SOFT,
            padding=(10, 5),
        )
        style.map("Treeview.Heading", background=[("active", WASH)])
        style.configure(
            "Vertical.TScrollbar",
            background=SOFT,
            troughcolor=CARD,
            bordercolor=CARD,
            lightcolor=SOFT,
            darkcolor=SOFT,
            arrowcolor=PLUM,
            gripcount=0,
        )
        style.map("Vertical.TScrollbar", background=[("active", WASH)])
        style.configure(
            "Horizontal.TProgressbar",
            background=VIOLET,
            troughcolor=WASH,
            bordercolor=WASH,
            lightcolor=VIOLET,
            darkcolor=VIOLET,
            thickness=8,
        )

    def _bind_keyboard(self) -> None:
        self.keyboard_controls = (
            self.add_button,
            self.folder_button,
            self.recursive_check,
            self.clear_button,
            self.open_session_button,
            self.save_session_button,
            self.relink_button,
            self.tree,
            self.length_box,
            self.device_box,
            self.offline_check,
            self.generate_button,
            self.retry_button,
            self.cancel_button,
            self.editor,
            self.copy_button,
            self.restore_button,
            self.export_button,
            self.help_button,
        )
        shortcuts = {
            "<Control-i>": self.add_button,
            "<Control-Shift-I>": self.folder_button,
            "<Control-o>": self.open_session_button,
            "<Control-s>": self.save_session_button,
            "<Control-e>": self.export_button,
            "<Control-Return>": self.generate_button,
            "<Escape>": self.cancel_button,
            "<F1>": self.help_button,
        }
        # Widget bindings run before Tk's Text class bindings (Ctrl+I/O/E).
        # Use local bindings, never bind_all: dialogs retain their own keys.
        for widget in (self.root, *self.keyboard_controls):
            for key, button in shortcuts.items():
                widget.bind(key, lambda event, target=button: self._shortcut(event, target))
            widget.bind("<F6>", self._switch_pane)
            widget.bind("<Shift-F6>", self._switch_pane)
        self.tree.bind("<Return>", self._edit_selected)
        self.editor.bind("<Tab>", lambda event: self._leave_editor(False))
        self.editor.bind("<Shift-Tab>", lambda event: self._leave_editor(True))

    def _keyboard_available(self, event) -> bool:
        return (
            not self.closed
            and event.widget.winfo_toplevel() == self.root
            and not self.root.tk.call("grab", "current", self.root._w)
        )

    def _shortcut(self, event, button) -> str:
        if self._keyboard_available(event) and not button.instate(["disabled"]):
            button.invoke()
        return "break"

    def _keyboard_help(self) -> None:
        messagebox.showinfo(
            "Keyboard shortcuts",
            "Ctrl+I: add images\nCtrl+Shift+I: open folder\n"
            "Ctrl+O: open session\nCtrl+S: save session\n"
            "Ctrl+Enter: generate captions\nEsc: cancel running batch\n"
            "Ctrl+E: export results\nF6 / Shift+F6: queue or caption editor\n"
            "Enter in queue: edit selected caption\n"
            "Tab / Shift+Tab: next / previous control (also in the editor)\n"
            "Arrow keys: select an image or caption length\n"
            "Space: activate a focused button or checkbox\n"
            "F1: show this help\n\n"
            "Shortcuts respect disabled controls. Cancelling finishes the current "
            "model operation. Normal text selection, copy, paste, and undo stay available.",
            parent=self.root,
        )

    def _device_changed(self, *_args) -> None:
        # A machine preference, not saved caption/session content.
        self.compute_status.set(f"LOCAL AI / {self.device.get().upper()} requested")

    def _initial_focus(self) -> None:
        if not self.closed and self.root.focus_get() is None:
            if self.rows:
                self._focus_queue()
            else:
                self.add_button.focus_set()

    def _focus_queue(self) -> None:
        if self.rows:
            selected = self.tree.selection()
            key = selected[0] if selected else next(iter(self.rows))
            self.tree.selection_set(key)
            self.tree.focus(key)
            self.tree.see(key)
            self.tree.focus_set()
        else:
            self.add_button.focus_set()

    def _edit_selected(self, event) -> str:
        if self._keyboard_available(event) and str(self.editor["state"]) == "normal":
            self.editor.focus_set()
        return "break"

    def _switch_pane(self, event) -> str:
        if self._keyboard_available(event):
            if self.root.focus_get() != self.editor and str(self.editor["state"]) == "normal":
                self.editor.focus_set()
            else:
                self._focus_queue()
        return "break"

    def _leave_editor(self, backwards: bool) -> str:
        self._save_edit()
        target = self.editor.tk_focusPrev() if backwards else self.editor.tk_focusNext()
        target.focus_set()
        return "break"

    def add_paths(self, paths: list[Path]) -> None:
        try:
            discovered = collect_images(paths, recursive=self.recursive.get())
            new = [path for path in discovered if str(path) not in self.rows]
            if len(self.rows) + len(new) > MAX_BATCH:
                raise ImageInputError(f"Keep at most {MAX_BATCH} images in the workspace.")
            for path in new:
                key = str(path)
                self.rows[key] = CaptionResult(path=key)
                self.tree.insert("", "end", iid=key, values=(path.name, "Ready"))
            if new:
                self._mark_dirty()
            if not self.tree.selection() and self.rows:
                self.tree.selection_set(next(iter(self.rows)))
            self.status.set(f"Added {len(new)} image(s). Select Generate captions when ready.")
            self._update_controls()
            if new:
                self._focus_queue()
        except (ImageInputError, OSError) as exc:
            messagebox.showerror("Could not add images", str(exc), parent=self.root)

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self.root,
            title="Choose images",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff")],
        )
        if paths:
            self.add_paths([Path(path) for path in paths])

    def _add_folder(self) -> None:
        path = filedialog.askdirectory(parent=self.root, title="Choose an image folder")
        if path:
            self.add_paths([Path(path)])

    def _select(self, _event=None) -> None:
        self._save_edit()
        selected = self.tree.selection()
        self.current = selected[0] if selected else None
        if self.preview_source:
            self.preview_source.close()
            self.preview_source = None
        if not self.current:
            self._update_controls()
            return
        row = self.rows[self.current]
        self.filename.configure(text=Path(row.path).name)
        try:
            self.preview_source = load_image(Path(row.path))
            self.preview_source.thumbnail((1400, 1000), Image.Resampling.LANCZOS)
            self._draw_preview()
            if self.image_errors.pop(row.path, None) is not None:
                self._refresh_row(row)
        except ImageInputError as exc:
            self.preview_photo = None
            self.preview.configure(image="", text=str(exc))
            try:
                available = Path(row.path).is_file()
            except OSError:
                available = False
            if not available:
                self.image_errors[row.path] = (
                    "Image missing or unavailable. Use Relink image to locate it. "
                    "Saved captions are kept."
                )
                self._refresh_row(row)
        self._show_caption()
        self._update_controls()

    def _relink(self) -> None:
        if self.busy or self.current not in self.image_errors:
            return
        old_path = self.current
        path = filedialog.askopenfilename(
            parent=self.root,
            title=f"Locate {Path(old_path).name}",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff")],
        )
        if not path:
            return
        preview = None
        try:
            replacement = Path(path).expanduser().resolve()
            if replacement.suffix.lower() not in SUPPORTED_SUFFIXES or not replacement.is_file():
                raise ImageInputError("Choose a supported image file.")
            key = str(replacement)
            normalized = ntpath.normcase(ntpath.normpath(key))
            for existing in self.rows:
                if existing == old_path:
                    continue
                duplicate = ntpath.normcase(ntpath.normpath(existing)) == normalized
                if not duplicate:
                    try:
                        duplicate = replacement.samefile(existing)
                    except OSError:
                        pass
                if duplicate:
                    raise ImageInputError("That image is already in this workspace.")
            preview = load_image(replacement)
            preview.thumbnail((1400, 1000), Image.Resampling.LANCZOS)
        except (OSError, ValueError) as exc:
            if preview is not None:
                preview.close()
            messagebox.showerror("Could not relink image", str(exc), parent=self.root)
            return

        # Validate first; then replace the path in place without touching captions,
        # generation status, timing, or provenance. No model work starts here.
        self._save_edit()
        row = self.rows[old_path]
        if key != old_path:
            self.tree.insert("", self.tree.index(old_path), iid=key)
            self.current = None
            self.tree.delete(old_path)
            self.rows = {
                key if existing == old_path else existing: result
                for existing, result in self.rows.items()
            }
        row.path = key
        self.image_errors.pop(old_path, None)
        self.current = key
        self._refresh_row(row)
        self.tree.selection_set(key)
        self.tree.focus(key)
        self.tree.see(key)
        if self.preview_source is not None:
            self.preview_source.close()
        self.preview_source = preview
        self.filename.configure(text=replacement.name)
        self._draw_preview()
        self._show_caption()
        self._mark_dirty()
        self._update_controls()
        self.status.set(
            f"Relinked {replacement.name}. Captions kept; no generation started. "
            "Review the caption against this image."
        )

    def _fit_placeholder(self) -> None:
        """Show the logo in the empty preview only when it fits above the text."""
        roomy = self.preview.winfo_height() >= 145
        self.preview.configure(image=self.empty_image if roomy else self.blank_image)

    def _draw_preview(self) -> None:
        if self.preview_source is None:
            if self.preview_photo is None and self.preview.cget("image"):
                self._fit_placeholder()
            return
        image = self.preview_source.copy()
        image.thumbnail(
            (max(40, self.preview.winfo_width() - 16), max(40, self.preview.winfo_height() - 16)),
            Image.Resampling.LANCZOS,
        )
        self.preview_photo = ImageTk.PhotoImage(image, master=self.root)
        self.preview.configure(image=self.preview_photo, text="")

    def _show_caption(self) -> None:
        row = self.rows.get(self.current)
        self.editor.configure(state="normal")
        self.editor.delete("1.0", "end")
        if row:
            self.editor.insert("1.0", row.caption)
            self.detail.configure(
                text=self.image_errors.get(row.path) or row.error
                if row.path in self.image_errors or row.status == "error"
                else (
                    f"Generated in {row.elapsed_seconds:.1f}s · Editable draft"
                    if row.status == "done"
                    else "Ready to generate a caption."
                )
            )
        self.editor.edit_reset()
        self.editor.edit_modified(False)
        editable = bool(row and row.status == "done")
        self.editor.configure(state="normal" if editable else "disabled", takefocus=editable)

    def _editor_modified(self, _event=None) -> None:
        if self.editor.edit_modified():
            self.editor.edit_modified(False)
            self._save_edit()

    def _save_edit(self) -> None:
        row = self.rows.get(self.current)
        if row and row.status == "done":
            text = self.editor.get("1.0", "end-1c").strip()
            if row.caption != text:
                row.caption = text
                row.edited = text != row.generated_caption
                self._mark_dirty()
                self._refresh_row(row)

    def _copy(self) -> None:
        self._save_edit()
        row = self.rows.get(self.current)
        if row and row.caption:
            self.root.clipboard_clear()
            self.root.clipboard_append(row.caption)
            self.status.set("Caption copied.")

    def _restore(self) -> None:
        row = self.rows.get(self.current)
        if row and row.status == "done":
            row.caption = row.generated_caption
            row.edited = False
            self._mark_dirty()
            self._refresh_row(row)
            self._show_caption()

    def _start(self) -> None:
        if self.busy:
            return
        paths = [
            Path(row.path)
            for row in self.rows.values()
            if row.status == "pending" and row.path not in self.image_errors
        ]
        if not paths:
            return
        self._save_edit()
        options = CaptionOptions(length=self.length.get(), beams=self.beams)
        offline = self.offline.get()
        device = self.device.get()
        self.busy = True
        self.cancel_event.clear()
        self.batch_finished = 0
        self.batch_total = len(paths)
        self.batch_error = False
        self.progress.configure(value=0, maximum=len(paths))
        self._mark_dirty()
        self._autosave_now()
        self.status.set("Preparing captioning model...")
        self._update_controls()
        threading.Thread(
            target=self._worker,
            args=(paths, options, offline, device),
            daemon=True,
            name="caption-worker",
        ).start()

    def _worker(
        self, paths: list[Path], options: CaptionOptions, offline: bool, device: str = "cpu"
    ) -> None:
        def report_status(text):
            self.events.put(("status", text))
            actual = getattr(self.engine, "device", "cpu").upper()
            fallback = " FALLBACK" if getattr(self.engine, "fallback_reason", "") else ""
            self.events.put(("device", f"LOCAL AI / {actual}{fallback}"))

        try:
            if (
                self.engine is None
                or self.engine.offline != offline
                or getattr(self.engine, "requested_device", "cpu") != device
            ):
                # Release the old model before loading a different device configuration.
                self.engine = None
                self.engine = CaptionEngine(offline=offline, device=device)
            for result in run_batch(
                paths,
                self.engine,
                options,
                cancel=self.cancel_event,
                status=report_status,
            ):
                self.events.put(("result", result))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            self.events.put(("finished", None))

    def _poll(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "status":
                    self.status.set(payload)
                elif event == "device":
                    self.compute_status.set(payload)
                elif event == "result":
                    self.rows[payload.path] = payload
                    self.tree.item(
                        payload.path,
                        values=(
                            Path(payload.path).name,
                            "Done" if payload.status == "done" else "Error",
                        ),
                        tags=(payload.status,),
                    )
                    self.batch_finished += 1
                    self.progress.configure(value=self.batch_finished)
                    self._mark_dirty()
                    if self.current == payload.path:
                        self._show_caption()
                    self._update_controls()
                elif event == "error":
                    self.batch_error = True
                    self.status.set(payload)
                    messagebox.showerror("Captioning paused", payload, parent=self.root)
                elif event == "finished":
                    self.busy = False
                    if not self.batch_error:
                        errors = sum(row.status == "error" for row in self.rows.values())
                        verb = "Cancelled" if self.cancel_event.is_set() else "Finished"
                        fallback = getattr(self.engine, "fallback_reason", "")
                        self.status.set(
                            f"{verb}: {self.batch_finished} of {self.batch_total} "
                            f"processed · {errors} error(s). "
                            + (f"Ran on CPU: {fallback} " if fallback else "")
                            + "Save the session to keep your work."
                        )
                    self._update_controls()
        except queue.Empty:
            pass
        if not self.closed:
            self.root.after(100, self._poll)

    def _cancel(self) -> None:
        self.cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.status.set(
            "Cancelling after the current model operation. Completed captions are kept."
        )
        self._update_controls()

    def _retry(self) -> None:
        if self.busy:
            return
        self._save_edit()
        for row in self.rows.values():
            if row.status == "error" and row.path not in self.image_errors:
                self._mark_dirty()
                row.status = "pending"
                row.error = ""
                self.tree.item(row.path, values=(Path(row.path).name, "Ready"), tags=())
        self._show_caption()
        self._start()

    def _export(self) -> None:
        self._save_edit()
        results = [row for row in self.rows.values() if row.status in {"done", "error"}]
        if not results:
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export captions",
            initialfile="lunacaption-results.csv",
            defaultextension=".csv",
            filetypes=[("CSV spreadsheet", "*.csv"), ("JSON", "*.json")],
            confirmoverwrite=True,
        )
        if path:
            try:
                export_results(results, Path(path), overwrite=True)
                self.status.set(f"Exported {len(results)} results to {Path(path).name}.")
            except (OSError, ValueError) as exc:
                messagebox.showerror("Export failed", str(exc), parent=self.root)

    def _snapshot(self) -> Session:
        # Called only on the Tk thread; persistence finishes before UI state can change.
        return Session(
            results=list(self.rows.values()),
            options=CaptionOptions(length=self.length.get(), beams=self.beams),
            offline=self.offline.get(),
            recursive=self.recursive.get(),
        )

    def _initialize_recovery(self, directory: Path) -> None:
        try:
            self.recovery = RecoveryStore(directory)
            session = self.recovery.load()
            self.autosave_status.set("Automatic recovery ready.")
            if session is not None:
                recover = messagebox.askyesno(
                    "Recover unsaved workspace?",
                    "An unsaved workspace was found. Restore its queue, captions, and settings? "
                    "Generation will stay stopped. No discards this recovery copy.",
                    parent=self.root,
                )
                if recover:
                    self._apply_session(session)
                    self._mark_dirty()
                    self.status.set(
                        "Workspace recovered. Review it and use Save session to keep it."
                    )
                else:
                    self.recovery.discard()
        except (OSError, ValueError) as exc:
            # Preserve unreadable recovery files for manual inspection.
            self._release_recovery()
            self.autosave_status.set(f"Recovery unavailable: {exc} Use Save session.")

    def _mark_dirty(self) -> None:
        self.dirty = True
        if self.recovery is not None and not self.closed:
            self._cancel_autosave()
            self.autosave_after = self.root.after(AUTOSAVE_DELAY_MS, self._autosave_now)
            self.autosave_status.set("Recovery copy pending...")

    def _cancel_autosave(self) -> None:
        if self.autosave_after is not None:
            self.root.after_cancel(self.autosave_after)
            self.autosave_after = None

    def _autosave_now(self) -> None:
        self._cancel_autosave()
        if self.closed or self.recovery is None:
            return
        self._save_edit()
        self._cancel_autosave()
        if not self.dirty:
            return
        try:
            self.recovery.save(self._snapshot())
            self.autosave_status.set("Recovery copy saved locally. Use Save session to keep it.")
        except (OSError, ValueError) as exc:
            self.autosave_status.set(f"Recovery save failed: {exc} Use Save session.")
        # Autosave never clears dirty: explicit discard/save decisions still matter.

    def _discard_recovery(self) -> bool:
        self._cancel_autosave()
        if self.recovery is not None:
            try:
                self.recovery.discard()
            except OSError as exc:
                self.autosave_status.set(f"Could not remove recovery copy: {exc}")
                messagebox.showerror(
                    "Recovery cleanup failed",
                    "The previous recovery copy could not be removed. "
                    "Your workspace is kept open. Check storage permissions and try again.",
                    parent=self.root,
                )
                return False
            self.autosave_status.set("Automatic recovery ready.")
        return True

    def _release_recovery(self) -> None:
        self._cancel_autosave()
        if self.recovery is not None:
            self.recovery.close()
            self.recovery = None

    def _settings_changed(self, *_args) -> None:
        self._mark_dirty()

    def _refresh_row(self, row: CaptionResult) -> None:
        state = (
            "Missing"
            if row.path in self.image_errors
            else "Edited"
            if row.status == "done" and row.edited
            else {"pending": "Ready", "done": "Done", "error": "Error"}[row.status]
        )
        self.tree.item(
            row.path,
            values=(Path(row.path).name, state),
            tags=("error" if row.path in self.image_errors else row.status,),
        )

    def _save_session(self) -> bool:
        if self.busy:
            return False
        self._save_edit()
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save session",
            initialfile=self.session_path.name
            if self.session_path
            else "workspace.lunacaption.json",
            initialdir=str(self.session_path.parent) if self.session_path else None,
            defaultextension=".lunacaption.json",
            filetypes=SESSION_TYPES,
            confirmoverwrite=True,
        )
        if not path:
            return False
        try:
            if self.recovery and Path(path).resolve() == self.recovery.path.resolve():
                raise ValueError("Choose a location outside the automatic recovery file.")
            save_session(self._snapshot(), Path(path), overwrite=True)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not save session", str(exc), parent=self.root)
            return False
        self.session_path = Path(path)
        self.dirty = False
        self._discard_recovery()
        self.status.set(f"Session saved to {self.session_path.name}.")
        return True

    def _confirm_replace(self) -> bool:
        self._save_edit()
        if not self.dirty:
            return True
        choice = messagebox.askyesnocancel(
            "Save workspace changes?",
            "Save your queue, captions, and settings before continuing?\n"
            "Yes: save a session. No: discard changes. Cancel: keep working.",
            parent=self.root,
        )
        if choice is None:
            return False
        return self._save_session() if choice else True

    def _open_session(self) -> None:
        if self.busy:
            return
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Open session",
            filetypes=SESSION_TYPES,
        )
        if not path:
            return
        # Validate before offering to replace anything. Read again after a save:
        # the user may save the active workspace over the file being opened.
        try:
            session = load_session(Path(path))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not open session", str(exc), parent=self.root)
            return
        self._save_edit()
        had_changes = self.dirty
        if not self._confirm_replace():
            return
        try:
            if had_changes and not self.dirty:
                session = load_session(Path(path))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not open session", str(exc), parent=self.root)
            return
        if not self._discard_recovery():
            return
        self._apply_session(session, Path(path))
        self.status.set(
            f"Opened {self.session_path.name}: {len(self.rows)} image(s), "
            f"{len(self.image_errors)} missing or unavailable. "
            "Generation starts only when requested."
        )

    def _apply_session(self, session: Session, path: Path | None = None) -> None:
        missing = {}
        for row in session.results:
            try:
                available = Path(row.path).is_file()
            except OSError:
                available = False
            if not available:
                missing[row.path] = "Image missing or unavailable. Saved captions are kept."
        self._reset_workspace()
        self.rows = {row.path: row for row in session.results}
        self.image_errors = missing
        self.length.set(session.options.length)
        self.beams = session.options.beams
        self.offline.set(session.offline)
        self.recursive.set(session.recursive)
        for row in session.results:
            self.tree.insert("", "end", iid=row.path)
            self._refresh_row(row)
        self.session_path = path
        self.dirty = False
        if self.rows:
            self.tree.selection_set(next(iter(self.rows)))
            self._select()
        self._cancel_autosave()
        if self.recovery is not None:
            self.autosave_status.set("Automatic recovery ready.")
        self._update_controls()
        self._focus_queue()

    def _reset_workspace(self) -> None:
        self._cancel_autosave()
        # Clear the selection before replacing rows so queued selection events
        # cannot apply the old editor contents to a restored caption.
        self.current = None
        self.rows.clear()
        self.image_errors.clear()
        self.tree.delete(*self.tree.get_children())
        if self.preview_source:
            self.preview_source.close()
            self.preview_source = None
        self.preview_photo = None
        self.preview.configure(image=self.empty_image, text="Add images to start.")
        self._fit_placeholder()
        self.filename.configure(text="No image selected")
        self.detail.configure(text="Review and edit generated text before sharing.")
        self._show_caption()
        self.editor.edit_reset()
        self.progress.configure(value=0)
        self.session_path = None
        self.dirty = False

    def _clear(self) -> None:
        if self.busy or not self._confirm_replace():
            return
        if not self._discard_recovery():
            return
        self._reset_workspace()
        self.status.set("Workspace cleared. Your original images are unchanged.")
        self._update_controls()
        self.add_button.focus_set()

    def _update_controls(self) -> None:
        done = sum(row.status == "done" for row in self.rows.values())
        pending = any(
            row.status == "pending" and row.path not in self.image_errors
            for row in self.rows.values()
        )
        errors = any(
            row.status == "error" and row.path not in self.image_errors
            for row in self.rows.values()
        )
        self.summary.set(f"{len(self.rows)} images · {done} captioned")
        for widget in (
            self.add_button,
            self.folder_button,
            self.clear_button,
            self.open_session_button,
            self.save_session_button,
            self.offline_check,
            self.recursive_check,
        ):
            widget.configure(state="disabled" if self.busy else "normal")
        self.relink_button.configure(
            state="normal" if not self.busy and self.current in self.image_errors else "disabled"
        )
        self.length_box.configure(state="disabled" if self.busy else "readonly")
        self.device_box.configure(state="disabled" if self.busy else "readonly")
        self.generate_button.configure(state="normal" if pending and not self.busy else "disabled")
        self.retry_button.configure(state="normal" if errors and not self.busy else "disabled")
        self.cancel_button.configure(
            state="normal" if self.busy and not self.cancel_event.is_set() else "disabled"
        )
        self.export_button.configure(
            state="normal"
            if any(row.status in {"done", "error"} for row in self.rows.values())
            else "disabled"
        )
        selected = self.rows.get(self.current)
        caption_state = "normal" if selected and selected.status == "done" else "disabled"
        self.copy_button.configure(state=caption_state)
        self.restore_button.configure(state=caption_state)
        focused = self.root.focus_get()
        if focused in self.keyboard_controls and (
            str(focused["state"]) == "disabled"
            if focused == self.editor
            else focused.instate(["disabled"])
        ):
            if self.busy and not self.cancel_button.instate(["disabled"]):
                self.cancel_button.focus_set()
            else:
                self._focus_queue()

    def _close(self) -> None:
        self._save_edit()
        if self.busy:
            if not messagebox.askyesno(
                "Close LunaCaption?",
                "A batch is running. Close and discard unsaved work? "
                "Choose No to return, cancel the batch, and save first.",
                parent=self.root,
            ):
                return
        elif not self._confirm_replace():
            return
        if not self._discard_recovery():
            return
        self._release_recovery()
        self.cancel_event.set()
        self.closed = True
        if self.preview_source:
            self.preview_source.close()
        self.root.destroy()


def main(*, offline: bool = False, device: str = "cpu") -> None:
    root = tk.Tk()
    CaptionApp(root, offline=offline, device=device)
    root.mainloop()


if __name__ == "__main__":
    main()
