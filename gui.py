import customtkinter as ctk
from tkinter import filedialog, messagebox
import tkinter as tk
from PIL import Image
import os
from playbook_editor import PB_PSU, Formation, load_csv_data

# --- App Settings ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

MAX_PLAYS = 30
IMAGE_BASE_PATH = "images"


class PlaybookEditor(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("NFL 2K5 Playbook Editor")
        self.geometry("1200x900")
        self.minsize(1000, 800)

        self.psu = None
        self.playbook_formations = {}
        self.current_formation = None
        self._default_package = None

        self.available_images = []
        self.available_image_idx = 0
        self.formation_images = []
        self.formation_image_idx = 0

        # Load CSV data once at startup
        self.formations_csv, self.package_names, self.play_names = load_csv_data()

        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Top bar
        self.top_bar = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.top_bar.pack(fill="x", side="top")

        self.load_btn = ctk.CTkButton(self.top_bar, text="Load PSU File", command=self._load_psu, width=140)
        self.load_btn.pack(side="left", padx=12, pady=8)

        self.save_btn = ctk.CTkButton(
            self.top_bar, text="Save to PSU", command=self._save_psu,
            width=140, state="disabled", fg_color="#2a6e2a", hover_color="#3a8e3a"
        )
        self.save_btn.pack(side="left", padx=4, pady=8)

        self.file_label = ctk.CTkLabel(self.top_bar, text="No file loaded", text_color="gray")
        self.file_label.pack(side="left", padx=16, pady=8)

        # Formation selection row
        self.formation_row = ctk.CTkFrame(self, height=44, corner_radius=0, fg_color="transparent")
        self.formation_row.pack(fill="x", padx=16, pady=(10, 0))

        ctk.CTkLabel(self.formation_row, text="Formation:").pack(side="left", padx=(0, 8))

        self.formation_var = ctk.StringVar(value="")
        self.formation_dropdown = ctk.CTkOptionMenu(
            self.formation_row, variable=self.formation_var,
            values=["Load a PSU file first"],
            command=self._on_formation_selected,
            width=220, state="disabled"
        )
        self.formation_dropdown.pack(side="left")

        ctk.CTkLabel(self.formation_row, text="Package:").pack(side="left", padx=(24, 8))

        self.package_var = ctk.StringVar(value="")
        self.package_dropdown = ctk.CTkOptionMenu(
            self.formation_row, variable=self.package_var,
            values=[""],
            command=self._on_package_selected,
            width=160, state="disabled"
        )
        self.package_dropdown.pack(side="left")

        self.default_label = ctk.CTkLabel(self.formation_row, text="(Default)", text_color="#aaaaaa")
        self.default_label.pack(side="left", padx=8)

        self.updated_label = ctk.CTkLabel(self.formation_row, text="Updated Package", text_color="#ccaa33")
        # Not packed until package is changed

        # Play count indicator
        self.play_count_label = ctk.CTkLabel(self.formation_row, text="", font=ctk.CTkFont(weight="bold"))
        self.play_count_label.pack(side="right", padx=8)

        # Main panels frame
        self.panels_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.panels_frame.pack(fill="both", expand=True, padx=16, pady=10)

        self.panels_frame.columnconfigure(0, weight=3)
        self.panels_frame.columnconfigure(1, weight=0)
        self.panels_frame.columnconfigure(2, weight=2)
        self.panels_frame.rowconfigure(0, weight=1)

        # --- Left panel — available plays ---
        left_frame = ctk.CTkFrame(self.panels_frame)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left_frame.rowconfigure(1, weight=1)
        left_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(left_frame, text="Available Plays", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=2, pady=(8, 4), padx=8, sticky="w"
        )

        self.available_listbox = tk.Listbox(
            left_frame, selectmode=tk.EXTENDED, bg="#2b2b2b", fg="white",
            selectbackground="#1f538d", activestyle="none",
            relief="flat", borderwidth=0, highlightthickness=0,
            font=("Courier New", 11)
        )
        self.available_listbox.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 4))
        self.available_listbox.bind("<<ListboxSelect>>", self._on_available_selected)

        avail_scroll = ctk.CTkScrollbar(left_frame, command=self.available_listbox.yview)
        avail_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 4), pady=(0, 4))
        self.available_listbox.configure(yscrollcommand=avail_scroll.set)

        # Image display below left panel
        self.available_img_label = ctk.CTkLabel(left_frame, text="")
        self.available_img_label.grid(row=2, column=0, columnspan=2, pady=(4, 2))

        self.available_img_formation_label = ctk.CTkLabel(left_frame, text="", text_color="#aaaaaa")
        self.available_img_formation_label.grid(row=3, column=0, columnspan=2)

        avail_nav_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        avail_nav_frame.grid(row=4, column=0, columnspan=2, pady=(2, 8))

        self.avail_prev_btn = ctk.CTkButton(
            avail_nav_frame, text="◄", width=32,
            command=lambda: self._cycle_image("available", -1), state="disabled"
        )
        self.avail_prev_btn.pack(side="left", padx=4)

        self.avail_img_counter = ctk.CTkLabel(avail_nav_frame, text="")
        self.avail_img_counter.pack(side="left", padx=8)

        self.avail_next_btn = ctk.CTkButton(
            avail_nav_frame, text="►", width=32,
            command=lambda: self._cycle_image("available", 1), state="disabled"
        )
        self.avail_next_btn.pack(side="left", padx=4)

        # --- Middle buttons ---
        mid_frame = ctk.CTkFrame(self.panels_frame, fg_color="transparent", width=60)
        mid_frame.grid(row=0, column=1, sticky="ns", padx=4)
        mid_frame.rowconfigure((0, 1, 2, 3, 4), weight=1)

        self.add_btn = ctk.CTkButton(
            mid_frame, text="→", width=50, command=self._add_plays,
            state="disabled"
        )
        self.add_btn.grid(row=1, column=0, pady=4)

        self.remove_btn = ctk.CTkButton(
            mid_frame, text="←", width=50, command=self._remove_plays,
            state="disabled", fg_color="#6e2a2a", hover_color="#8e3a3a"
        )
        self.remove_btn.grid(row=2, column=0, pady=4)

        # --- Right panel — formation plays ---
        right_frame = ctk.CTkFrame(self.panels_frame)
        right_frame.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        right_frame.rowconfigure(1, weight=1)
        right_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(right_frame, text="Plays in Formation", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=3, pady=(8, 4), padx=8, sticky="w"
        )

        self.formation_listbox = tk.Listbox(
            right_frame, selectmode=tk.EXTENDED, bg="#2b2b2b", fg="white",
            selectbackground="#1f538d", activestyle="none",
            relief="flat", borderwidth=0, highlightthickness=0,
            font=("Courier New", 11)
        )
        self.formation_listbox.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 4))
        self.formation_listbox.bind("<<ListboxSelect>>", self._on_formation_play_selected)

        form_scroll = ctk.CTkScrollbar(right_frame, command=self.formation_listbox.yview)
        form_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 2), pady=(0, 4))
        self.formation_listbox.configure(yscrollcommand=form_scroll.set)

        # Up/down buttons for reordering
        ud_frame = ctk.CTkFrame(right_frame, fg_color="transparent", width=36)
        ud_frame.grid(row=1, column=2, sticky="ns", padx=(0, 4), pady=(0, 4))
        ud_frame.rowconfigure((0, 1, 2), weight=1)

        self.up_btn = ctk.CTkButton(ud_frame, text="▲", width=32, command=self._move_up, state="disabled")
        self.up_btn.grid(row=0, column=0, pady=(0, 4), sticky="s")

        self.down_btn = ctk.CTkButton(ud_frame, text="▼", width=32, command=self._move_down, state="disabled")
        self.down_btn.grid(row=1, column=0, pady=(4, 0), sticky="n")

        # Image display below right panel
        self.formation_img_label = ctk.CTkLabel(right_frame, text="")
        self.formation_img_label.grid(row=2, column=0, columnspan=3, pady=(4, 2))

        self.formation_img_formation_label = ctk.CTkLabel(right_frame, text="", text_color="#aaaaaa")
        self.formation_img_formation_label.grid(row=3, column=0, columnspan=3)

        form_nav_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        form_nav_frame.grid(row=4, column=0, columnspan=3, pady=(2, 8))

        self.form_prev_btn = ctk.CTkButton(
            form_nav_frame, text="◄", width=32,
            command=lambda: self._cycle_image("formation", -1), state="disabled"
        )
        self.form_prev_btn.pack(side="left", padx=4)

        self.form_img_counter = ctk.CTkLabel(form_nav_frame, text="")
        self.form_img_counter.pack(side="left", padx=8)

        self.form_next_btn = ctk.CTkButton(
            form_nav_frame, text="►", width=32,
            command=lambda: self._cycle_image("formation", 1), state="disabled"
        )
        self.form_next_btn.pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # File Operations
    # ------------------------------------------------------------------

    def _load_psu(self):
        path = filedialog.askopenfilename(
            title="Select PSU File",
            filetypes=[("PSU Files", "*.psu"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            self.psu = PB_PSU(path)
            # Reset formation objects from CSV
            self.formations_csv, self.package_names, self.play_names = load_csv_data()
            self.psu.load_playbook(self.formations_csv, self.package_names, self.play_names)
            self.playbook_formations = self.psu.playbook_formations

            # Populate dropdown with offensive formations only
            offensive = [
                name for name, f in self.playbook_formations.items()
                if f.side.lower() in ("offense", "offensive")
            ]
            if not offensive:
                messagebox.showwarning("No Offensive Formations", "No offensive formations found in this playbook.")
                return

            self.formation_dropdown.configure(values=offensive, state="normal")
            self.formation_var.set(offensive[0])
            self._on_formation_selected(offensive[0])

            self.file_label.configure(text=path.split("/")[-1], text_color="white")
            self.save_btn.configure(state="normal")

        except Exception as e:
            messagebox.showerror("Error Loading PSU", str(e))

    def _save_psu(self):
        if not self.psu:
            return

        # Write all formations to bytes and handle package changes
        for formation in self.playbook_formations.values():
            self.psu.write_formation_to_bytes(formation)
            if getattr(formation, '_package_changed', False):
                package_idx = self.psu.package_name_to_index.get(formation.package)
                if package_idx is not None:
                    self.psu.change_package(formation, package_idx)

        try:
            self.psu.save_psu()
            messagebox.showinfo("Saved", "Playbook saved successfully.")
        except Exception as e:
            messagebox.showerror("Error Saving PSU", str(e))

    # ------------------------------------------------------------------
    # Formation Selection
    # ------------------------------------------------------------------

    def _on_formation_selected(self, formation_name):
        self.current_formation = self.playbook_formations.get(formation_name)
        if not self.current_formation:
            return

        self._refresh_package_dropdown()

        # Enable buttons
        self.add_btn.configure(state="normal")
        self.remove_btn.configure(state="normal")
        self.up_btn.configure(state="normal")
        self.down_btn.configure(state="normal")

        self._refresh_panels()

    def _refresh_package_dropdown(self):
        if not self.current_formation:
            return

        # Get all offensive packages that exist in the PSU, sorted
        psu_packages = list(dict.fromkeys(
            f.package for f in self.playbook_formations.values()
            if f.side.lower() in ("offense", "offensive") and f.package
        ))
        for name in ["Jokers", "5 Wide"]:
            if name not in psu_packages:
                psu_packages.append(name)
        psu_packages.sort()

        self.package_dropdown.configure(values=psu_packages, state="normal")
        self.package_var.set(self.current_formation.package)

        # Store the original PSU default for this formation
        self._default_package = (
            self.current_formation.package
            if not getattr(self.current_formation, '_package_changed', False)
            else self.current_formation._original_package
        )

        # Reset labels based on whether package was previously changed
        if getattr(self.current_formation, '_package_changed', False):
            self.default_label.pack_forget()
            self.updated_label.pack(side="left", padx=8)
        else:
            self.updated_label.pack_forget()
            self.default_label.pack(side="left", padx=8)

    def _on_package_selected(self, package_name):
        if not self.current_formation:
            return

        if package_name == self._default_package:
            self.updated_label.pack_forget()
            self.default_label.pack(side="left", padx=8)
            self.current_formation.package = self._default_package
            self.current_formation._package_changed = False
        else:
            self.default_label.pack_forget()
            self.updated_label.pack(side="left", padx=8)
            if not getattr(self.current_formation, '_package_changed', False):
                self.current_formation._original_package = self.current_formation.package
            self.current_formation.package = package_name
            self.current_formation._package_changed = True

    # ------------------------------------------------------------------
    # Panel Refresh
    # ------------------------------------------------------------------

    def _refresh_panels(self):
        if not self.current_formation:
            return
        self._refresh_formation_panel()
        self._refresh_available_panel()
        self._update_play_count()

    def _refresh_formation_panel(self):
        self.formation_listbox.delete(0, tk.END)
        for play_bytes in self.current_formation.play_bytes:

            play_index = play_bytes[0] + (256 if play_bytes[1] == 0x01 else 0)
            play_name = self.psu.index_to_play_name.get(play_index, f"Unknown({play_index})")
            self.formation_listbox.insert(tk.END, play_name)

    def _refresh_available_panel(self):
        self.available_listbox.delete(0, tk.END)
        self.available_listbox.delete(0, tk.END)
        entries = self._get_available_entries()
        for pb, play_name in entries:
            self.available_listbox.insert(tk.END, play_name)

    def _update_play_count(self):
        if not self.current_formation:
            return
        count = len(self.current_formation.play_bytes)
        pages = count // 3 + (1 if count % 3 != 0 else 0)
        text = f"{count}/{MAX_PLAYS} plays  ({pages} page{'s' if pages != 1 else ''})"

        if count >= MAX_PLAYS:
            color = "#cc3333"
        elif count % 3 == 0:
            color = "#33cc33"
        else:
            color = "#ff6600"

        self.play_count_label.configure(text=text, text_color=color)

        if count >= MAX_PLAYS:
            self.add_btn.configure(state="disabled")
        else:
            self.add_btn.configure(state="normal")

    # ------------------------------------------------------------------
    # Play Manipulation
    # ------------------------------------------------------------------

    def _add_plays(self):
        if not self.current_formation:
            return
        selected = self.available_listbox.curselection()
        if not selected:
            return

        # Save scroll position
        top = self.available_listbox.yview()[0]

        count = len(self.current_formation.play_bytes)
        slots_remaining = MAX_PLAYS - count

        available_entries = self._get_available_entries()

        to_add = []
        for idx in selected:
            if idx < len(available_entries):
                to_add.append(available_entries[idx])

        to_add = to_add[:slots_remaining]

        for pb, play_name in to_add:
            self.current_formation.play_bytes.append(pb)
            self.current_formation.plays.append(play_name)

        self._refresh_panels()

        # Restore scroll position
        self.available_listbox.yview_moveto(top)

    def _remove_plays(self):
        if not self.current_formation:
            return
        selected = self.formation_listbox.curselection()
        if not selected:
            return
        for idx in reversed(selected):
            del self.current_formation.play_bytes[idx]
            del self.current_formation.plays[idx]
        self._refresh_panels()

    def _move_up(self):
        if not self.current_formation:
            return
        selected = list(self.formation_listbox.curselection())
        if not selected or selected[0] == 0:
            return
        pb = self.current_formation.play_bytes
        pn = self.current_formation.plays
        for idx in selected:
            if idx == 0:
                continue
            pb[idx - 1], pb[idx] = pb[idx], pb[idx - 1]
            pn[idx - 1], pn[idx] = pn[idx], pn[idx - 1]
        self._refresh_formation_panel()
        for idx in selected:
            if idx > 0:
                self.formation_listbox.selection_set(idx - 1)
        self._update_play_count()

    def _move_down(self):
        if not self.current_formation:
            return
        selected = list(self.formation_listbox.curselection())
        if not selected or selected[-1] >= len(self.current_formation.play_bytes) - 1:
            return
        pb = self.current_formation.play_bytes
        pn = self.current_formation.plays
        for idx in reversed(selected):
            if idx >= len(pb) - 1:
                continue
            pb[idx], pb[idx + 1] = pb[idx + 1], pb[idx]
            pn[idx], pn[idx + 1] = pn[idx + 1], pn[idx]
        self._refresh_formation_panel()
        for idx in selected:
            if idx < len(pb) - 1:
                self.formation_listbox.selection_set(idx + 1)
        self._update_play_count()

    # ------------------------------------------------------------------
    # Image Display
    # ------------------------------------------------------------------

    def _get_play_images(self, play_name):
        """Returns list of (image_path, formation_name) for all images
        of a play across all offensive formations in the PSU."""
        images = []
        play_filename = play_name.replace(" ", "_").replace("/", "")
        if not os.path.isdir(IMAGE_BASE_PATH):
            return images
        for formation_folder in os.listdir(IMAGE_BASE_PATH):
            folder_path = os.path.join(IMAGE_BASE_PATH, formation_folder)
            if not os.path.isdir(folder_path):
                continue
            try:
                folder_files = os.listdir(folder_path)
            except Exception:
                continue
            matching = sorted([
                f for f in folder_files
                if f.lower().startswith(play_filename.lower()) and f.lower().endswith(".jpeg")
            ])
            for f in matching:
                formation_name = formation_folder.replace("_", " ")
                images.append((os.path.join(folder_path, f), formation_name))
        return images

    def _show_image(self, panel, images, idx):
        """Display image at idx for the given panel ('available' or 'formation')."""
        if panel == "available":
            img_label = self.available_img_label
            formation_label = self.available_img_formation_label
            prev_btn = self.avail_prev_btn
            next_btn = self.avail_next_btn
            counter_label = self.avail_img_counter
        else:
            img_label = self.formation_img_label
            formation_label = self.formation_img_formation_label
            prev_btn = self.form_prev_btn
            next_btn = self.form_next_btn
            counter_label = self.form_img_counter

        if not images:
            img_label.configure(image=None, text="No image available")
            formation_label.configure(text="")
            counter_label.configure(text="")
            prev_btn.configure(state="disabled")
            next_btn.configure(state="disabled")
            return

        img_path, formation_name = images[idx]
        try:
            pil_img = Image.open(img_path)
            pil_img.thumbnail((270, 182), Image.LANCZOS)
            ctk_img = ctk.CTkImage(
                light_image=pil_img,
                dark_image=pil_img,
                size=(pil_img.width, pil_img.height)
            )
            img_label.configure(image=ctk_img, text="")
            img_label.image = ctk_img  # keep reference
        except Exception as e:
            print(e)
            #img_label.configure(image=None, text="Error loading image")
            img_label.configure(image=None, text=f"Error: {e}")

        formation_label.configure(text=formation_name)
        counter_label.configure(text=f"{idx + 1}/{len(images)}")
        prev_btn.configure(state="disabled" if len(images) <= 1 else "normal")
        next_btn.configure(state="disabled" if len(images) <= 1 else "normal")

    def _cycle_image(self, panel, direction):
        if panel == "available":
            if not self.available_images:
                return
            self.available_image_idx = (self.available_image_idx + direction) % len(self.available_images)
            self._show_image("available", self.available_images, self.available_image_idx)
        else:
            if not self.formation_images:
                return
            self.formation_image_idx = (self.formation_image_idx + direction) % len(self.formation_images)
            self._show_image("formation", self.formation_images, self.formation_image_idx)

    def _on_available_selected(self, event):
        selected = self.available_listbox.curselection()
        if not selected:
            return
        available_entries = self._get_available_entries()
        idx = selected[0]
        if idx >= len(available_entries):
            return
        _, play_name = available_entries[idx]
        self.available_images = self._get_play_images(play_name)
        self.available_image_idx = 0
        self._show_image("available", self.available_images, self.available_image_idx)

    def _on_formation_play_selected(self, event):
        selected = self.formation_listbox.curselection()
        if not selected:
            return
        idx = selected[0]
        if idx >= len(self.current_formation.play_bytes):
            return
        pb = self.current_formation.play_bytes[idx]
        play_index = pb[0] + (256 if pb[1] == 0x01 else 0)
        play_name = self.psu.index_to_play_name.get(play_index, f"Unknown({play_index})")
        self.formation_images = self._get_play_images(play_name)
        self.formation_image_idx = 0
        self._show_image("formation", self.formation_images, self.formation_image_idx)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_available_entries(self):
        """Returns sorted list of (play_bytes, play_name) for all offensive
        plays in the playbook not in the current formation."""
        current_play_bytes = set(self.current_formation.play_bytes)
        entries = []
        for pb in self.psu.all_playbook_plays:
            if pb in current_play_bytes:
                continue
            play_index = pb[0] + (256 if pb[1] == 0x01 else 0)
            play_name = self.psu.index_to_play_name.get(play_index, f"Unknown({play_index})")
            entries.append((pb, play_name))
        entries.sort(key=lambda x: (x[1], x[0][0]))
        return entries


if __name__ == "__main__":
    app = PlaybookEditor()
    app.mainloop()