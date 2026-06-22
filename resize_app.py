import os
import sys
import threading
import time
import io
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
from PIL import ImageDraw
from ftp_client import FTPClientFrame

# Cấu hình giao diện CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class ImageResizerApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Phần mềm Xử lý Ảnh & Công cụ PDF")
        self.geometry("1000x780")
        self.minsize(900, 700)

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
        self.pdf_current_page = 0         # Index of current visible page
        self.pdf_total_pages = 0
        self.pdf_scale = 1.0              # Scale factor for rendering
        self.pdf_page_image = None        # PIL Image of the current page
        self.pdf_tk_image = None          # Tkinter PhotoImage
        self.crop_rects = []              # List of (page_index, fitz.Rect, pil_image_of_crop)
        self.canvas_sel_start = None      # (x, y) of mouse press
        self.canvas_sel_rect = None       # Canvas rectangle ID
        self.pdf_to_print = ctk.StringVar(value="")
        self.print_after_merge = ctk.BooleanVar(value=False)

        self.setup_gui()
        self.toggle_resize_mode()
        self.toggle_format_options()

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
            text_color="#3B82F6",
        )
        self.title_label.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")

        # TABVIEW CHÍNH
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, padx=20, pady=(5, 5), sticky="nsew")
        self.tabview.add("Xử lý Ảnh")
        self.tabview.add("Công cụ PDF")
        self.tabview.add("FTP Client")

        self.setup_image_tab()
        self.setup_pdf_tab()
        self.setup_ftp_tab()

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

    # =========================================================
    # TAB XỬ LÝ ẢNH
    # =========================================================

    def setup_image_tab(self):
        tab = self.tabview.tab("Xử lý Ảnh")
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
        tab = self.tabview.tab("Công cụ PDF")
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

        self.lbl_hint = ctk.CTkLabel(toolbar, text="🖱 Kéo chuột để chọn vùng cắt", text_color="#94A3B8", font=ctk.CTkFont(size=11))
        self.lbl_hint.grid(row=0, column=4, padx=(10, 0), pady=2)

        # Canvas hiển thị trang PDF
        canvas_container = ctk.CTkFrame(viewer_frame)
        canvas_container.grid(row=1, column=0, padx=8, pady=(4, 8), sticky="nsew")
        canvas_container.grid_columnconfigure(0, weight=1)
        canvas_container.grid_rowconfigure(0, weight=1)

        self.pdf_canvas = tk.Canvas(canvas_container, bg="#1E293B", cursor="crosshair", highlightthickness=0)
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
        sep = ctk.CTkFrame(right_panel, height=1, fg_color="#374151")
        sep.grid(row=5, column=0, padx=12, pady=8, sticky="ew")

        ctk.CTkLabel(right_panel, text="In tệp PDF độc lập", font=ctk.CTkFont(size=12, weight="bold"), text_color="#94A3B8").grid(row=6, column=0, padx=12, pady=(2, 4), sticky="w")
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
    # TAB FTP CLIENT
    # =========================================================

    def setup_ftp_tab(self):
        tab = self.tabview.tab("FTP Client")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        ftp_frame = FTPClientFrame(tab)
        ftp_frame.grid(row=0, column=0, sticky="nsew")

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
        self.log(f"Đã mở: {Path(path).name}  ({self.pdf_total_pages} trang)")
        self.render_current_page()
        self.btn_prev_page.configure(state="normal")
        self.btn_next_page.configure(state="normal")

    def render_current_page(self):
        if not self.pdf_document:
            return
        import fitz

        page = self.pdf_document[self.pdf_current_page]
        self.lbl_page_info.configure(text=f"Trang  {self.pdf_current_page + 1} / {self.pdf_total_pages}")

        # Render trang thành ảnh với độ phân giải 150 DPI
        mat = fitz.Matrix(1.5, 1.5)  # scale = 1.5x ≈ 108 DPI
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_data = pix.tobytes("ppm")
        pil_img = Image.open(io.BytesIO(img_data))
        self.pdf_page_image = pil_img
        self.pdf_scale = 1.5  # keep track of render scale

        # Fit ảnh vào kích thước canvas hiện tại
        self._display_page_image()

        # Xóa hình chọn cũ
        self.canvas_sel_rect = None
        self.canvas_sel_start = None
        self.btn_crop.configure(state="disabled")

    def _display_page_image(self):
        if self.pdf_page_image is None:
            return
        cw = self.pdf_canvas.winfo_width() or 600
        ch = self.pdf_canvas.winfo_height() or 800

        img = self.pdf_page_image
        iw, ih = img.size

        # Scale to fit the canvas width
        fit_scale = cw / iw
        disp_w = cw
        disp_h = int(ih * fit_scale)

        display_img = img.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        self.pdf_display_scale = fit_scale  # used for coordinate mapping

        self.pdf_tk_image = ImageTk.PhotoImage(display_img)
        self.pdf_canvas.delete("all")
        self.pdf_canvas.create_image(0, 0, anchor="nw", image=self.pdf_tk_image, tags="page_img")
        self.pdf_canvas.configure(scrollregion=(0, 0, disp_w, disp_h))

    def on_canvas_resize(self, event):
        self._display_page_image()

    def prev_page(self):
        if self.pdf_current_page > 0:
            self.pdf_current_page -= 1
            self.render_current_page()

    def next_page(self):
        if self.pdf_current_page < self.pdf_total_pages - 1:
            self.pdf_current_page += 1
            self.render_current_page()

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
        """Chuyển đổi tọa độ canvas sang tọa độ trang PDF (điểm)."""
        import fitz
        items = self.pdf_canvas.find_withtag("sel_rect")
        if not items:
            return None
        x0, y0, x1, y1 = self.pdf_canvas.coords(items[0])

        # Canvas pixels → rendered image pixels → PDF points
        scale = getattr(self, 'pdf_display_scale', 1.0)
        # self.pdf_scale is the render matrix scale (1.5)
        render_to_pdf = 1.0 / self.pdf_scale  # rendered px → pdf points (72dpi base)

        # Pixel in rendered image
        rx0 = x0 / scale
        ry0 = y0 / scale
        rx1 = x1 / scale
        ry1 = y1 / scale

        # To PDF points
        px0 = rx0 * render_to_pdf
        py0 = ry0 * render_to_pdf
        px1 = rx1 * render_to_pdf
        py1 = ry1 * render_to_pdf

        return fitz.Rect(min(px0, px1), min(py0, py1), max(px0, px1), max(py0, py1))

    # =========================================================
    # LOGIC PDF – CẮT VÀ QUẢN LÝ HÀNG ĐỢI
    # =========================================================

    def do_crop(self):
        if not self.pdf_document:
            return
        import fitz

        fitz_rect = self._get_selection_rect_on_page()
        if not fitz_rect:
            messagebox.showwarning("Cảnh báo", "Vui lòng vẽ vùng cần cắt trước.")
            return

        # Clip vùng chọn vào trang
        page = self.pdf_document[self.pdf_current_page]
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

        label = f"Vùng {len(self.crop_rects) + 1} – Trang {self.pdf_current_page + 1}"
        self.crop_rects.append({
            "label": label,
            "page": self.pdf_current_page,
            "rect": clipped,
            "image": crop_img,
        })

        self.log(f"[CẮT] Đã thêm: {label}  ({crop_img.width}x{crop_img.height}px)")
        self.after(10, self.refresh_crop_queue_ui)

        # Xóa vùng chọn sau khi cắt
        self.pdf_canvas.delete("sel_rect")
        self.canvas_sel_rect = None
        self.canvas_sel_start = None
        self.btn_crop.configure(state="disabled")

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
            ctk.CTkLabel(self.crop_list_frame, text="(Chưa có vùng cắt nào)", text_color="#6B7280", font=ctk.CTkFont(size=12)).grid(row=0, column=0, padx=10, pady=10)
            return

        for i, item in enumerate(self.crop_rects):
            row_f = ctk.CTkFrame(self.crop_list_frame, fg_color="#1E293B", corner_radius=6)
            row_f.grid(row=i, column=0, padx=4, pady=3, sticky="ew")
            row_f.grid_columnconfigure(0, weight=1)

            # Thumbnail nhỏ của vùng cắt
            thumb = item["image"].copy()
            thumb.thumbnail((48, 48))
            tk_thumb = ImageTk.PhotoImage(thumb)
            lbl_thumb = tk.Label(row_f, image=tk_thumb, bg="#1E293B", bd=0)
            lbl_thumb.image = tk_thumb  # giữ tham chiếu
            lbl_thumb.grid(row=0, column=0, rowspan=2, padx=6, pady=5, sticky="w")

            ctk.CTkLabel(row_f, text=item["label"], anchor="w", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=1, padx=(0, 5), pady=(5, 0), sticky="ew")
            ctk.CTkLabel(row_f, text=f"{item['image'].width}×{item['image'].height}px", anchor="w", text_color="#94A3B8", font=ctk.CTkFont(size=10)).grid(row=1, column=1, padx=(0, 5), pady=(0, 5), sticky="ew")

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
