#!/usr/bin/env python3
"""
Photo/Video Organizer - Trieur rapide de médias
Permet de trier rapidement des photos et vidéos dans des dossiers personnalisés.
"""

import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass
import cv2
from pathlib import Path
from typing import List, Optional
import threading


# Extensions supportées
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.heic', '.heif'}
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.3gp'}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


class MediaOrganizer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Photo/Video Organizer")
        self.root.geometry("1200x800")
        self.root.attributes('-topmost', True)  # Toujours au premier plan

        # Variables
        self.media_files: List[Path] = []
        self.current_index = 0
        self.destination_folder: Optional[Path] = None
        self.subfolders: List[Path] = []
        self.folder_buttons: List[tk.Button] = []
        self.current_image: Optional[ImageTk.PhotoImage] = None
        self.video_capture: Optional[cv2.VideoCapture] = None
        self.is_playing_video = False

        self._setup_ui()
        self._bind_shortcuts()

    def _setup_ui(self):
        """Configure l'interface utilisateur."""
        # Frame principale
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Frame supérieure pour les contrôles
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 5))

        # Boutons de sélection
        ttk.Button(control_frame, text="📁 Choisir dossiers source",
                   command=self._select_source_folders).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="📂 Dossier destination",
                   command=self._select_destination).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="➕ Nouveau dossier",
                   command=self._create_subfolder).pack(side=tk.LEFT, padx=2)

        ttk.Separator(control_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # Navigation
        ttk.Button(control_frame, text="⬅ Précédent (←)",
                   command=self._previous_media).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="➡ Suivant (→)",
                   command=self._next_media).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="🗑 Supprimer (Del)",
                   command=self._delete_current).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="⏭ Passer (Espace)",
                   command=self._skip_media).pack(side=tk.LEFT, padx=2)

        # Label de progression
        self.progress_label = ttk.Label(control_frame, text="0/0")
        self.progress_label.pack(side=tk.RIGHT, padx=10)

        # Zone centrale avec prévisualisation et dossiers
        center_frame = ttk.Frame(main_frame)
        center_frame.pack(fill=tk.BOTH, expand=True)

        # Frame de prévisualisation (gauche)
        preview_frame = ttk.LabelFrame(center_frame, text="Prévisualisation", padding="5")
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Canvas pour l'image/vidéo
        self.canvas = tk.Canvas(preview_frame, bg='black')
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Label pour le nom du fichier
        self.filename_label = ttk.Label(preview_frame, text="Aucun fichier", font=('Arial', 10))
        self.filename_label.pack(pady=5)

        # Contrôles vidéo
        video_control_frame = ttk.Frame(preview_frame)
        video_control_frame.pack(fill=tk.X)
        self.play_button = ttk.Button(video_control_frame, text="▶ Play/Pause",
                                       command=self._toggle_video_play)
        self.play_button.pack(side=tk.LEFT, padx=2)
        self.video_slider = ttk.Scale(video_control_frame, from_=0, to=100, orient=tk.HORIZONTAL)
        self.video_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Frame des dossiers de destination (droite)
        self.folders_frame = ttk.LabelFrame(center_frame, text="Dossiers de destination (1-9 pour raccourcis)",
                                            padding="5", width=300)
        self.folders_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        self.folders_frame.pack_propagate(False)

        # Scrollable frame pour les boutons de dossiers
        self.folders_canvas = tk.Canvas(self.folders_frame, width=280)
        self.folders_scrollbar = ttk.Scrollbar(self.folders_frame, orient=tk.VERTICAL,
                                                command=self.folders_canvas.yview)
        self.folders_inner_frame = ttk.Frame(self.folders_canvas)

        self.folders_canvas.configure(yscrollcommand=self.folders_scrollbar.set)
        self.folders_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.folders_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.folders_canvas.create_window((0, 0), window=self.folders_inner_frame, anchor=tk.NW)

        self.folders_inner_frame.bind('<Configure>',
            lambda e: self.folders_canvas.configure(scrollregion=self.folders_canvas.bbox("all")))

        # Barre de statut
        self.status_bar = ttk.Label(main_frame, text="Prêt - Sélectionnez des dossiers source",
                                    relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(fill=tk.X, pady=(5, 0))

    def _bind_shortcuts(self):
        """Configure les raccourcis clavier."""
        self.root.bind('<Left>', lambda e: self._previous_media())
        self.root.bind('<Right>', lambda e: self._next_media())
        self.root.bind('<Delete>', lambda e: self._delete_current())
        self.root.bind('<space>', lambda e: self._skip_media())
        self.root.bind('<Escape>', lambda e: self.root.quit())

        # Raccourcis numériques 1-9 pour les dossiers
        for i in range(1, 10):
            self.root.bind(str(i), lambda e, idx=i-1: self._move_to_folder_by_index(idx))

    def _select_source_folders(self):
        """Permet de sélectionner les dossiers source."""
        folders = []
        while True:
            folder = filedialog.askdirectory(title="Sélectionner un dossier source (Annuler pour terminer)")
            if not folder:
                break
            folders.append(folder)
            if not messagebox.askyesno("Ajouter un autre dossier?",
                                       f"Dossier ajouté: {folder}\n\nVoulez-vous ajouter un autre dossier?"):
                break

        if folders:
            self._load_media_from_folders(folders)

    def _load_media_from_folders(self, folders: List[str]):
        """Charge tous les fichiers médias des dossiers sélectionnés."""
        self.media_files = []
        for folder in folders:
            folder_path = Path(folder)
            for file in folder_path.rglob('*'):
                if file.suffix.lower() in MEDIA_EXTENSIONS:
                    self.media_files.append(file)

        # Trier par date de modification (plus récent en premier)
        self.media_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        self.current_index = 0
        self._update_status(f"{len(self.media_files)} fichiers trouvés")
        self._display_current_media()

    def _select_destination(self):
        """Sélectionne le dossier parent de destination."""
        folder = filedialog.askdirectory(title="Sélectionner le dossier parent de destination")
        if folder:
            self.destination_folder = Path(folder)
            self._update_status(f"Destination: {self.destination_folder}")
            self._scan_existing_subfolders()

    def _scan_existing_subfolders(self):
        """Scanne les sous-dossiers existants dans la destination."""
        if not self.destination_folder:
            return

        self.subfolders = [d for d in self.destination_folder.iterdir() if d.is_dir()]
        self.subfolders.sort(key=lambda x: x.name.lower())
        self._refresh_folder_buttons()

    def _create_subfolder(self):
        """Crée un nouveau sous-dossier dans la destination."""
        if not self.destination_folder:
            messagebox.showwarning("Attention", "Veuillez d'abord sélectionner un dossier de destination")
            return

        # Dialogue pour le nom du dossier
        dialog = tk.Toplevel(self.root)
        dialog.title("Nouveau dossier")
        dialog.geometry("300x100")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.attributes('-topmost', True)

        ttk.Label(dialog, text="Nom du dossier:").pack(pady=5)
        entry = ttk.Entry(dialog, width=40)
        entry.pack(pady=5)
        entry.focus_set()

        def create():
            name = entry.get().strip()
            if name:
                new_folder = self.destination_folder / name
                try:
                    new_folder.mkdir(exist_ok=True)
                    if new_folder not in self.subfolders:
                        self.subfolders.append(new_folder)
                        self.subfolders.sort(key=lambda x: x.name.lower())
                        self._refresh_folder_buttons()
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("Erreur", f"Impossible de créer le dossier: {e}")

        entry.bind('<Return>', lambda e: create())
        ttk.Button(dialog, text="Créer", command=create).pack(pady=5)

    def _refresh_folder_buttons(self):
        """Actualise les boutons de dossiers."""
        # Supprimer les anciens boutons
        for widget in self.folders_inner_frame.winfo_children():
            widget.destroy()
        self.folder_buttons = []

        # Créer les nouveaux boutons
        for i, folder in enumerate(self.subfolders):
            shortcut = f"[{i+1}] " if i < 9 else "    "
            btn = ttk.Button(
                self.folders_inner_frame,
                text=f"{shortcut}{folder.name}",
                command=lambda f=folder: self._move_current_to_folder(f),
                width=35
            )
            btn.pack(pady=2, fill=tk.X)
            self.folder_buttons.append(btn)

    def _move_to_folder_by_index(self, index: int):
        """Déplace le fichier courant vers le dossier à l'index donné."""
        if index < len(self.subfolders):
            self._move_current_to_folder(self.subfolders[index])

    def _move_current_to_folder(self, destination: Path):
        """Déplace le fichier courant vers le dossier spécifié."""
        if not self.media_files or self.current_index >= len(self.media_files):
            return

        current_file = self.media_files[self.current_index]
        try:
            # Libérer les ressources vidéo si nécessaire
            self._release_video()

            # Déplacer le fichier
            new_path = destination / current_file.name

            # Gérer les conflits de noms
            if new_path.exists():
                base = new_path.stem
                suffix = new_path.suffix
                counter = 1
                while new_path.exists():
                    new_path = destination / f"{base}_{counter}{suffix}"
                    counter += 1

            shutil.move(str(current_file), str(new_path))
            self._update_status(f"Déplacé vers: {destination.name}")

            # Retirer de la liste et passer au suivant
            self.media_files.pop(self.current_index)
            if self.current_index >= len(self.media_files):
                self.current_index = max(0, len(self.media_files) - 1)
            self._display_current_media()

        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de déplacer le fichier: {e}")

    def _display_current_media(self):
        """Affiche le média courant."""
        self._release_video()
        self.canvas.delete("all")

        if not self.media_files:
            self.filename_label.config(text="Aucun fichier")
            self.progress_label.config(text="0/0")
            return

        if self.current_index >= len(self.media_files):
            self.current_index = len(self.media_files) - 1

        current_file = self.media_files[self.current_index]
        self.filename_label.config(text=current_file.name)
        self.progress_label.config(text=f"{self.current_index + 1}/{len(self.media_files)}")

        # Mettre à jour le canvas après affichage
        self.root.update_idletasks()
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width, canvas_height = 800, 600

        suffix = current_file.suffix.lower()

        if suffix in IMAGE_EXTENSIONS:
            self._display_image(current_file, canvas_width, canvas_height)
        elif suffix in VIDEO_EXTENSIONS:
            self._display_video(current_file, canvas_width, canvas_height)

    def _display_image(self, file_path: Path, canvas_width: int, canvas_height: int):
        """Affiche une image."""
        try:
            image = Image.open(file_path)

            # Gérer l'orientation EXIF
            try:
                from PIL import ExifTags
                for orientation in ExifTags.TAGS.keys():
                    if ExifTags.TAGS[orientation] == 'Orientation':
                        break
                exif = image._getexif()
                if exif:
                    orientation_value = exif.get(orientation)
                    if orientation_value == 3:
                        image = image.rotate(180, expand=True)
                    elif orientation_value == 6:
                        image = image.rotate(270, expand=True)
                    elif orientation_value == 8:
                        image = image.rotate(90, expand=True)
            except (AttributeError, KeyError, IndexError):
                pass

            # Redimensionner pour s'adapter au canvas
            ratio = min(canvas_width / image.width, canvas_height / image.height)
            new_size = (int(image.width * ratio), int(image.height * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)

            self.current_image = ImageTk.PhotoImage(image)
            self.canvas.create_image(canvas_width // 2, canvas_height // 2,
                                     image=self.current_image, anchor=tk.CENTER)
        except Exception as e:
            self.canvas.create_text(canvas_width // 2, canvas_height // 2,
                                   text=f"Erreur: {e}", fill="white")

    def _display_video(self, file_path: Path, canvas_width: int, canvas_height: int):
        """Affiche la première frame d'une vidéo."""
        try:
            self.video_capture = cv2.VideoCapture(str(file_path))
            self.video_path = file_path

            # Lire la première frame
            ret, frame = self.video_capture.read()
            if ret:
                self._display_video_frame(frame, canvas_width, canvas_height)

            # Configurer le slider
            total_frames = int(self.video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
            self.video_slider.config(to=total_frames)
            self.video_slider.set(0)

        except Exception as e:
            self.canvas.create_text(canvas_width // 2, canvas_height // 2,
                                   text=f"Erreur vidéo: {e}", fill="white")

    def _display_video_frame(self, frame, canvas_width: int, canvas_height: int):
        """Affiche une frame vidéo."""
        # Convertir BGR en RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame_rgb)

        # Redimensionner
        ratio = min(canvas_width / image.width, canvas_height / image.height)
        new_size = (int(image.width * ratio), int(image.height * ratio))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

        self.current_image = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(canvas_width // 2, canvas_height // 2,
                                image=self.current_image, anchor=tk.CENTER)

    def _toggle_video_play(self):
        """Bascule lecture/pause de la vidéo."""
        if not self.video_capture:
            return

        self.is_playing_video = not self.is_playing_video
        if self.is_playing_video:
            self._play_video_loop()

    def _play_video_loop(self):
        """Boucle de lecture vidéo."""
        if not self.is_playing_video or not self.video_capture:
            return

        ret, frame = self.video_capture.read()
        if ret:
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            self._display_video_frame(frame, canvas_width, canvas_height)

            # Mettre à jour le slider
            current_frame = int(self.video_capture.get(cv2.CAP_PROP_POS_FRAMES))
            self.video_slider.set(current_frame)

            # Continuer la lecture (environ 30 fps)
            self.root.after(33, self._play_video_loop)
        else:
            # Fin de la vidéo
            self.is_playing_video = False
            self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)

    def _release_video(self):
        """Libère les ressources vidéo."""
        self.is_playing_video = False
        if self.video_capture:
            self.video_capture.release()
            self.video_capture = None

    def _next_media(self):
        """Passe au média suivant."""
        if self.media_files and self.current_index < len(self.media_files) - 1:
            self.current_index += 1
            self._display_current_media()

    def _previous_media(self):
        """Revient au média précédent."""
        if self.media_files and self.current_index > 0:
            self.current_index -= 1
            self._display_current_media()

    def _skip_media(self):
        """Passe le média courant (va au suivant sans action)."""
        self._next_media()

    def _delete_current(self):
        """Supprime le fichier courant (met à la corbeille ou supprime)."""
        if not self.media_files or self.current_index >= len(self.media_files):
            return

        current_file = self.media_files[self.current_index]

        if messagebox.askyesno("Confirmer la suppression",
                              f"Voulez-vous vraiment supprimer:\n{current_file.name}?"):
            try:
                self._release_video()

                # Essayer d'utiliser send2trash si disponible
                try:
                    from send2trash import send2trash
                    send2trash(str(current_file))
                except ImportError:
                    current_file.unlink()

                self._update_status(f"Supprimé: {current_file.name}")
                self.media_files.pop(self.current_index)
                if self.current_index >= len(self.media_files):
                    self.current_index = max(0, len(self.media_files) - 1)
                self._display_current_media()

            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible de supprimer: {e}")

    def _update_status(self, message: str):
        """Met à jour la barre de statut."""
        self.status_bar.config(text=message)

    def run(self):
        """Lance l'application."""
        self.root.mainloop()


def main():
    """Point d'entrée principal."""
    # Vérifier les dépendances
    try:
        import PIL
        import cv2
    except ImportError as e:
        print("Dépendances manquantes. Installez-les avec:")
        print("pip install pillow pillow-heif opencv-python")
        return

    app = MediaOrganizer()
    app.run()


if __name__ == "__main__":
    main()
