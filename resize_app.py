import os
import sys
import threading
import time
import io
import shutil
import json
import subprocess
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
from PIL import ImageDraw
import yt_dlp
from ftp_client import FTPClientFrame

# Cấu hình giao diện CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

APP_WINDOW_BG = "#162338"
SCREEN_BG = "#1B2A42"
HEADER_BG = "#243754"
BODY_BG = "#20324D"
CARD_BG = "#273B59"
BORDER_COLOR = "#405A80"
MUTED_TEXT = "#B7C9E4"
TITLE_ACCENT = "#5AAEFF"
HERO_TEXT = "#F4F8FF"
CANVAS_BG = "#314865"
ROW_BG = "#2A405E"
DIVIDER_COLOR = "#4A638A"
BACK_BTN_BG = "#314766"
BACK_BTN_HOVER = "#3C5678"


def resource_path(*parts):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base.joinpath(*parts))


class ImageResizerApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Phần mềm Xử lý Ảnh & Công cụ PDF")
        self.geometry("1000x780")
        self.minsize(900, 700)
        self.configure(fg_color=APP_WINDOW_BG)
        self.apply_window_icon()

        # --- Trạng thái Xử lý Ảnh ---
        self.cancel_requested = False
        self.processing_thread = None
        self.input_folder = ctk.StringVar(value="")
        self.output_folder = ctk.StringVar(value="")
        self.resize_mode = ctk.StringVar(value="dimensions")
        self.maintain_aspect = ctk.BooleanVar(value=True)
        self.open_output_on_finish = ctk.BooleanVar(value=True)
        self.output_format = ctk.StringVar(value="Giữ nguyên định dạng")

        # --- Trạng thái Công cụ PDF ---
        self.pdf_document = None          # fitz.Document object
        self.pdf_path = None              # Path to current PDF
        self.pdf_current_page = 0         # Index of current focused page
        self.pdf_total_pages = 0
        self.pdf_scale = 1.0              # Scale factor for rendering
        self.pdf_page_image = None        # Backward-compatible current page image ref
        self.pdf_page_images = []         # PIL Images of every PDF page
        self.pdf_tk_images = []           # Tkinter PhotoImages for all rendered pages
        self.pdf_page_layouts = []        # Canvas layout metadata for each visible page
        self.crop_rects = []              # List of (page_index, fitz.Rect, pil_image_of_crop)
        self.canvas_sel_start = None      # (x, y) of mouse press
        self.canvas_sel_rect = None       # Canvas rectangle ID
        self.pdf_to_print = ctk.StringVar(value="")
        self.print_after_merge = ctk.BooleanVar(value=False)
        self.pdf_split_path = ctk.StringVar(value="")
        self.pdf_split_ranges = ctk.StringVar(value="")
        self.pdf_split_output_dir = ctk.StringVar(value=str(Path.home() / "Documents"))
        self.pdf_merge_files = []
        self.active_screen = "home"
        self.screens = {}
        self.ffmpeg_path = shutil.which("ffmpeg")
        self.ffmpeg_available = self._is_ffmpeg_usable(self.ffmpeg_path)

        # --- Trạng thái tiện ích YouTube ---
        self.youtube_url = ctk.StringVar(value="")
        self.youtube_output_dir = ctk.StringVar(value=str(Path.home() / "Downloads"))
        self.youtube_mode = ctk.StringVar(value="video")
        self.youtube_quality = ctk.StringVar(value="Chưa có chất lượng")
        self.youtube_title = ctk.StringVar(value="Chưa phân tích liên kết nào")
        self.youtube_video_formats = []
        self.youtube_audio_formats = []
        self.youtube_format_map = {"video": {}, "audio": {}}
        self.youtube_last_info = None

        self.setup_gui()
        self.toggle_resize_mode()
        self.toggle_format_options()

    def apply_window_icon(self):
        try:
            icon_ico = resource_path("assets", "tool_app_icon.ico")
            if Path(icon_ico).exists():
                self.iconbitmap(icon_ico)
        except Exception:
            pass

        try:
            icon_png = resource_path("assets", "tool_app_icon.png")
            if Path(icon_png).exists():
                self._app_icon = tk.PhotoImage(file=icon_png)
                self.iconphoto(True, self._app_icon)
        except Exception:
            pass

    def _is_ffmpeg_usable(self, ffmpeg_path):
        if not ffmpeg_path:
            return False

        ffmpeg_file = Path(ffmpeg_path)
        if not ffmpeg_file.exists():
            return False
        try:
            result = subprocess.run(
                [str(ffmpeg_file), "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                encoding="utf-8",
                errors="ignore",
            )
            return result.returncode == 0 and "ffmpeg version" in (result.stdout or "").lower()
        except Exception:
            return False

    def _build_sanitized_env(self):
        env = os.environ.copy()
        if not self.ffmpeg_available and self.ffmpeg_path:
            broken_dir = str(Path(self.ffmpeg_path).parent).lower()
            path_items = env.get("PATH", "").split(os.pathsep)
            env["PATH"] = os.pathsep.join(
                item for item in path_items
                if item and item.lower() != broken_dir
            )
        return env

    # =========================================================
    # SETUP GUI
    # =========================================================

    def setup_gui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=0)

        # TIÊU ĐỀ
        self.title_label = ctk.CTkLabel(
            self,
            text="✨ Bộ Công cụ Tiện ích (Ảnh & PDF) ✨",
            font=ctk.CTkFont(family="Inter", size=22, weight="bold"),
            text_color=TITLE_ACCENT,
        )
        self.title_label.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")

        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, padx=20, pady=(5, 5), sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

        self.setup_home_screen()
        self.setup_image_tab()
        self.setup_pdf_tab()
        self.setup_pdf_merge_split_tab()
        self.setup_ftp_tab()
        self.setup_youtube_tab()
        self.show_screen("home")

        # THANH TIẾN TRÌNH DÙNG CHUNG
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(row=2, column=0, padx=20, pady=(3, 0), sticky="ew")
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.lbl_progress = ctk.CTkLabel(self.progress_frame, text="Sẵn sàng.", anchor="w")
        self.lbl_progress.grid(row=0, column=0, padx=5, pady=1, sticky="w")

        self.lbl_progress_percent = ctk.CTkLabel(self.progress_frame, text="0%", anchor="e")
        self.lbl_progress_percent.grid(row=0, column=1, padx=5, pady=1, sticky="e")

        self.btn_cancel = ctk.CTkButton(
            self.progress_frame, text="Hủy bỏ", fg_color="#EF4444",
            hover_color="#DC2626", command=self.cancel_processing,
            state="disabled", width=80, height=24
        )
        self.btn_cancel.grid(row=0, column=2, padx=5, pady=1)

        self.progressbar = ctk.CTkProgressBar(self.progress_frame)
        self.progressbar.set(0)
        self.progressbar.grid(row=1, column=0, columnspan=3, padx=5, pady=(2, 5), sticky="ew")

        # KHUNG NHẬT KÝ DÙNG CHUNG
        self.log_textbox = ctk.CTkTextbox(self, height=100, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_textbox.grid(row=3, column=0, padx=20, pady=(0, 12), sticky="ew")
        self.log_textbox.configure(state="disabled")

    def register_screen(self, key, frame):
        self.screens[key] = frame

    def show_screen(self, screen_key):
        target = self.screens.get(screen_key)
        if target is None:
            return

        for frame in self.screens.values():
            frame.grid_remove()

        target.grid(row=0, column=0, sticky="nsew")
        self.active_screen = screen_key

        titles = {
            "home": "✨ Bộ Công cụ Tiện ích (Ảnh & PDF) ✨",
            "image": "🖼️ Công cụ Xử lý Ảnh",
            "pdf": "📄 Công cụ PDF",
            "pdf_merge_split": "Tách/Gộp PDF",
            "ftp": "🌐 FTP Client",
            "youtube": "🎬 Tải Video YouTube",
        }
        self.title_label.configure(text=titles.get(screen_key, "✨ Bộ Công cụ Tiện ích (Ảnh & PDF) ✨"))

    def create_tool_screen(self, key, title, description, accent_color):
        screen = ctk.CTkFrame(self.content_frame, fg_color=SCREEN_BG, corner_radius=18)
        screen.grid_columnconfigure(0, weight=1)
        screen.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(screen, fg_color=HEADER_BG, corner_radius=16)
        header.grid(row=0, column=0, padx=14, pady=(14, 8), sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        back_btn = ctk.CTkButton(
            header,
            text="← Trang chủ",
            width=120,
            fg_color=BACK_BTN_BG,
            hover_color=BACK_BTN_HOVER,
            command=lambda: self.show_screen("home")
        )
        back_btn.grid(row=0, column=0, padx=14, pady=14, sticky="w")

        title_wrap = ctk.CTkFrame(header, fg_color="transparent")
        title_wrap.grid(row=0, column=1, padx=(2, 14), pady=10, sticky="ew")
        title_wrap.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            title_wrap,
            text=title,
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=accent_color
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_wrap,
            text=description,
            text_color=MUTED_TEXT,
            font=ctk.CTkFont(size=12)
        ).grid(row=1, column=0, pady=(2, 0), sticky="w")

        body = ctk.CTkFrame(screen, fg_color=BODY_BG, corner_radius=16)
        body.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.register_screen(key, screen)
        return body

    def setup_home_screen(self):
        home = ctk.CTkFrame(self.content_frame, fg_color=SCREEN_BG, corner_radius=18)
        home.grid_columnconfigure(0, weight=1)
        home.grid_rowconfigure(1, weight=1)

        hero = ctk.CTkFrame(home, fg_color=HEADER_BG, corner_radius=18)
        hero.grid(row=0, column=0, padx=14, pady=(14, 10), sticky="ew")
        hero.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hero,
            text="Tool đa năng cho ảnh, PDF và kết nối tệp",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=HERO_TEXT
        ).grid(row=0, column=0, padx=22, pady=(18, 4), sticky="w")
        ctk.CTkLabel(
            hero,
            text="Chọn một nhóm chức năng để bắt đầu. Kiểu giao diện này giúp thêm tool mới mà không cần nới rộng tab.",
            font=ctk.CTkFont(size=13),
            text_color=MUTED_TEXT
        ).grid(row=1, column=0, padx=22, pady=(0, 18), sticky="w")

        grid = ctk.CTkFrame(home, fg_color="transparent")
        grid.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="nsew")
        for col in range(3):
            grid.grid_columnconfigure(col, weight=1)
        for row in range(2):
            grid.grid_rowconfigure(row, weight=1)

        cards = [
            ("image", "🖼️", "Xử lý Ảnh", "Resize hàng loạt, đổi định dạng, giữ tỷ lệ", "#3B82F6"),
            ("pdf", "📄", "Công cụ PDF", "Mở toàn bộ PDF, cắt nhiều vùng, gộp để in", "#10B981"),
            ("pdf_merge_split", "PDF", "Tách/Gộp PDF", "Tách trang theo khoảng và gộp nhiều PDF", "#A78BFA"),
            ("ftp", "🌐", "FTP Client", "Kết nối, duyệt và thao tác tệp từ server", "#F59E0B"),
            ("youtube", "🎬", "Tải YouTube", "Phân tích link, chọn video hoặc âm thanh, rồi tải đúng chất lượng", "#EF4444"),
        ]

        for index, (screen_key, icon, title, desc, color) in enumerate(cards):
            row = index // 3
            col = index % 3
            self.create_home_card(grid, row, col, screen_key, icon, title, desc, color)

        self.register_screen("home", home)

    def create_home_card(self, parent, row, col, screen_key, icon, title, desc, accent_color):
        card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=18, border_width=1, border_color=BORDER_COLOR)
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            card,
            text=icon,
            font=ctk.CTkFont(size=42),
            text_color=accent_color
        ).grid(row=0, column=0, padx=18, pady=(22, 10), sticky="w")
        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=HERO_TEXT
        ).grid(row=1, column=0, padx=18, sticky="w")
        ctk.CTkLabel(
            card,
            text=desc,
            font=ctk.CTkFont(size=12),
            text_color=MUTED_TEXT,
            justify="left",
            wraplength=240
        ).grid(row=2, column=0, padx=18, pady=(6, 14), sticky="w")
        ctk.CTkButton(
            card,
            text="Mở chức năng",
            fg_color=accent_color,
            hover_color=accent_color,
            text_color="#020617",
            font=ctk.CTkFont(weight="bold"),
            command=lambda: self.show_screen(screen_key),
            height=38
        ).grid(row=4, column=0, padx=18, pady=(0, 18), sticky="ew")

    # =========================================================
    # TAB XỬ LÝ ẢNH
    # =========================================================

    def setup_image_tab(self):
        tab = self.create_tool_screen(
            "image",
            "Xử lý Ảnh",
            "Resize hàng loạt theo pixel hoặc phần trăm, xuất đúng định dạng bạn cần.",
            "#60A5FA"
        )
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Chọn thư mục
        self.folder_frame = ctk.CTkFrame(tab)
        self.folder_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.folder_frame.grid_columnconfigure(1, weight=1)

        for row_i, (lbl_text, var, cmd, placeholder) in enumerate([
            ("Thư mục đầu vào:", self.input_folder, self.browse_input, "Chọn thư mục ảnh gốc..."),
            ("Thư mục đầu ra:", self.output_folder, self.browse_output, "Chọn thư mục lưu ảnh resize..."),
        ]):
            pad_y = (15, 5) if row_i == 0 else (5, 15)
            ctk.CTkLabel(self.folder_frame, text=lbl_text, anchor="w", width=130).grid(row=row_i, column=0, padx=15, pady=pad_y, sticky="w")
            ctk.CTkEntry(self.folder_frame, textvariable=var, placeholder_text=placeholder).grid(row=row_i, column=1, padx=10, pady=pad_y, sticky="ew")
            ctk.CTkButton(self.folder_frame, text="Chọn...", width=90, command=cmd).grid(row=row_i, column=2, padx=15, pady=pad_y)

        # Cấu hình kích thước & định dạng
        self.config_frame = ctk.CTkFrame(tab)
        self.config_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.config_frame.grid_columnconfigure(0, weight=1)
        self.config_frame.grid_columnconfigure(1, weight=1)
        self.config_frame.grid_rowconfigure(0, weight=1)

        # Trái: chế độ resize
        rf = ctk.CTkFrame(self.config_frame)
        rf.grid(row=0, column=0, padx=(15, 7), pady=15, sticky="nsew")
        rf.grid_columnconfigure(1, weight=1)
        self.resize_frame = rf

        ctk.CTkLabel(rf, text="Cấu hình Kích thước", font=ctk.CTkFont(size=14, weight="bold"), text_color="#60A5FA").grid(row=0, column=0, columnspan=2, padx=15, pady=(10, 5), sticky="w")
        self.rad_dim = ctk.CTkRadioButton(rf, text="Theo kích thước (Pixel)", variable=self.resize_mode, value="dimensions", command=self.toggle_resize_mode)
        self.rad_dim.grid(row=1, column=0, columnspan=2, padx=15, pady=5, sticky="w")
        ctk.CTkLabel(rf, text="Rộng (px):").grid(row=2, column=0, padx=(30, 5), pady=2, sticky="e")
        self.entry_width = ctk.CTkEntry(rf, width=80)
        self.entry_width.insert(0, "1920")
        self.entry_width.grid(row=2, column=1, padx=(5, 15), pady=2, sticky="w")
        ctk.CTkLabel(rf, text="Cao (px):").grid(row=3, column=0, padx=(30, 5), pady=2, sticky="e")
        self.entry_height = ctk.CTkEntry(rf, width=80)
        self.entry_height.insert(0, "1080")
        self.entry_height.grid(row=3, column=1, padx=(5, 15), pady=2, sticky="w")
        self.chk_aspect = ctk.CTkCheckBox(rf, text="Giữ nguyên tỷ lệ ảnh", variable=self.maintain_aspect)
        self.chk_aspect.grid(row=4, column=0, columnspan=2, padx=(30, 15), pady=5, sticky="w")
        self.rad_pct = ctk.CTkRadioButton(rf, text="Theo tỷ lệ phần trăm (%)", variable=self.resize_mode, value="percentage", command=self.toggle_resize_mode)
        self.rad_pct.grid(row=5, column=0, columnspan=2, padx=15, pady=(10, 5), sticky="w")
        pf = ctk.CTkFrame(rf, fg_color="transparent")
        pf.grid(row=6, column=0, columnspan=2, padx=(30, 15), pady=(0, 10), sticky="ew")
        pf.grid_columnconfigure(0, weight=1)
        self.slider_pct = ctk.CTkSlider(pf, from_=10, to=200, number_of_steps=190, command=self.update_pct_label)
        self.slider_pct.set(50)
        self.slider_pct.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.lbl_pct_val = ctk.CTkLabel(pf, text="50%", width=45)
        self.lbl_pct_val.grid(row=0, column=1, sticky="e")

        # Phải: định dạng & tùy chọn
        ff = ctk.CTkFrame(self.config_frame)
        ff.grid(row=0, column=1, padx=(7, 15), pady=15, sticky="nsew")
        ff.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(ff, text="Định dạng & Tùy chọn", font=ctk.CTkFont(size=14, weight="bold"), text_color="#60A5FA").grid(row=0, column=0, columnspan=2, padx=15, pady=(10, 5), sticky="w")
        ctk.CTkLabel(ff, text="Định dạng xuất:").grid(row=1, column=0, padx=15, pady=5, sticky="w")
        self.dropdown_format = ctk.CTkOptionMenu(ff, values=["Giữ nguyên định dạng", "JPEG", "PNG", "WEBP"], variable=self.output_format, command=self.toggle_format_options)
        self.dropdown_format.grid(row=1, column=1, padx=15, pady=5, sticky="ew")
        ctk.CTkLabel(ff, text="Chất lượng:").grid(row=2, column=0, padx=15, pady=5, sticky="w")
        qf = ctk.CTkFrame(ff, fg_color="transparent")
        qf.grid(row=2, column=1, padx=15, pady=5, sticky="ew")
        qf.grid_columnconfigure(0, weight=1)
        self.slider_quality = ctk.CTkSlider(qf, from_=10, to=100, number_of_steps=90, command=self.update_quality_label)
        self.slider_quality.set(85)
        self.slider_quality.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.lbl_quality_val = ctk.CTkLabel(qf, text="85%", width=35)
        self.lbl_quality_val.grid(row=0, column=1, sticky="e")
        self.chk_open_out = ctk.CTkCheckBox(ff, text="Mở thư mục đầu ra khi hoàn thành", variable=self.open_output_on_finish)
        self.chk_open_out.grid(row=4, column=0, columnspan=2, padx=15, pady=(15, 10), sticky="w")

        # Nút bắt đầu
        self.btn_start = ctk.CTkButton(tab, text="▶  Bắt đầu thay đổi kích thước", fg_color="#3B82F6", hover_color="#2563EB", font=ctk.CTkFont(weight="bold"), command=self.start_processing, height=36)
        self.btn_start.grid(row=2, column=0, padx=10, pady=(8, 12), sticky="ew")

    # =========================================================
    # TAB CÔNG CỤ PDF (INTERACTIVE CROPPER)
    # =========================================================

    def setup_pdf_tab(self):
        tab = self.create_tool_screen(
            "pdf",
            "Công cụ PDF",
            "Đọc toàn bộ trang, cắt nhiều vùng trên nhiều trang và gộp lại thành một file.",
            "#34D399"
        )
        tab.grid_columnconfigure(0, weight=3)  # Viewer bên trái
        tab.grid_columnconfigure(1, weight=1)  # Panel phải (queue)
        tab.grid_rowconfigure(0, weight=1)

        # --- PHẦN VIEWER TRÁI ---
        viewer_frame = ctk.CTkFrame(tab)
        viewer_frame.grid(row=0, column=0, padx=(8, 4), pady=8, sticky="nsew")
        viewer_frame.grid_columnconfigure(0, weight=1)
        viewer_frame.grid_rowconfigure(1, weight=1)

        # Thanh công cụ trên viewer
        toolbar = ctk.CTkFrame(viewer_frame, fg_color="transparent")
        toolbar.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")
        toolbar.grid_columnconfigure(2, weight=1)

        self.btn_open_pdf = ctk.CTkButton(toolbar, text="📂 Mở tệp PDF...", width=140, command=self.open_pdf_file)
        self.btn_open_pdf.grid(row=0, column=0, padx=(0, 6), pady=2)

        self.btn_prev_page = ctk.CTkButton(toolbar, text="◀ Trang trước", width=110, state="disabled", command=self.prev_page)
        self.btn_prev_page.grid(row=0, column=1, padx=3, pady=2)

        self.lbl_page_info = ctk.CTkLabel(toolbar, text="Chưa mở tệp", anchor="center")
        self.lbl_page_info.grid(row=0, column=2, padx=6, pady=2, sticky="ew")

        self.btn_next_page = ctk.CTkButton(toolbar, text="Trang sau ▶", width=110, state="disabled", command=self.next_page)
        self.btn_next_page.grid(row=0, column=3, padx=3, pady=2)

        self.lbl_hint = ctk.CTkLabel(toolbar, text="🖱 Kéo chuột để chọn vùng cắt trên bất kỳ trang nào", text_color=MUTED_TEXT, font=ctk.CTkFont(size=11))
        self.lbl_hint.grid(row=0, column=4, padx=(10, 0), pady=2)

        # Canvas hiển thị trang PDF
        canvas_container = ctk.CTkFrame(viewer_frame)
        canvas_container.grid(row=1, column=0, padx=8, pady=(4, 8), sticky="nsew")
        canvas_container.grid_columnconfigure(0, weight=1)
        canvas_container.grid_rowconfigure(0, weight=1)

        self.pdf_canvas = tk.Canvas(canvas_container, bg=CANVAS_BG, cursor="crosshair", highlightthickness=0)
        self.pdf_canvas.grid(row=0, column=0, sticky="nsew")

        # Scrollbars cho canvas
        vsb = tk.Scrollbar(canvas_container, orient="vertical", command=self.pdf_canvas.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = tk.Scrollbar(canvas_container, orient="horizontal", command=self.pdf_canvas.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        self.pdf_canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Sự kiện chuột để vẽ hình chữ nhật
        self.pdf_canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.pdf_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.pdf_canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.pdf_canvas.bind("<Configure>", self.on_canvas_resize)

        # Nút cắt
        self.btn_crop = ctk.CTkButton(
            viewer_frame, text="✂️  Cắt vùng đã chọn & Thêm vào danh sách",
            fg_color="#8B5CF6", hover_color="#7C3AED",
            font=ctk.CTkFont(weight="bold"),
            command=self.do_crop, state="disabled", height=34
        )
        self.btn_crop.grid(row=2, column=0, padx=8, pady=(4, 8), sticky="ew")

        # --- PHẦN PANEL PHẢI (QUEUE) ---
        right_panel = ctk.CTkFrame(tab)
        right_panel.grid(row=0, column=1, padx=(4, 8), pady=8, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(right_panel, text="Danh sách vùng cắt", font=ctk.CTkFont(size=14, weight="bold"), text_color="#60A5FA").grid(row=0, column=0, padx=12, pady=(10, 5), sticky="w")

        # Danh sách cuộn
        self.crop_list_frame = ctk.CTkScrollableFrame(right_panel, label_text="Thứ tự gộp (trên → dưới):")
        self.crop_list_frame.grid(row=1, column=0, padx=12, pady=5, sticky="nsew")
        self.crop_list_frame.grid_columnconfigure(0, weight=1)

        # Nút xóa tất cả
        self.btn_clear_crops = ctk.CTkButton(
            right_panel, text="🧹 Xóa tất cả",
            fg_color="#4B5563", hover_color="#374151",
            command=self.clear_all_crops, height=30
        )
        self.btn_clear_crops.grid(row=2, column=0, padx=12, pady=(5, 2), sticky="ew")

        # Hộp kiểm in sau khi gộp
        self.chk_print_after = ctk.CTkCheckBox(right_panel, text="In sau khi gộp xong", variable=self.print_after_merge)
        self.chk_print_after.grid(row=3, column=0, padx=12, pady=5, sticky="w")

        # Nút gộp thành 1 trang
        self.btn_merge_to_one = ctk.CTkButton(
            right_panel, text="📄 Gộp thành 1 trang PDF",
            fg_color="#10B981", hover_color="#059669",
            font=ctk.CTkFont(weight="bold"),
            command=self.merge_to_one_page, height=36
        )
        self.btn_merge_to_one.grid(row=4, column=0, padx=12, pady=(5, 4), sticky="ew")

        # Nút in tệp PDF độc lập
        sep = ctk.CTkFrame(right_panel, height=1, fg_color=DIVIDER_COLOR)
        sep.grid(row=5, column=0, padx=12, pady=8, sticky="ew")

        ctk.CTkLabel(right_panel, text="In tệp PDF độc lập", font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED_TEXT).grid(row=6, column=0, padx=12, pady=(2, 4), sticky="w")
        self.entry_print_file = ctk.CTkEntry(right_panel, textvariable=self.pdf_to_print, placeholder_text="Chọn tệp PDF cần in...", state="readonly")
        self.entry_print_file.grid(row=7, column=0, padx=12, pady=3, sticky="ew")
        self.btn_browse_print = ctk.CTkButton(right_panel, text="Chọn tệp PDF...", command=self.browse_print_pdf, height=30)
        self.btn_browse_print.grid(row=8, column=0, padx=12, pady=3, sticky="ew")
        self.btn_print_now = ctk.CTkButton(
            right_panel, text="🖨️ Tiến hành in PDF",
            fg_color="#3B82F6", hover_color="#2563EB",
            font=ctk.CTkFont(weight="bold"),
            command=self.execute_print_pdf, height=34
        )
        self.btn_print_now.grid(row=9, column=0, padx=12, pady=(3, 12), sticky="ew")

    # =========================================================
    # TAB TÁCH/GỘP PDF
    # =========================================================

    def setup_pdf_merge_split_tab(self):
        tab = self.create_tool_screen(
            "pdf_merge_split",
            "Tách/Gộp PDF",
            "Tách file PDF theo khoảng trang và gộp nhiều file PDF theo đúng thứ tự.",
            "#C4B5FD"
        )
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        split_frame = ctk.CTkFrame(tab)
        split_frame.grid(row=0, column=0, padx=(8, 4), pady=8, sticky="nsew")
        split_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(split_frame, text="Tách file PDF", font=ctk.CTkFont(size=16, weight="bold"), text_color="#C4B5FD").grid(row=0, column=0, columnspan=3, padx=14, pady=(14, 8), sticky="w")
        ctk.CTkLabel(split_frame, text="File nguồn:", anchor="w", width=105).grid(row=1, column=0, padx=(14, 6), pady=6, sticky="w")
        ctk.CTkEntry(split_frame, textvariable=self.pdf_split_path, placeholder_text="Chọn file PDF cần tách...", state="readonly").grid(row=1, column=1, padx=6, pady=6, sticky="ew")
        ctk.CTkButton(split_frame, text="Chọn...", width=90, command=self.browse_pdf_split_file).grid(row=1, column=2, padx=(6, 14), pady=6)

        ctk.CTkLabel(split_frame, text="Khoảng trang:", anchor="w", width=105).grid(row=2, column=0, padx=(14, 6), pady=6, sticky="w")
        ctk.CTkEntry(split_frame, textvariable=self.pdf_split_ranges, placeholder_text="Ví dụ: 1-3,5,8-10").grid(row=2, column=1, columnspan=2, padx=(6, 14), pady=6, sticky="ew")

        ctk.CTkLabel(split_frame, text="Thư mục lưu:", anchor="w", width=105).grid(row=3, column=0, padx=(14, 6), pady=6, sticky="w")
        ctk.CTkEntry(split_frame, textvariable=self.pdf_split_output_dir, placeholder_text="Chọn thư mục xuất file...", state="readonly").grid(row=3, column=1, padx=6, pady=6, sticky="ew")
        ctk.CTkButton(split_frame, text="Chọn...", width=90, command=self.browse_pdf_split_output).grid(row=3, column=2, padx=(6, 14), pady=6)

        ctk.CTkLabel(
            split_frame,
            text="Mỗi khoảng trang sẽ được lưu thành một file PDF riêng. Để trống khoảng trang nếu muốn tách từng trang.",
            text_color=MUTED_TEXT,
            wraplength=360,
            justify="left"
        ).grid(row=4, column=0, columnspan=3, padx=14, pady=(4, 10), sticky="w")

        self.btn_split_pdf = ctk.CTkButton(
            split_frame,
            text="Tách PDF",
            fg_color="#8B5CF6",
            hover_color="#7C3AED",
            font=ctk.CTkFont(weight="bold"),
            command=self.split_pdf_file,
            height=38
        )
        self.btn_split_pdf.grid(row=5, column=0, columnspan=3, padx=14, pady=(6, 14), sticky="ew")

        merge_frame = ctk.CTkFrame(tab)
        merge_frame.grid(row=0, column=1, padx=(4, 8), pady=8, sticky="nsew")
        merge_frame.grid_columnconfigure(0, weight=1)
        merge_frame.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(merge_frame, text="Gộp nhiều file PDF", font=ctk.CTkFont(size=16, weight="bold"), text_color="#C4B5FD").grid(row=0, column=0, padx=14, pady=(14, 8), sticky="w")

        btn_row = ctk.CTkFrame(merge_frame, fg_color="transparent")
        btn_row.grid(row=1, column=0, padx=14, pady=(0, 6), sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(btn_row, text="Thêm PDF...", command=self.add_pdf_merge_files, height=30).grid(row=0, column=0, padx=(0, 4), sticky="ew")
        ctk.CTkButton(btn_row, text="Xóa tất cả", fg_color="#4B5563", hover_color="#374151", command=self.clear_pdf_merge_files, height=30).grid(row=0, column=1, padx=(4, 0), sticky="ew")

        self.pdf_merge_list_frame = ctk.CTkScrollableFrame(merge_frame, label_text="Thứ tự gộp (trên → dưới):")
        self.pdf_merge_list_frame.grid(row=2, column=0, padx=14, pady=6, sticky="nsew")
        self.pdf_merge_list_frame.grid_columnconfigure(0, weight=1)

        self.btn_merge_pdf_files = ctk.CTkButton(
            merge_frame,
            text="Gộp PDF",
            fg_color="#10B981",
            hover_color="#059669",
            font=ctk.CTkFont(weight="bold"),
            command=self.merge_pdf_files,
            height=38
        )
        self.btn_merge_pdf_files.grid(row=3, column=0, padx=14, pady=(6, 14), sticky="ew")
        self.refresh_pdf_merge_list_ui()

    # =========================================================
    # TAB FTP CLIENT
    # =========================================================

    def setup_ftp_tab(self):
        tab = self.create_tool_screen(
            "ftp",
            "FTP Client",
            "Kết nối và làm việc với máy chủ FTP trong cùng một giao diện công cụ.",
            "#FBBF24"
        )
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        ftp_frame = FTPClientFrame(tab)
        ftp_frame.grid(row=0, column=0, sticky="nsew")

    # =========================================================
    # TAB TẢI YOUTUBE
    # =========================================================

    def setup_youtube_tab(self):
        tab = self.create_tool_screen(
            "youtube",
            "Tải Video YouTube",
            "Nhập liên kết, phân tích stream video hoặc âm thanh, rồi chọn đúng chất lượng để tải về máy.",
            "#F87171"
        )
        tab.grid_columnconfigure(0, weight=3)
        tab.grid_columnconfigure(1, weight=2)
        tab.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(tab, fg_color=SCREEN_BG, corner_radius=16)
        left.grid(row=0, column=0, padx=(12, 6), pady=12, sticky="nsew")
        left.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(left, text="Liên kết YouTube", font=ctk.CTkFont(size=14, weight="bold"), text_color="#FCA5A5").grid(row=0, column=0, columnspan=3, padx=16, pady=(16, 6), sticky="w")
        self.entry_youtube_url = ctk.CTkEntry(left, textvariable=self.youtube_url, placeholder_text="Dán link video YouTube vào đây...")
        self.entry_youtube_url.grid(row=1, column=0, columnspan=2, padx=(16, 8), pady=6, sticky="ew")
        self.btn_analyze_youtube = ctk.CTkButton(left, text="Phân tích", width=120, fg_color="#EF4444", hover_color="#DC2626", command=self.start_youtube_analysis)
        self.btn_analyze_youtube.grid(row=1, column=2, padx=(0, 16), pady=6, sticky="e")

        ctk.CTkLabel(left, text="Thư mục lưu", font=ctk.CTkFont(size=13, weight="bold"), text_color="#FCA5A5").grid(row=2, column=0, columnspan=3, padx=16, pady=(12, 4), sticky="w")
        self.entry_youtube_output = ctk.CTkEntry(left, textvariable=self.youtube_output_dir, placeholder_text="Chọn thư mục lưu video/audio...")
        self.entry_youtube_output.grid(row=3, column=0, columnspan=2, padx=(16, 8), pady=6, sticky="ew")
        self.btn_browse_youtube_output = ctk.CTkButton(left, text="Chọn thư mục", width=120, fg_color="#1D4ED8", hover_color="#1E40AF", command=self.browse_youtube_output)
        self.btn_browse_youtube_output.grid(row=3, column=2, padx=(0, 16), pady=6, sticky="e")

        self.youtube_info_box = ctk.CTkFrame(left, fg_color=HEADER_BG, corner_radius=14)
        self.youtube_info_box.grid(row=4, column=0, columnspan=3, padx=16, pady=(12, 10), sticky="ew")
        self.youtube_info_box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.youtube_info_box, text="Thông tin phân tích", font=ctk.CTkFont(size=13, weight="bold"), text_color=HERO_TEXT).grid(row=0, column=0, padx=14, pady=(12, 4), sticky="w")
        self.lbl_youtube_title = ctk.CTkLabel(self.youtube_info_box, textvariable=self.youtube_title, justify="left", wraplength=520, text_color=HERO_TEXT)
        self.lbl_youtube_title.grid(row=1, column=0, padx=14, pady=(0, 6), sticky="w")
        if self.ffmpeg_path and not self.ffmpeg_available:
            ffmpeg_note = f"FFmpeg: phát hiện bản lỗi tại {self.ffmpeg_path}, app sẽ tự bỏ qua để tránh popup lỗi DLL"
        elif self.ffmpeg_available:
            ffmpeg_note = "FFmpeg: sẵn sàng ghép video chất lượng cao"
        else:
            ffmpeg_note = "FFmpeg: chưa tìm thấy, một số video chất lượng cao có thể không ghép được âm thanh"
        self.lbl_youtube_ffmpeg = ctk.CTkLabel(self.youtube_info_box, text=ffmpeg_note, text_color=MUTED_TEXT, justify="left", wraplength=520)
        self.lbl_youtube_ffmpeg.grid(row=2, column=0, padx=14, pady=(0, 12), sticky="w")

        right = ctk.CTkFrame(tab, fg_color=SCREEN_BG, corner_radius=16)
        right.grid(row=0, column=1, padx=(6, 12), pady=12, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(right, text="Kiểu tải", font=ctk.CTkFont(size=14, weight="bold"), text_color="#FCA5A5").grid(row=0, column=0, padx=16, pady=(16, 6), sticky="w")
        mode_frame = ctk.CTkFrame(right, fg_color="transparent")
        mode_frame.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")
        ctk.CTkRadioButton(mode_frame, text="Video", variable=self.youtube_mode, value="video", command=self.update_youtube_quality_options).grid(row=0, column=0, padx=(0, 12), pady=4, sticky="w")
        ctk.CTkRadioButton(mode_frame, text="Âm thanh", variable=self.youtube_mode, value="audio", command=self.update_youtube_quality_options).grid(row=0, column=1, padx=0, pady=4, sticky="w")

        ctk.CTkLabel(right, text="Chất lượng khả dụng", font=ctk.CTkFont(size=14, weight="bold"), text_color="#FCA5A5").grid(row=2, column=0, padx=16, pady=(8, 6), sticky="w")
        self.youtube_quality_menu = ctk.CTkOptionMenu(right, values=["Chưa có chất lượng"], variable=self.youtube_quality, state="disabled")
        self.youtube_quality_menu.grid(row=3, column=0, padx=16, pady=(0, 10), sticky="ew")

        self.youtube_summary_box = ctk.CTkTextbox(right, height=180, font=ctk.CTkFont(family="Consolas", size=11))
        self.youtube_summary_box.grid(row=4, column=0, padx=16, pady=(0, 10), sticky="nsew")
        self.youtube_summary_box.insert("1.0", "Sau khi phân tích, danh sách chất lượng video hoặc âm thanh sẽ hiện ở đây.")
        self.youtube_summary_box.configure(state="disabled")

        self.btn_download_youtube = ctk.CTkButton(
            right,
            text="Tải về máy",
            fg_color="#10B981",
            hover_color="#059669",
            font=ctk.CTkFont(weight="bold"),
            command=self.start_youtube_download,
            state="disabled",
            height=38
        )
        self.btn_download_youtube.grid(row=5, column=0, padx=16, pady=(0, 16), sticky="ew")

    # =========================================================
    # LOGIC PDF – MỞ VÀ HIỂN THỊ
    # =========================================================

    def open_pdf_file(self):
        import fitz
        path = filedialog.askopenfilename(title="Chọn tệp PDF cần xem và cắt", filetypes=[("PDF", "*.pdf")])
        if not path:
            return

        if self.pdf_document:
            self.pdf_document.close()

        self.pdf_document = fitz.open(path)
        self.pdf_path = path
        self.pdf_current_page = 0
        self.pdf_total_pages = len(self.pdf_document)
        self.pdf_page_images = []
        self.pdf_tk_images = []
        self.pdf_page_layouts = []
        self.pdf_canvas.delete("all")
        self.log(f"Đã mở: {Path(path).name}  ({self.pdf_total_pages} trang)")
        self.render_all_pages()
        self.btn_prev_page.configure(state="normal")
        self.btn_next_page.configure(state="normal")

    def render_all_pages(self):
        if not self.pdf_document:
            return
        import fitz
        self.lbl_progress.configure(text="Đang tải toàn bộ trang PDF...")
        self.progressbar.set(0)
        self.lbl_progress_percent.configure(text="0%")

        self.pdf_scale = 1.5  # keep track of render scale
        self.pdf_page_images = []
        mat = fitz.Matrix(self.pdf_scale, self.pdf_scale)
        for page_index in range(self.pdf_total_pages):
            page = self.pdf_document[page_index]
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes("ppm")
            pil_img = Image.open(io.BytesIO(img_data)).copy()
            self.pdf_page_images.append(pil_img)
            progress = (page_index + 1) / max(self.pdf_total_pages, 1)
            self.progressbar.set(progress)
            self.lbl_progress_percent.configure(text=f"{int(progress * 100)}%")

        self.pdf_page_image = self.pdf_page_images[0] if self.pdf_page_images else None
        self._display_all_pages()
        self._reset_selection()
        self.lbl_progress.configure(text="Đã tải xong toàn bộ PDF.")
        self._update_page_info(0)

    def _display_all_pages(self):
        if not self.pdf_page_images:
            return

        canvas_width = max((self.pdf_canvas.winfo_width() or 600) - 24, 200)
        page_gap = 18
        side_padding = 12
        top_padding = 12
        y_cursor = top_padding

        self.pdf_canvas.delete("all")
        self.pdf_tk_images = []
        self.pdf_page_layouts = []

        for page_index, img in enumerate(self.pdf_page_images):
            iw, ih = img.size
            fit_scale = min(1.0, canvas_width / max(iw, 1))
            disp_w = max(1, int(iw * fit_scale))
            disp_h = max(1, int(ih * fit_scale))
            display_img = img.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(display_img)
            self.pdf_tk_images.append(tk_img)

            x0 = side_padding
            y0 = y_cursor
            x1 = x0 + disp_w
            y1 = y0 + disp_h

            self.pdf_canvas.create_rectangle(
                x0 - 1, y0 - 1, x1 + 1, y1 + 1,
                outline=BORDER_COLOR, width=1, fill="#FFFFFF"
            )
            self.pdf_canvas.create_image(x0, y0, anchor="nw", image=tk_img, tags=(f"page_{page_index}", "page_img"))
            self.pdf_canvas.create_text(
                x0, y0 - 10, anchor="sw",
                text=f"Trang {page_index + 1}",
                fill=HERO_TEXT,
                font=("Segoe UI", 10, "bold")
            )

            self.pdf_page_layouts.append({
                "page_index": page_index,
                "canvas_left": x0,
                "canvas_top": y0,
                "canvas_right": x1,
                "canvas_bottom": y1,
                "display_scale": fit_scale,
            })
            y_cursor = y1 + page_gap

        total_width = side_padding * 2 + max(layout["canvas_right"] - layout["canvas_left"] for layout in self.pdf_page_layouts)
        self.pdf_canvas.configure(scrollregion=(0, 0, total_width, y_cursor))
        self._scroll_to_page(self.pdf_current_page, update_label=True)

    def on_canvas_resize(self, event):
        self._display_all_pages()

    def prev_page(self):
        if self.pdf_current_page > 0:
            self.pdf_current_page -= 1
            self._scroll_to_page(self.pdf_current_page, update_label=True)

    def next_page(self):
        if self.pdf_current_page < self.pdf_total_pages - 1:
            self.pdf_current_page += 1
            self._scroll_to_page(self.pdf_current_page, update_label=True)

    def _scroll_to_page(self, page_index, update_label=False):
        if not self.pdf_page_layouts:
            return

        page_index = max(0, min(page_index, len(self.pdf_page_layouts) - 1))
        target = self.pdf_page_layouts[page_index]
        self.pdf_current_page = page_index
        scrollregion = self.pdf_canvas.cget("scrollregion")
        if scrollregion:
            _, _, _, bottom = [float(v) for v in scrollregion.split()]
            if bottom > 0:
                self.pdf_canvas.yview_moveto(max(0.0, target["canvas_top"] / bottom))

        if update_label:
            self._update_page_info(page_index)

    def _update_page_info(self, page_index=None):
        if not self.pdf_total_pages:
            self.lbl_page_info.configure(text="Chưa mở tệp")
            return
        current = self.pdf_current_page if page_index is None else page_index
        self.lbl_page_info.configure(text=f"Trang {current + 1} / {self.pdf_total_pages}")

    def _reset_selection(self):
        self.pdf_canvas.delete("sel_rect")
        self.canvas_sel_rect = None
        self.canvas_sel_start = None
        self.btn_crop.configure(state="disabled")

    # =========================================================
    # LOGIC PDF – VẼ VÙNG CHỌN
    # =========================================================

    def on_canvas_press(self, event):
        if not self.pdf_document:
            return
        x = self.pdf_canvas.canvasx(event.x)
        y = self.pdf_canvas.canvasy(event.y)
        self.canvas_sel_start = (x, y)
        # Xóa hình chữ nhật cũ nếu có
        if self.canvas_sel_rect:
            self.pdf_canvas.delete(self.canvas_sel_rect)
            self.canvas_sel_rect = None

    def on_canvas_drag(self, event):
        if not self.canvas_sel_start:
            return
        x0, y0 = self.canvas_sel_start
        x1 = self.pdf_canvas.canvasx(event.x)
        y1 = self.pdf_canvas.canvasy(event.y)
        if self.canvas_sel_rect:
            self.pdf_canvas.delete(self.canvas_sel_rect)
        self.canvas_sel_rect = self.pdf_canvas.create_rectangle(
            x0, y0, x1, y1,
            outline="#F59E0B", width=2, dash=(6, 3), tags="sel_rect"
        )

    def on_canvas_release(self, event):
        if not self.canvas_sel_start:
            return
        x1 = self.pdf_canvas.canvasx(event.x)
        y1 = self.pdf_canvas.canvasy(event.y)
        x0, y0 = self.canvas_sel_start

        # Đảm bảo vùng chọn đủ lớn (tránh nhấp chuột đơn)
        if abs(x1 - x0) < 10 or abs(y1 - y0) < 10:
            self.btn_crop.configure(state="disabled")
            return

        self.btn_crop.configure(state="normal")

    def _get_selection_rect_on_page(self):
        """Chuyển đổi tọa độ canvas sang tọa độ trang PDF của đúng trang đã chọn."""
        import fitz
        items = self.pdf_canvas.find_withtag("sel_rect")
        if not items:
            return None
        x0, y0, x1, y1 = self.pdf_canvas.coords(items[0])
        sx0, sx1 = min(x0, x1), max(x0, x1)
        sy0, sy1 = min(y0, y1), max(y0, y1)
        center_x = (sx0 + sx1) / 2
        center_y = (sy0 + sy1) / 2

        target_layout = None
        for layout in self.pdf_page_layouts:
            if layout["canvas_left"] <= center_x <= layout["canvas_right"] and layout["canvas_top"] <= center_y <= layout["canvas_bottom"]:
                target_layout = layout
                break

        if target_layout is None:
            return None, None

        if (
            sx0 < target_layout["canvas_left"] or
            sx1 > target_layout["canvas_right"] or
            sy0 < target_layout["canvas_top"] or
            sy1 > target_layout["canvas_bottom"]
        ):
            messagebox.showwarning("Cảnh báo", "Vui lòng chỉ chọn vùng nằm gọn trong một trang PDF.")
            return "invalid", None

        display_scale = target_layout["display_scale"]
        render_to_pdf = 1.0 / self.pdf_scale

        rx0 = (sx0 - target_layout["canvas_left"]) / display_scale
        ry0 = (sy0 - target_layout["canvas_top"]) / display_scale
        rx1 = (sx1 - target_layout["canvas_left"]) / display_scale
        ry1 = (sy1 - target_layout["canvas_top"]) / display_scale

        px0 = rx0 * render_to_pdf
        py0 = ry0 * render_to_pdf
        px1 = rx1 * render_to_pdf
        py1 = ry1 * render_to_pdf

        return target_layout["page_index"], fitz.Rect(px0, py0, px1, py1)

    # =========================================================
    # LOGIC PDF – CẮT VÀ QUẢN LÝ HÀNG ĐỢI
    # =========================================================

    def do_crop(self):
        if not self.pdf_document:
            return
        import fitz

        selection = self._get_selection_rect_on_page()
        if not selection:
            messagebox.showwarning("Cảnh báo", "Vui lòng vẽ vùng cần cắt gọn trong một trang trước.")
            return
        page_index, fitz_rect = selection
        if page_index == "invalid":
            return
        if page_index is None or fitz_rect is None:
            messagebox.showwarning("Cảnh báo", "Vui lòng vẽ vùng cần cắt gọn trong một trang trước.")
            return

        # Clip vùng chọn vào trang
        page = self.pdf_document[page_index]
        page_rect = page.rect
        clipped = fitz_rect & page_rect
        if clipped.is_empty:
            messagebox.showwarning("Cảnh báo", "Vùng cắt nằm ngoài trang PDF.")
            return

        # Render vùng đó với độ phân giải cao hơn để xuất
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat, clip=clipped, alpha=False)
        img_bytes = pix.tobytes("png")
        crop_img = Image.open(io.BytesIO(img_bytes)).copy()

        label = f"Vùng {len(self.crop_rects) + 1} – Trang {page_index + 1}"
        self.crop_rects.append({
            "label": label,
            "page": page_index,
            "rect": clipped,
            "image": crop_img,
        })

        self.log(f"[CẮT] Đã thêm: {label}  ({crop_img.width}x{crop_img.height}px)")
        self.after(10, self.refresh_crop_queue_ui)

        # Xóa vùng chọn sau khi cắt
        self._reset_selection()

    def clear_all_crops(self):
        self.crop_rects.clear()
        self.log("Đã xóa toàn bộ danh sách vùng cắt.")
        self.after(10, self.refresh_crop_queue_ui)

    def crop_move_up(self, index):
        if index > 0:
            self.crop_rects[index], self.crop_rects[index - 1] = self.crop_rects[index - 1], self.crop_rects[index]
            self.after(10, self.refresh_crop_queue_ui)

    def crop_move_down(self, index):
        if index < len(self.crop_rects) - 1:
            self.crop_rects[index], self.crop_rects[index + 1] = self.crop_rects[index + 1], self.crop_rects[index]
            self.after(10, self.refresh_crop_queue_ui)

    def crop_delete(self, index):
        removed = self.crop_rects.pop(index)
        self.log(f"Đã xóa: {removed['label']}")
        self.after(10, self.refresh_crop_queue_ui)

    def refresh_crop_queue_ui(self):
        for w in self.crop_list_frame.winfo_children():
            w.destroy()

        if not self.crop_rects:
            ctk.CTkLabel(self.crop_list_frame, text="(Chưa có vùng cắt nào)", text_color=MUTED_TEXT, font=ctk.CTkFont(size=12)).grid(row=0, column=0, padx=10, pady=10)
            return

        for i, item in enumerate(self.crop_rects):
            row_f = ctk.CTkFrame(self.crop_list_frame, fg_color=ROW_BG, corner_radius=6)
            row_f.grid(row=i, column=0, padx=4, pady=3, sticky="ew")
            row_f.grid_columnconfigure(0, weight=1)

            # Thumbnail nhỏ của vùng cắt
            thumb = item["image"].copy()
            thumb.thumbnail((48, 48))
            tk_thumb = ImageTk.PhotoImage(thumb)
            lbl_thumb = tk.Label(row_f, image=tk_thumb, bg=ROW_BG, bd=0)
            lbl_thumb.image = tk_thumb  # giữ tham chiếu
            lbl_thumb.grid(row=0, column=0, rowspan=2, padx=6, pady=5, sticky="w")

            ctk.CTkLabel(row_f, text=item["label"], anchor="w", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=1, padx=(0, 5), pady=(5, 0), sticky="ew")
            ctk.CTkLabel(row_f, text=f"{item['image'].width}×{item['image'].height}px", anchor="w", text_color=MUTED_TEXT, font=ctk.CTkFont(size=10)).grid(row=1, column=1, padx=(0, 5), pady=(0, 5), sticky="ew")

            btn_f = ctk.CTkFrame(row_f, fg_color="transparent")
            btn_f.grid(row=0, column=2, rowspan=2, padx=4, pady=4)

            ctk.CTkButton(btn_f, text="▲", width=24, height=24, state="normal" if i > 0 else "disabled", command=lambda idx=i: self.crop_move_up(idx)).grid(row=0, column=0, padx=1)
            ctk.CTkButton(btn_f, text="▼", width=24, height=24, state="normal" if i < len(self.crop_rects) - 1 else "disabled", command=lambda idx=i: self.crop_move_down(idx)).grid(row=0, column=1, padx=1)
            ctk.CTkButton(btn_f, text="❌", width=24, height=24, fg_color="#EF4444", hover_color="#DC2626", command=lambda idx=i: self.crop_delete(idx)).grid(row=0, column=2, padx=1)

    # =========================================================
    # LOGIC PDF – GỘP THÀNH 1 TRANG
    # =========================================================

    def merge_to_one_page(self):
        if not self.crop_rects:
            messagebox.showerror("Lỗi", "Chưa có vùng cắt nào. Vui lòng cắt ít nhất một vùng.")
            return

        output_path = filedialog.asksaveasfilename(
            title="Lưu tệp PDF đã gộp", defaultextension=".pdf",
            filetypes=[("Tệp PDF", "*.pdf")]
        )
        if not output_path:
            return

        self.log_clear()
        self.log(f"Đang gộp {len(self.crop_rects)} vùng cắt thành 1 trang PDF...")

        self.btn_merge_to_one.configure(state="disabled")
        t = threading.Thread(
            target=self._merge_thread,
            args=(self.crop_rects.copy(), output_path, self.print_after_merge.get()),
            daemon=True
        )
        t.start()

    def _merge_thread(self, rects, output_path, should_print):
        import fitz

        try:
            # Kích thước trang A4 theo đơn vị điểm (72 dpi)
            A4_W, A4_H = 595, 842
            MARGIN = 20
            available_w = A4_W - 2 * MARGIN
            available_h = A4_H - 2 * MARGIN

            total = len(rects)
            self.lbl_progress.configure(text="Đang tính toán bố cục trang...")
            self.progressbar.set(0)

            # Tính chiều cao của từng vùng khi scale để vừa chiều rộng
            images = [item["image"] for item in rects]
            scaled_heights = []
            for img in images:
                sw = available_w
                sh = int(img.height * (sw / img.width))
                scaled_heights.append(sh)

            total_h = sum(scaled_heights) + MARGIN * (len(rects) - 1)

            # Nếu tổng chiều cao vượt trang A4, scale nhỏ lại đồng đều
            if total_h > available_h:
                compress = available_h / total_h
                scaled_heights = [int(h * compress) for h in scaled_heights]

            # Tạo PDF mới
            out_doc = fitz.open()
            page = out_doc.new_page(width=A4_W, height=A4_H)

            y_cursor = MARGIN
            for idx, (item, sh) in enumerate(zip(rects, scaled_heights)):
                self.progressbar.set((idx + 1) / total)
                self.lbl_progress.configure(text=f"Đang đặt vùng {idx+1}/{total} lên trang...")
                self.lbl_progress_percent.configure(text=f"{int((idx+1)/total*100)}%")

                img = item["image"]
                # Chuyển PIL image sang bytes PNG để nhúng vào PDF
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)

                rect = fitz.Rect(MARGIN, y_cursor, MARGIN + available_w, y_cursor + sh)
                page.insert_image(rect, stream=buf.read())
                y_cursor += sh + MARGIN

            out_doc.save(output_path)
            out_doc.close()

            self.progressbar.set(1.0)
            self.lbl_progress_percent.configure(text="100%")
            self.lbl_progress.configure(text="Gộp thành công!")
            self.log(f"[THÀNH CÔNG] Đã lưu tệp PDF tại: {output_path}")

            if should_print:
                self.log("Đang gửi lệnh in...")
                self.print_pdf_file(output_path)

        except Exception as e:
            self.log(f"[LỖI] Lỗi khi gộp PDF: {e}")
            self.lbl_progress.configure(text="Lỗi gộp PDF.")
            self.progressbar.set(0)
            self.lbl_progress_percent.configure(text="0%")

        self.after(100, lambda: self.btn_merge_to_one.configure(state="normal"))

    # =========================================================
    # LOGIC IN TỆP PDF
    # =========================================================

    def browse_print_pdf(self):
        path = filedialog.askopenfilename(title="Chọn tệp PDF cần in", filetypes=[("PDF", "*.pdf")])
        if path:
            self.pdf_to_print.set(path)
            self.log(f"Tệp để in: {path}")

    def execute_print_pdf(self):
        p = self.pdf_to_print.get().strip()
        if not p or not os.path.exists(p):
            messagebox.showerror("Lỗi", "Vui lòng chọn tệp PDF hợp lệ để in.")
            return
        self.print_pdf_file(p)

    def print_pdf_file(self, pdf_path):
        try:
            self.log(f"Đang gửi lệnh in: {Path(pdf_path).name}")
            os.startfile(str(pdf_path), "print")
            self.log("[THÀNH CÔNG] Lệnh in đã được gửi đến máy in.")
        except Exception as e:
            self.log(f"[LỖI] Không thể in: {e}")
            messagebox.showerror("Lỗi", f"Không thể in tệp:\n{e}")

    # =========================================================
    # LOGIC TÁCH/GỘP FILE PDF
    # =========================================================

    def browse_pdf_split_file(self):
        path = filedialog.askopenfilename(title="Chọn file PDF cần tách", filetypes=[("PDF", "*.pdf")])
        if path:
            self.pdf_split_path.set(path)
            self.log(f"[PDF] File cần tách: {path}")

    def browse_pdf_split_output(self):
        folder = filedialog.askdirectory(title="Chọn thư mục lưu file PDF đã tách")
        if folder:
            self.pdf_split_output_dir.set(folder)
            self.log(f"[PDF] Thư mục lưu file tách: {folder}")

    def split_pdf_file(self):
        input_path = self.pdf_split_path.get().strip()
        output_dir = self.pdf_split_output_dir.get().strip()
        ranges_text = self.pdf_split_ranges.get().strip()

        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("Lỗi", "Vui lòng chọn file PDF nguồn hợp lệ.")
            return
        if not output_dir:
            messagebox.showerror("Lỗi", "Vui lòng chọn thư mục lưu file PDF đã tách.")
            return

        os.makedirs(output_dir, exist_ok=True)
        self.log_clear()
        self.log(f"[PDF] Bắt đầu tách: {Path(input_path).name}")
        self.btn_split_pdf.configure(state="disabled")
        self.lbl_progress.configure(text="Đang chuẩn bị tách PDF...")
        self.progressbar.set(0)
        self.lbl_progress_percent.configure(text="0%")

        threading.Thread(
            target=self._split_pdf_file_thread,
            args=(input_path, output_dir, ranges_text),
            daemon=True
        ).start()

    def _split_pdf_file_thread(self, input_path, output_dir, ranges_text):
        import fitz
        doc = None
        try:
            doc = fitz.open(input_path)
            ranges = self._parse_pdf_page_ranges(ranges_text, len(doc))
            base_name = Path(input_path).stem
            total = len(ranges)
            output_files = []

            for index, (start_page, end_page) in enumerate(ranges, start=1):
                out_doc = fitz.open()
                out_doc.insert_pdf(doc, from_page=start_page - 1, to_page=end_page - 1)
                if start_page == end_page:
                    suffix = f"trang_{start_page:03d}"
                else:
                    suffix = f"trang_{start_page:03d}-{end_page:03d}"
                output_path = Path(output_dir) / f"{base_name}_{suffix}.pdf"
                out_doc.save(str(output_path), garbage=4, deflate=True)
                out_doc.close()
                output_files.append(str(output_path))

                progress = index / max(total, 1)
                self.after(0, lambda p=progress: self.progressbar.set(p))
                self.after(0, lambda p=progress: self.lbl_progress_percent.configure(text=f"{int(p * 100)}%"))
                self.after(0, lambda i=index, t=total: self.lbl_progress.configure(text=f"Đang tách PDF... {i}/{t}"))

            self.after(0, lambda: self._finish_split_pdf(output_dir, output_files))
        except Exception as e:
            self.after(0, lambda: self._handle_pdf_tool_error(f"Tách PDF thất bại: {e}", self.btn_split_pdf))
        finally:
            if doc:
                doc.close()

    def _parse_pdf_page_ranges(self, ranges_text, total_pages):
        if total_pages <= 0:
            raise ValueError("File PDF không có trang nào.")
        if not ranges_text:
            return [(page, page) for page in range(1, total_pages + 1)]

        ranges = []
        for part in ranges_text.replace(" ", "").split(","):
            if not part:
                continue
            if "-" in part:
                start_text, end_text = part.split("-", 1)
                start_page = int(start_text)
                end_page = int(end_text)
            else:
                start_page = end_page = int(part)
            if start_page < 1 or end_page < 1 or start_page > end_page or end_page > total_pages:
                raise ValueError(f"Khoảng trang không hợp lệ: {part}. File có {total_pages} trang.")
            ranges.append((start_page, end_page))

        if not ranges:
            raise ValueError("Vui lòng nhập khoảng trang hợp lệ.")
        return ranges

    def _finish_split_pdf(self, output_dir, output_files):
        self.progressbar.set(1.0)
        self.lbl_progress_percent.configure(text="100%")
        self.lbl_progress.configure(text="Tách PDF hoàn tất.")
        self.btn_split_pdf.configure(state="normal")
        self.log(f"[THÀNH CÔNG] Đã tạo {len(output_files)} file trong: {output_dir}")
        for path in output_files[:20]:
            self.log(f"[PDF] {path}")
        if len(output_files) > 20:
            self.log(f"[PDF] ... và {len(output_files) - 20} file khác")

    def add_pdf_merge_files(self):
        paths = filedialog.askopenfilenames(title="Chọn các file PDF cần gộp", filetypes=[("PDF", "*.pdf")])
        if not paths:
            return
        added = 0
        existing = set(self.pdf_merge_files)
        for path in paths:
            if path not in existing:
                self.pdf_merge_files.append(path)
                existing.add(path)
                added += 1
        self.log(f"[PDF] Đã thêm {added} file vào danh sách gộp.")
        self.refresh_pdf_merge_list_ui()

    def clear_pdf_merge_files(self):
        self.pdf_merge_files.clear()
        self.log("[PDF] Đã xóa danh sách file cần gộp.")
        self.refresh_pdf_merge_list_ui()

    def move_pdf_merge_file_up(self, index):
        if index > 0:
            self.pdf_merge_files[index], self.pdf_merge_files[index - 1] = self.pdf_merge_files[index - 1], self.pdf_merge_files[index]
            self.refresh_pdf_merge_list_ui()

    def move_pdf_merge_file_down(self, index):
        if index < len(self.pdf_merge_files) - 1:
            self.pdf_merge_files[index], self.pdf_merge_files[index + 1] = self.pdf_merge_files[index + 1], self.pdf_merge_files[index]
            self.refresh_pdf_merge_list_ui()

    def remove_pdf_merge_file(self, index):
        removed = self.pdf_merge_files.pop(index)
        self.log(f"[PDF] Đã xóa khỏi danh sách gộp: {Path(removed).name}")
        self.refresh_pdf_merge_list_ui()

    def refresh_pdf_merge_list_ui(self):
        for widget in self.pdf_merge_list_frame.winfo_children():
            widget.destroy()

        if not self.pdf_merge_files:
            ctk.CTkLabel(self.pdf_merge_list_frame, text="(Chưa có file PDF nào)", text_color=MUTED_TEXT).grid(row=0, column=0, padx=10, pady=10)
            return

        for index, path in enumerate(self.pdf_merge_files):
            row = ctk.CTkFrame(self.pdf_merge_list_frame, fg_color=ROW_BG, corner_radius=6)
            row.grid(row=index, column=0, padx=4, pady=3, sticky="ew")
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=f"{index + 1}. {Path(path).name}", anchor="w", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, padx=8, pady=(6, 0), sticky="ew")
            ctk.CTkLabel(row, text=path, anchor="w", text_color=MUTED_TEXT, font=ctk.CTkFont(size=10)).grid(row=1, column=0, padx=8, pady=(0, 6), sticky="ew")
            buttons = ctk.CTkFrame(row, fg_color="transparent")
            buttons.grid(row=0, column=1, rowspan=2, padx=4, pady=4)
            ctk.CTkButton(buttons, text="▲", width=26, height=24, state="normal" if index > 0 else "disabled", command=lambda i=index: self.move_pdf_merge_file_up(i)).grid(row=0, column=0, padx=1)
            ctk.CTkButton(buttons, text="▼", width=26, height=24, state="normal" if index < len(self.pdf_merge_files) - 1 else "disabled", command=lambda i=index: self.move_pdf_merge_file_down(i)).grid(row=0, column=1, padx=1)
            ctk.CTkButton(buttons, text="X", width=26, height=24, fg_color="#EF4444", hover_color="#DC2626", command=lambda i=index: self.remove_pdf_merge_file(i)).grid(row=0, column=2, padx=1)

    def merge_pdf_files(self):
        input_paths = self.pdf_merge_files.copy()
        if len(input_paths) < 2:
            messagebox.showerror("Lỗi", "Vui lòng chọn ít nhất 2 file PDF để gộp.")
            return
        missing = [path for path in input_paths if not os.path.exists(path)]
        if missing:
            messagebox.showerror("Lỗi", f"Một số file không tồn tại:\n{missing[0]}")
            return

        output_path = filedialog.asksaveasfilename(
            title="Lưu file PDF đã gộp",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")]
        )
        if not output_path:
            return

        self.log_clear()
        self.log(f"[PDF] Bắt đầu gộp {len(input_paths)} file PDF...")
        self.btn_merge_pdf_files.configure(state="disabled")
        self.lbl_progress.configure(text="Đang chuẩn bị gộp PDF...")
        self.progressbar.set(0)
        self.lbl_progress_percent.configure(text="0%")

        threading.Thread(
            target=self._merge_pdf_files_thread,
            args=(input_paths, output_path),
            daemon=True
        ).start()

    def _merge_pdf_files_thread(self, input_paths, output_path):
        import fitz
        out_doc = None
        try:
            out_doc = fitz.open()
            total = len(input_paths)
            for index, path in enumerate(input_paths, start=1):
                src = fitz.open(path)
                out_doc.insert_pdf(src)
                src.close()

                progress = index / max(total, 1)
                self.after(0, lambda p=progress: self.progressbar.set(p))
                self.after(0, lambda p=progress: self.lbl_progress_percent.configure(text=f"{int(p * 100)}%"))
                self.after(0, lambda i=index, t=total: self.lbl_progress.configure(text=f"Đang gộp PDF... {i}/{t}"))

            out_doc.save(output_path, garbage=4, deflate=True)
            self.after(0, lambda: self._finish_merge_pdf(output_path, total))
        except Exception as e:
            self.after(0, lambda: self._handle_pdf_tool_error(f"Gộp PDF thất bại: {e}", self.btn_merge_pdf_files))
        finally:
            if out_doc:
                out_doc.close()

    def _finish_merge_pdf(self, output_path, total_files):
        self.progressbar.set(1.0)
        self.lbl_progress_percent.configure(text="100%")
        self.lbl_progress.configure(text="Gộp PDF hoàn tất.")
        self.btn_merge_pdf_files.configure(state="normal")
        self.log(f"[THÀNH CÔNG] Đã gộp {total_files} file thành: {output_path}")

    def _handle_pdf_tool_error(self, message, button):
        self.lbl_progress.configure(text="Lỗi xử lý PDF.")
        self.progressbar.set(0)
        self.lbl_progress_percent.configure(text="0%")
        button.configure(state="normal")
        self.log(f"[LỖI] {message}")
        messagebox.showerror("Lỗi", message)

    # =========================================================
    # LOGIC TẢI YOUTUBE
    # =========================================================

    def browse_youtube_output(self):
        folder = filedialog.askdirectory(title="Chọn thư mục lưu video/audio YouTube")
        if folder:
            self.youtube_output_dir.set(folder)
            self.log(f"[YOUTUBE] Thư mục lưu: {folder}")

    def start_youtube_analysis(self):
        url = self.youtube_url.get().strip()
        if not url:
            messagebox.showerror("Lỗi", "Vui lòng nhập liên kết YouTube cần phân tích.")
            return

        self.log_clear()
        self.log(f"[YOUTUBE] Bắt đầu phân tích: {url}")
        self.youtube_title.set("Đang phân tích liên kết...")
        self._set_youtube_summary("Đang phân tích chất lượng khả dụng của video...")
        self.youtube_quality.set("Đang tải dữ liệu...")
        self.youtube_quality_menu.configure(values=["Đang tải dữ liệu..."], state="disabled")
        self.btn_download_youtube.configure(state="disabled")
        self.btn_analyze_youtube.configure(state="disabled")
        self.lbl_progress.configure(text="Đang phân tích video YouTube...")
        self.progressbar.set(0)
        self.lbl_progress_percent.configure(text="0%")

        threading.Thread(target=self._analyze_youtube_thread, args=(url,), daemon=True).start()

    def _analyze_youtube_thread(self, url):
        try:
            cmd = [
                sys.executable,
                "-m",
                "yt_dlp",
                "--dump-single-json",
                "--skip-download",
                "--no-warnings",
                "--no-playlist",
                "--ignore-config",
                "--extractor-args",
                "youtube:player_client=android,web",
                url,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
                env=self._build_sanitized_env()
            )
            info = json.loads(result.stdout)

            self.youtube_last_info = info
            self.youtube_video_formats, self.youtube_audio_formats = self._build_youtube_format_lists(info)
            self.youtube_format_map = {
                "video": {item["label"]: item for item in self.youtube_video_formats},
                "audio": {item["label"]: item for item in self.youtube_audio_formats},
            }

            self.after(0, self._apply_youtube_analysis_result)
        except Exception as e:
            self.after(0, lambda: self._handle_youtube_error(f"Không thể phân tích liên kết: {e}"))

    def _apply_youtube_analysis_result(self):
        title = self.youtube_last_info.get("title", "Không lấy được tiêu đề") if self.youtube_last_info else "Không lấy được tiêu đề"
        duration = self._format_seconds(self.youtube_last_info.get("duration")) if self.youtube_last_info else "?"
        uploader = self.youtube_last_info.get("uploader", "Không rõ") if self.youtube_last_info else "Không rõ"
        self.youtube_title.set(f"{title}\nKênh: {uploader} | Thời lượng: {duration}")

        lines = [
            f"Video khả dụng: {len(self.youtube_video_formats)} lựa chọn",
            f"Âm thanh khả dụng: {len(self.youtube_audio_formats)} lựa chọn",
        ]
        if self.ffmpeg_path and not self.ffmpeg_available:
            lines.append("Lưu ý: đã bỏ qua bản FFmpeg lỗi trên máy. Video cần ghép âm thanh có thể chưa tải được đến khi thay FFmpeg chuẩn.")
        elif not self.ffmpeg_available:
            lines.append("Lưu ý: máy chưa có FFmpeg, các lựa chọn video cần ghép âm thanh có thể tải không thành công.")
        self._set_youtube_summary("\n".join(lines))

        self.update_youtube_quality_options()
        self.btn_analyze_youtube.configure(state="normal")
        self.lbl_progress.configure(text="Phân tích YouTube hoàn tất.")
        self.progressbar.set(1.0)
        self.lbl_progress_percent.configure(text="100%")
        self.log(f"[YOUTUBE] Đã phân tích xong: {title}")

    def update_youtube_quality_options(self):
        mode = self.youtube_mode.get()
        options = self.youtube_video_formats if mode == "video" else self.youtube_audio_formats
        labels = [item["label"] for item in options]
        summary_lines = [item["detail"] for item in options[:30]]

        if labels:
            self.youtube_quality_menu.configure(values=labels, state="normal")
            self.youtube_quality.set(labels[0])
            self._set_youtube_summary("\n".join(summary_lines))
            self.btn_download_youtube.configure(state="normal")
        else:
            self.youtube_quality_menu.configure(values=["Không có chất lượng phù hợp"], state="disabled")
            self.youtube_quality.set("Không có chất lượng phù hợp")
            self._set_youtube_summary("Không tìm thấy lựa chọn phù hợp cho chế độ hiện tại.")
            self.btn_download_youtube.configure(state="disabled")

    def start_youtube_download(self):
        url = self.youtube_url.get().strip()
        output_dir = self.youtube_output_dir.get().strip()
        mode = self.youtube_mode.get()
        selected_label = self.youtube_quality.get().strip()

        if not url:
            messagebox.showerror("Lỗi", "Vui lòng nhập liên kết YouTube trước.")
            return
        if not output_dir:
            messagebox.showerror("Lỗi", "Vui lòng chọn thư mục lưu.")
            return

        selected = self.youtube_format_map.get(mode, {}).get(selected_label)
        if not selected:
            messagebox.showerror("Lỗi", "Vui lòng phân tích lại và chọn một chất lượng hợp lệ.")
            return

        os.makedirs(output_dir, exist_ok=True)
        self.log_clear()
        self.log(f"[YOUTUBE] Bắt đầu tải: {selected_label}")
        self.lbl_progress.configure(text="Đang tải YouTube...")
        self.progressbar.set(0)
        self.lbl_progress_percent.configure(text="0%")
        self.btn_download_youtube.configure(state="disabled")
        self.btn_analyze_youtube.configure(state="disabled")

        threading.Thread(target=self._download_youtube_thread, args=(url, output_dir, mode, selected), daemon=True).start()

    def _download_youtube_thread(self, url, output_dir, mode, selected):
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "ignoreconfig": True,
                "continuedl": True,
                "retries": 10,
                "fragment_retries": 10,
                "file_access_retries": 5,
                "socket_timeout": 30,
                "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
                "outtmpl": str(Path(output_dir) / "%(title).180B [%(id)s].%(ext)s"),
                "progress_hooks": [self._youtube_progress_hook],
            }

            if mode == "video":
                ydl_opts["format"] = selected["format_selector"]
                ydl_opts["merge_output_format"] = "mp4"
            else:
                if selected.get("requires_ffmpeg") and not self.ffmpeg_available:
                    raise RuntimeError("Lựa chọn âm thanh này cần FFmpeg để tách khỏi video, nhưng FFmpeg trên máy hiện không dùng được.")
                ydl_opts["format"] = selected["format_selector"]
                ydl_opts["final_ext"] = selected.get("ext", "audio").lower()
                ydl_opts["postprocessors"] = []
                if selected.get("requires_ffmpeg"):
                    ydl_opts["postprocessors"].append({
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": selected.get("ext", "best").lower(),
                        "preferredquality": "0",
                    })

            previous_path = os.environ.get("PATH", "")
            try:
                os.environ["PATH"] = self._build_sanitized_env().get("PATH", previous_path)
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    output_file = self._resolve_youtube_output_file(ydl, info, output_dir)
            finally:
                os.environ["PATH"] = previous_path

            self.after(0, lambda: self._finish_youtube_download(output_dir, output_file))
        except Exception as e:
            self.after(0, lambda: self._handle_youtube_error(f"Tải xuống thất bại: {e}"))

    def _youtube_progress_hook(self, data):
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes", 0)
            if total:
                progress = max(0.0, min(1.0, downloaded / total))
                self.after(0, lambda p=progress: self.progressbar.set(p))
                self.after(0, lambda p=progress: self.lbl_progress_percent.configure(text=f"{int(p * 100)}%"))
            speed = data.get("speed")
            eta = data.get("eta")
            msg = f"Đang tải... {self._format_bytes(downloaded)}"
            if total:
                msg += f" / {self._format_bytes(total)}"
            if speed:
                msg += f" | {self._format_bytes(speed)}/s"
            if eta is not None:
                msg += f" | ETA: {int(eta)}s"
            self.after(0, lambda m=msg: self.lbl_progress.configure(text=m))
        elif status == "finished":
            self.after(0, lambda: self.lbl_progress.configure(text="Đang hoàn tất và ghép tệp..."))

    def _resolve_youtube_output_file(self, ydl, info, output_dir):
        requested_downloads = info.get("requested_downloads") or []
        for item in requested_downloads:
            filepath = item.get("filepath") or item.get("filename")
            if filepath and os.path.exists(filepath):
                return filepath

        candidates = []
        filename = info.get("filepath") or info.get("_filename")
        if filename:
            candidates.append(filename)
        candidates.append(ydl.prepare_filename(info))

        requested_formats = info.get("requested_formats") or []
        candidates.extend(
            item.get("filepath") or item.get("filename")
            for item in requested_formats
            if item.get("filepath") or item.get("filename")
        )

        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate

        output_path = Path(output_dir)
        existing_files = [path for path in output_path.iterdir() if path.is_file()]
        if existing_files:
            return str(max(existing_files, key=lambda path: path.stat().st_mtime))
        return candidates[0] if candidates else ""

    def _finish_youtube_download(self, output_dir, output_file):
        self.progressbar.set(1.0)
        self.lbl_progress_percent.configure(text="100%")
        self.lbl_progress.configure(text="Tải YouTube hoàn tất.")
        self.btn_download_youtube.configure(state="normal")
        self.btn_analyze_youtube.configure(state="normal")
        self.log(f"[YOUTUBE] Đã tải xong vào thư mục: {output_dir}")
        if output_file:
            self.log(f"[YOUTUBE] Tệp đầu ra: {output_file}")

    def _handle_youtube_error(self, message):
        self.lbl_progress.configure(text="Lỗi tiện ích YouTube.")
        self.progressbar.set(0)
        self.lbl_progress_percent.configure(text="0%")
        self.btn_download_youtube.configure(state="normal" if self.youtube_format_map.get(self.youtube_mode.get(), {}) else "disabled")
        self.btn_analyze_youtube.configure(state="normal")
        self.log(f"[LỖI] {message}")
        messagebox.showerror("Lỗi", message)

    def _build_youtube_format_lists(self, info):
        formats = info.get("formats", []) if info else []
        video_entries = []
        audio_entries = []

        for fmt in formats:
            format_id = fmt.get("format_id")
            if not format_id:
                continue

            vcodec = fmt.get("vcodec")
            acodec = fmt.get("acodec")
            ext = (fmt.get("ext") or "unknown").upper()
            filesize = self._format_bytes(fmt.get("filesize") or fmt.get("filesize_approx"))

            if vcodec and vcodec != "none":
                height = fmt.get("height") or 0
                fps = fmt.get("fps") or 0
                has_audio = acodec not in (None, "none")
                mode_note = "video + âm thanh" if has_audio else "video, ghép thêm âm thanh"
                format_selector = format_id if has_audio else f"{format_id}+bestaudio/best"
                detail_suffix = f" | {filesize}" if filesize != "?" else ""
                label = f"{height}p | {ext} | {'Có âm thanh' if has_audio else 'Ghép âm thanh'}"
                detail = f"{label} | fps: {fps or '?'} | chọn: {mode_note}{detail_suffix}"
                video_entries.append({
                    "label": label,
                    "detail": detail,
                    "format_selector": format_selector,
                    "height": height,
                    "fps": fps,
                    "has_audio": has_audio,
                })

            if acodec and acodec != "none" and (not vcodec or vcodec == "none"):
                abr = fmt.get("abr") or 0
                asr = fmt.get("asr") or 0
                detail_suffix = f" | {filesize}" if filesize != "?" else ""
                asr_suffix = f" | {int(asr)} Hz" if asr else ""
                label = f"{int(abr) if abr else '?'} kbps | {ext} | {acodec} | ID {format_id}"
                detail = f"{label}{asr_suffix}{detail_suffix}"
                audio_entries.append({
                    "label": label,
                    "detail": detail,
                    "format_selector": format_id,
                    "abr": abr,
                    "ext": fmt.get("ext") or "audio",
                    "requires_ffmpeg": False,
                })

        video_entries.sort(key=lambda x: (x["height"], x["fps"], x["has_audio"]), reverse=True)
        audio_entries.sort(key=lambda x: x["abr"], reverse=True)

        if not audio_entries and video_entries:
            audio_entries.append({
                "label": "Tách âm thanh từ video tốt nhất",
                "detail": "Lấy âm thanh từ video gốc. Cần FFmpeg để xuất ra file âm thanh riêng.",
                "format_selector": "bestaudio/best",
                "abr": 0,
                "ext": "mp3",
                "requires_ffmpeg": True,
            })

        return self._dedupe_youtube_entries(video_entries), self._dedupe_youtube_entries(audio_entries)

    def _dedupe_youtube_entries(self, entries):
        deduped = []
        seen = set()
        for entry in entries:
            key = entry["label"]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(entry)
        return deduped

    def _set_youtube_summary(self, text):
        self.youtube_summary_box.configure(state="normal")
        self.youtube_summary_box.delete("1.0", "end")
        self.youtube_summary_box.insert("1.0", text)
        self.youtube_summary_box.configure(state="disabled")

    def _format_bytes(self, num_bytes):
        if not num_bytes:
            return "?"
        units = ["B", "KB", "MB", "GB"]
        value = float(num_bytes)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.1f} {unit}"
            value /= 1024
        return "?"

    def _format_seconds(self, seconds):
        if not seconds:
            return "?"
        seconds = int(seconds)
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    # =========================================================
    # LOGIC XỬ LÝ ẢNH
    # =========================================================

    def browse_input(self):
        folder = filedialog.askdirectory(title="Chọn thư mục ảnh đầu vào")
        if folder:
            self.input_folder.set(folder)
            if not self.output_folder.get():
                self.output_folder.set(str(Path(folder) / "resized"))
            self.log(f"Đầu vào: {folder}")

    def browse_output(self):
        folder = filedialog.askdirectory(title="Chọn thư mục đầu ra")
        if folder:
            self.output_folder.set(folder)
            self.log(f"Đầu ra: {folder}")

    def toggle_resize_mode(self):
        mode = self.resize_mode.get()
        is_dim = mode == "dimensions"
        self.entry_width.configure(state="normal" if is_dim else "disabled")
        self.entry_height.configure(state="normal" if is_dim else "disabled")
        self.chk_aspect.configure(state="normal" if is_dim else "disabled")
        self.slider_pct.configure(state="disabled" if is_dim else "normal")

    def toggle_format_options(self, choice=None):
        fmt = self.output_format.get()
        self.slider_quality.configure(state="normal" if fmt in ["JPEG", "WEBP", "Giữ nguyên định dạng"] else "disabled")

    def update_pct_label(self, val):
        self.lbl_pct_val.configure(text=f"{int(val)}%")

    def update_quality_label(self, val):
        self.lbl_quality_val.configure(text=f"{int(val)}%")

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", f"[{timestamp}] {message}\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def log_clear(self):
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

    def cancel_processing(self):
        if self.processing_thread and self.processing_thread.is_alive():
            self.cancel_requested = True
            self.log("[CẢNH BÁO] Yêu cầu hủy bỏ...")
            self.btn_cancel.configure(state="disabled")

    def start_processing(self):
        in_path = self.input_folder.get().strip()
        out_path = self.output_folder.get().strip()
        if not in_path or not os.path.exists(in_path):
            messagebox.showerror("Lỗi", "Vui lòng chọn Thư mục đầu vào hợp lệ.")
            return
        if not out_path:
            messagebox.showerror("Lỗi", "Vui lòng chọn Thư mục đầu ra hợp lệ.")
            return

        mode = self.resize_mode.get()
        width = height = pct = None

        if mode == "dimensions":
            ws = self.entry_width.get().strip()
            hs = self.entry_height.get().strip()
            if not ws and not hs:
                messagebox.showerror("Lỗi", "Nhập ít nhất Chiều rộng hoặc Chiều cao.")
                return
            try:
                if ws:
                    width = int(ws)
                    assert width > 0
            except:
                messagebox.showerror("Lỗi", "Chiều rộng phải là số nguyên dương.")
                return
            try:
                if hs:
                    height = int(hs)
                    assert height > 0
            except:
                messagebox.showerror("Lỗi", "Chiều cao phải là số nguyên dương.")
                return
        else:
            pct = int(self.slider_pct.get())

        quality = int(self.slider_quality.get())
        target_fmt = self.output_format.get()

        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.cancel_requested = False
        self.log_clear()

        self.processing_thread = threading.Thread(
            target=self.process_images_thread,
            args=(in_path, out_path, mode, width, height, self.maintain_aspect.get(), pct, target_fmt, quality),
            daemon=True
        )
        self.processing_thread.start()

    def process_images_thread(self, in_dir, out_dir, mode, target_w, target_h, maintain_aspect, pct, format_choice, quality):
        self.log("Đang khởi động Trình Thay đổi Kích thước Ảnh...")
        self.log(f"Đầu vào: {in_dir}  |  Đầu ra: {out_dir}")
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            self.log(f"[LỖI] Không thể tạo thư mục đầu ra: {e}")
            self.after(100, lambda: self.btn_start.configure(state="normal"))
            self.after(100, lambda: self.btn_cancel.configure(state="disabled"))
            return

        supported = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.gif'}
        image_files = [f for f in os.listdir(in_dir) if Path(in_dir, f).is_file() and Path(f).suffix.lower() in supported]
        total = len(image_files)

        if total == 0:
            self.log("[CẢNH BÁO] Không tìm thấy ảnh nào trong thư mục.")
            self.progressbar.set(0)
            self.lbl_progress.configure(text="Không tìm thấy ảnh.")
            self.after(100, lambda: self.btn_start.configure(state="normal"))
            self.after(100, lambda: self.btn_cancel.configure(state="disabled"))
            return

        self.log(f"Tìm thấy {total} ảnh.")
        success_count = error_count = 0

        for index, filename in enumerate(image_files):
            if self.cancel_requested:
                self.log("[THÔNG TIN] Đã hủy bỏ.")
                break
            input_path = Path(in_dir) / filename
            prog = index / total
            self.progressbar.set(prog)
            self.lbl_progress_percent.configure(text=f"{int(prog*100)}%")
            self.lbl_progress.configure(text=f"Đang xử lý ({index+1}/{total}): {filename}")

            try:
                with Image.open(input_path) as img:
                    orig_w, orig_h = img.size
                    orig_fmt = img.format
                    if mode == "percentage":
                        s = pct / 100.0
                        new_w, new_h = max(1, int(orig_w * s)), max(1, int(orig_h * s))
                    else:
                        if maintain_aspect:
                            if target_w and not target_h:
                                new_w = target_w
                                new_h = max(1, int(orig_h * target_w / orig_w))
                            elif target_h and not target_w:
                                new_h = target_h
                                new_w = max(1, int(orig_w * target_h / orig_h))
                            else:
                                r = min(target_w / orig_w, target_h / orig_h)
                                new_w, new_h = max(1, int(orig_w * r)), max(1, int(orig_h * r))
                        else:
                            new_w = target_w or orig_w
                            new_h = target_h or orig_h

                    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                    if format_choice == "Giữ nguyên định dạng":
                        save_fmt = orig_fmt
                        ext = input_path.suffix
                    else:
                        save_fmt = format_choice
                        ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(format_choice, f".{format_choice.lower()}")

                    if save_fmt in ["JPEG", "JPG"] and resized.mode in ("RGBA", "LA", "P"):
                        bg = Image.new("RGB", resized.size, (255, 255, 255))
                        if resized.mode == "P":
                            resized = resized.convert("RGBA")
                        if resized.mode in ("RGBA", "LA"):
                            bg.paste(resized, mask=resized.split()[-1])
                        resized = bg

                    out_name = input_path.stem + ext
                    kwargs = {}
                    if save_fmt in ["JPEG", "JPG", "WEBP"]:
                        kwargs["quality"] = quality
                    resized.save(Path(out_dir) / out_name, format=save_fmt, **kwargs)
                    self.log(f"[OK] {filename} → {out_name}  ({orig_w}x{orig_h} → {new_w}x{new_h})")
                    success_count += 1
            except Exception as e:
                self.log(f"[LỖI] {filename}: {e}")
                error_count += 1

        self.log(f"--- Kết quả: {success_count}/{total} thành công, {error_count} lỗi ---")
        self.progressbar.set(1.0)
        if self.cancel_requested:
            self.lbl_progress.configure(text=f"Đã hủy. Đã xử lý {success_count} ảnh.")
            self.lbl_progress_percent.configure(text="-- %")
        else:
            self.lbl_progress.configure(text=f"Hoàn thành! {success_count} ảnh được resize.")
            self.lbl_progress_percent.configure(text="100%")
            if self.open_output_on_finish.get():
                try:
                    os.startfile(out_dir)
                except:
                    pass

        self.after(100, lambda: self.btn_start.configure(state="normal"))
        self.after(100, lambda: self.btn_cancel.configure(state="disabled"))


if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    app = ImageResizerApp()
    app.mainloop()
