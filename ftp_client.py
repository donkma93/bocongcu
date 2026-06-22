"""
ftp_client.py – Module FTP Client tích hợp CustomTkinter
Tính năng:
  - Kết nối FTP bằng host / port / user / password
  - Hiển thị cây thư mục & file dạng tree (lazy-load)
  - Download file / toàn bộ thư mục
  - Upload file / toàn bộ thư mục
  - Thanh tiến trình riêng cho từng tác vụ
"""

import os
import io
import threading
import time
import ftplib
from pathlib import Path, PurePosixPath
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk


# ─────────────────────────────────────────────────────────────────────────────
# HẰNG SỐ ICON (emoji đơn giản, không cần file ảnh)
# ─────────────────────────────────────────────────────────────────────────────
ICON_FOLDER  = "📁"
ICON_FILE    = "📄"
ICON_FOLDER_OPEN = "📂"
ICON_LOADING = "⏳"


class FTPClientFrame(ctk.CTkFrame):
    """Frame FTP Client – nhúng vào bất kỳ CTkTabview hoặc CTkWindow nào."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.ftp: ftplib.FTP | None = None
        self.ftp_lock = threading.Lock()
        self.current_ftp_path = "/"
        self._transfer_cancel = False
        self._node_map: dict[str, dict] = {}   # iid → {type, path}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_connection_bar()
        self._build_main_area()
        self._build_bottom_bar()

    # ─────────────────────────────────────────────────────────────────────
    # UI: THANH KẾT NỐI
    # ─────────────────────────────────────────────────────────────────────

    def _build_connection_bar(self):
        bar = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=8)
        bar.grid(row=0, column=0, padx=10, pady=(10, 4), sticky="ew")
        bar.grid_columnconfigure((1, 3, 5, 7), weight=1)

        lbl = lambda text, col: ctk.CTkLabel(bar, text=text, anchor="e").grid(
            row=0, column=col, padx=(12 if col == 0 else 4, 4), pady=10, sticky="e"
        )
        lbl("Máy chủ:", 0)
        self.var_host = ctk.StringVar(value="")
        ctk.CTkEntry(bar, textvariable=self.var_host, placeholder_text="ftp.example.com").grid(
            row=0, column=1, padx=4, pady=10, sticky="ew"
        )
        lbl("Cổng:", 2)
        self.var_port = ctk.StringVar(value="21")
        ctk.CTkEntry(bar, textvariable=self.var_port, width=55).grid(
            row=0, column=3, padx=4, pady=10, sticky="ew"
        )
        lbl("Tên đăng nhập:", 4)
        self.var_user = ctk.StringVar(value="")
        ctk.CTkEntry(bar, textvariable=self.var_user, placeholder_text="anonymous").grid(
            row=0, column=5, padx=4, pady=10, sticky="ew"
        )
        lbl("Mật khẩu:", 6)
        self.var_pass = ctk.StringVar(value="")
        ctk.CTkEntry(bar, textvariable=self.var_pass, show="*", placeholder_text="••••••").grid(
            row=0, column=7, padx=4, pady=10, sticky="ew"
        )
        self.btn_connect = ctk.CTkButton(
            bar, text="🔌 Kết nối", width=100,
            fg_color="#3B82F6", hover_color="#2563EB",
            font=ctk.CTkFont(weight="bold"),
            command=self._toggle_connect
        )
        self.btn_connect.grid(row=0, column=8, padx=(8, 12), pady=10)

    # ─────────────────────────────────────────────────────────────────────
    # UI: KHU VỰC CHÍNH (TREE + PANEL PHẢI)
    # ─────────────────────────────────────────────────────────────────────

    def _build_main_area(self):
        paned = tk.PanedWindow(self, orient="horizontal", bg="#0F172A",
                               sashwidth=6, sashrelief="flat")
        paned.grid(row=1, column=0, padx=10, pady=4, sticky="nsew")

        # ── LEFT: FTP TREE ───────────────────────────────────────────────
        left = ctk.CTkFrame(paned, fg_color="#1E293B", corner_radius=8)

        tree_header = ctk.CTkFrame(left, fg_color="transparent")
        tree_header.pack(fill="x", padx=8, pady=(8, 2))
        ctk.CTkLabel(
            tree_header, text="🌐  Cây thư mục FTP",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#60A5FA"
        ).pack(side="left")

        self.lbl_ftp_path = ctk.CTkLabel(
            tree_header, text="/", text_color="#94A3B8",
            font=ctk.CTkFont(size=11)
        )
        self.lbl_ftp_path.pack(side="right", padx=8)

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=2)
        ctk.CTkButton(btn_row, text="🔄 Làm mới", width=90, height=26,
                      command=self._refresh_tree).pack(side="left", padx=(0, 4))
        ctk.CTkButton(btn_row, text="📥 Tải xuống", width=100, height=26,
                      fg_color="#8B5CF6", hover_color="#7C3AED",
                      command=self._download_selected).pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text="📤 Tải lên", width=100, height=26,
                      fg_color="#10B981", hover_color="#059669",
                      command=self._upload_to_selected).pack(side="left", padx=4)

        # Treeview
        tree_frame = tk.Frame(left, bg="#1E293B")
        tree_frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("FTP.Treeview",
                        background="#0F172A",
                        foreground="#E2E8F0",
                        fieldbackground="#0F172A",
                        rowheight=24,
                        font=("Consolas", 10))
        style.configure("FTP.Treeview.Heading",
                        background="#1E3A5F",
                        foreground="#93C5FD",
                        font=("Inter", 10, "bold"),
                        relief="flat")
        style.map("FTP.Treeview",
                  background=[("selected", "#2563EB")],
                  foreground=[("selected", "white")])

        vsb = tk.Scrollbar(tree_frame, orient="vertical")
        hsb = tk.Scrollbar(tree_frame, orient="horizontal")
        self.ftp_tree = ttk.Treeview(
            tree_frame,
            columns=("size", "modified"),
            show="tree headings",
            style="FTP.Treeview",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )
        vsb.config(command=self.ftp_tree.yview)
        hsb.config(command=self.ftp_tree.xview)
        self.ftp_tree.heading("#0", text="Tên")
        self.ftp_tree.heading("size", text="Kích thước")
        self.ftp_tree.heading("modified", text="Ngày sửa đổi")
        self.ftp_tree.column("#0", width=280, stretch=True)
        self.ftp_tree.column("size", width=90, anchor="e", stretch=False)
        self.ftp_tree.column("modified", width=130, stretch=False)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.ftp_tree.pack(fill="both", expand=True)

        self.ftp_tree.bind("<<TreeviewOpen>>", self._on_node_expand)

        paned.add(left, minsize=350)

        # ── RIGHT: PANEL THÔNG TIN & LOCAL ──────────────────────────────
        right = ctk.CTkFrame(paned, fg_color="#1E293B", corner_radius=8)

        ctk.CTkLabel(
            right, text="💾  Thư mục Local",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#60A5FA"
        ).pack(anchor="w", padx=12, pady=(10, 4))

        # Chọn thư mục local
        loc_row = ctk.CTkFrame(right, fg_color="transparent")
        loc_row.pack(fill="x", padx=12, pady=2)
        self.var_local_dir = ctk.StringVar(value=str(Path.home() / "Downloads"))
        ctk.CTkEntry(loc_row, textvariable=self.var_local_dir,
                     placeholder_text="Thư mục local...").pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(loc_row, text="Chọn...", width=70, height=28,
                      command=self._browse_local_dir).pack(side="right")

        # Listbox hiển thị file local
        ctk.CTkLabel(right, text="File trong thư mục local:", text_color="#94A3B8",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(8, 2))

        local_frame = tk.Frame(right, bg="#0F172A")
        local_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        style.configure("Local.Treeview",
                        background="#0F172A", foreground="#E2E8F0",
                        fieldbackground="#0F172A", rowheight=22,
                        font=("Consolas", 10))
        style.configure("Local.Treeview.Heading",
                        background="#1E3A5F", foreground="#93C5FD",
                        font=("Inter", 10, "bold"), relief="flat")
        style.map("Local.Treeview",
                  background=[("selected", "#2563EB")],
                  foreground=[("selected", "white")])

        lvsb = tk.Scrollbar(local_frame, orient="vertical")
        self.local_tree = ttk.Treeview(
            local_frame, columns=("size",), show="tree headings",
            style="Local.Treeview",
            yscrollcommand=lvsb.set
        )
        lvsb.config(command=self.local_tree.yview)
        self.local_tree.heading("#0", text="Tên file")
        self.local_tree.heading("size", text="Kích thước")
        self.local_tree.column("#0", width=200, stretch=True)
        self.local_tree.column("size", width=80, anchor="e", stretch=False)
        lvsb.pack(side="right", fill="y")
        self.local_tree.pack(fill="both", expand=True)

        ctk.CTkButton(right, text="🔄 Làm mới danh sách local", height=28,
                      command=self._refresh_local_tree).pack(fill="x", padx=12, pady=(0, 4))

        self.var_local_dir.trace_add("write", lambda *_: self.after(200, self._refresh_local_tree))
        paned.add(right, minsize=280)

    # ─────────────────────────────────────────────────────────────────────
    # UI: THANH DƯỚI (PROGRESS + LOG)
    # ─────────────────────────────────────────────────────────────────────

    def _build_bottom_bar(self):
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=2, column=0, padx=10, pady=(4, 10), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        prog_row = ctk.CTkFrame(bottom, fg_color="transparent")
        prog_row.grid(row=0, column=0, sticky="ew")
        prog_row.grid_columnconfigure(0, weight=1)

        self.lbl_status = ctk.CTkLabel(prog_row, text="Chưa kết nối.", anchor="w",
                                       text_color="#94A3B8")
        self.lbl_status.grid(row=0, column=0, padx=5, sticky="w")

        self.lbl_prog_pct = ctk.CTkLabel(prog_row, text="", anchor="e", width=45)
        self.lbl_prog_pct.grid(row=0, column=1, padx=5, sticky="e")

        self.btn_cancel_transfer = ctk.CTkButton(
            prog_row, text="⛔ Dừng", width=70, height=24,
            fg_color="#EF4444", hover_color="#DC2626",
            state="disabled", command=self._cancel_transfer
        )
        self.btn_cancel_transfer.grid(row=0, column=2, padx=5)

        self.progressbar = ctk.CTkProgressBar(bottom)
        self.progressbar.set(0)
        self.progressbar.grid(row=1, column=0, padx=5, pady=(2, 4), sticky="ew")

        self.log_box = ctk.CTkTextbox(bottom, height=90,
                                      font=ctk.CTkFont(family="Consolas", size=10))
        self.log_box.grid(row=2, column=0, padx=5, pady=(0, 0), sticky="ew")
        self.log_box.configure(state="disabled")

    # ─────────────────────────────────────────────────────────────────────
    # KẾT NỐI FTP
    # ─────────────────────────────────────────────────────────────────────

    def _toggle_connect(self):
        if self.ftp:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        host = self.var_host.get().strip()
        port = self.var_port.get().strip()
        user = self.var_user.get().strip() or "anonymous"
        pwd  = self.var_pass.get()

        if not host:
            messagebox.showerror("Lỗi", "Vui lòng nhập địa chỉ máy chủ FTP.")
            return

        try:
            port_int = int(port)
        except ValueError:
            messagebox.showerror("Lỗi", "Cổng phải là số nguyên.")
            return

        self.btn_connect.configure(text="⏳ Đang kết nối...", state="disabled")
        self._log(f"Đang kết nối đến {host}:{port_int} ...")

        threading.Thread(
            target=self._connect_thread,
            args=(host, port_int, user, pwd),
            daemon=True
        ).start()

    def _connect_thread(self, host, port, user, pwd):
        try:
            ftp = ftplib.FTP()
            ftp.connect(host, port, timeout=15)
            ftp.login(user, pwd)
            ftp.encoding = "utf-8"
            self.ftp = ftp
            welcome = ftp.getwelcome()
            self.after(0, lambda: self._on_connected(welcome))
        except Exception as e:
            self.after(0, lambda err=e: self._on_connect_error(str(err)))

    def _on_connected(self, welcome):
        self.btn_connect.configure(text="🔴 Ngắt kết nối", state="normal",
                                   fg_color="#EF4444", hover_color="#DC2626")
        self._log(f"Kết nối thành công! {welcome}")
        self.lbl_status.configure(text=f"✅ Đã kết nối: {self.var_host.get()}", text_color="#34D399")
        self._load_ftp_tree()

    def _on_connect_error(self, err):
        self.btn_connect.configure(text="🔌 Kết nối", state="normal",
                                   fg_color="#3B82F6", hover_color="#2563EB")
        self._log(f"[LỖI] Không thể kết nối: {err}")
        self.lbl_status.configure(text="❌ Kết nối thất bại.", text_color="#F87171")
        messagebox.showerror("Kết nối thất bại", f"Không thể kết nối FTP:\n{err}")

    def _disconnect(self):
        if self.ftp:
            try:
                self.ftp.quit()
            except Exception:
                pass
            self.ftp = None
        self.ftp_tree.delete(*self.ftp_tree.get_children())
        self._node_map.clear()
        self.btn_connect.configure(text="🔌 Kết nối", state="normal",
                                   fg_color="#3B82F6", hover_color="#2563EB")
        self.lbl_status.configure(text="Đã ngắt kết nối.", text_color="#94A3B8")
        self.lbl_ftp_path.configure(text="/")
        self._log("Đã ngắt kết nối FTP.")

    # ─────────────────────────────────────────────────────────────────────
    # FTP TREE LOADING
    # ─────────────────────────────────────────────────────────────────────

    def _load_ftp_tree(self, ftp_path="/"):
        self.ftp_tree.delete(*self.ftp_tree.get_children())
        self._node_map.clear()
        self._log(f"Đang tải danh sách thư mục: {ftp_path}")

        root_iid = self.ftp_tree.insert(
            "", "end",
            text=f"{ICON_FOLDER}  /",
            values=("", ""),
            open=False
        )
        self._node_map[root_iid] = {"type": "dir", "path": "/"}
        # Placeholder để có mũi tên mở rộng
        self.ftp_tree.insert(root_iid, "end", text=f"{ICON_LOADING}  Đang tải...", iid=f"__placeholder_{root_iid}")
        # Tự động mở gốc
        self.ftp_tree.item(root_iid, open=True)
        self._expand_node(root_iid)

    def _on_node_expand(self, event):
        iid = self.ftp_tree.focus()
        if not iid:
            return
        # Kiểm tra nếu có placeholder → load
        children = self.ftp_tree.get_children(iid)
        if children and str(children[0]).startswith("__placeholder_"):
            self._expand_node(iid)

    def _expand_node(self, iid):
        node_info = self._node_map.get(iid)
        if not node_info or node_info["type"] != "dir":
            return
        ftp_path = node_info["path"]

        threading.Thread(
            target=self._load_dir_thread,
            args=(iid, ftp_path),
            daemon=True
        ).start()

    def _load_dir_thread(self, parent_iid, ftp_path):
        if not self.ftp:
            return
        try:
            with self.ftp_lock:
                self.ftp.cwd(ftp_path)
                entries = []
                self.ftp.retrlines("LIST", entries.append)

            parsed = [self._parse_list_line(e, ftp_path) for e in entries]
            parsed = [p for p in parsed if p]
            # Sắp xếp: thư mục trước, file sau
            parsed.sort(key=lambda x: (0 if x["type"] == "dir" else 1, x["name"].lower()))
            self.after(0, lambda: self._populate_tree_node(parent_iid, parsed))
        except Exception as e:
            self.after(0, lambda err=e: self._log(f"[LỖI] Tải thư mục {ftp_path}: {err}"))

    def _populate_tree_node(self, parent_iid, entries):
        # Xóa placeholder
        for child in self.ftp_tree.get_children(parent_iid):
            if str(child).startswith("__placeholder_"):
                self.ftp_tree.delete(child)

        for entry in entries:
            is_dir = entry["type"] == "dir"
            icon = ICON_FOLDER if is_dir else ICON_FILE
            size_str = self._fmt_size(entry.get("size", 0)) if not is_dir else ""
            iid = self.ftp_tree.insert(
                parent_iid, "end",
                text=f"{icon}  {entry['name']}",
                values=(size_str, entry.get("modified", "")),
            )
            self._node_map[iid] = {"type": entry["type"], "path": entry["path"], "name": entry["name"]}
            if is_dir:
                # Thêm placeholder để có mũi tên expand
                self.ftp_tree.insert(iid, "end", text=f"{ICON_LOADING}  Đang tải...", iid=f"__placeholder_{iid}")

    def _parse_list_line(self, line: str, parent_path: str) -> dict | None:
        """Parse dòng LIST (Unix style: drwxr-xr-x ... name)."""
        try:
            parts = line.split(None, 8)
            if len(parts) < 9:
                return None
            perms = parts[0]
            size  = int(parts[4]) if parts[4].isdigit() else 0
            month = parts[5]
            day   = parts[6]
            year_or_time = parts[7]
            name  = parts[8]
            if name in (".", ".."):
                return None
            modified = f"{month} {day} {year_or_time}"
            ftype = "dir" if perms.startswith("d") else "file"
            path = str(PurePosixPath(parent_path) / name)
            return {"type": ftype, "name": name, "size": size, "modified": modified, "path": path}
        except Exception:
            return None

    def _refresh_tree(self):
        if not self.ftp:
            messagebox.showinfo("Thông báo", "Chưa kết nối FTP.")
            return
        self._load_ftp_tree()

    # ─────────────────────────────────────────────────────────────────────
    # LOCAL TREE
    # ─────────────────────────────────────────────────────────────────────

    def _browse_local_dir(self):
        d = filedialog.askdirectory(title="Chọn thư mục local")
        if d:
            self.var_local_dir.set(d)

    def _refresh_local_tree(self):
        self.local_tree.delete(*self.local_tree.get_children())
        local = self.var_local_dir.get().strip()
        if not local or not os.path.isdir(local):
            return
        try:
            for name in sorted(os.listdir(local)):
                full = os.path.join(local, name)
                if os.path.isdir(full):
                    self.local_tree.insert("", "end", text=f"{ICON_FOLDER}  {name}", values=("",))
                else:
                    size = os.path.getsize(full)
                    self.local_tree.insert("", "end", text=f"{ICON_FILE}  {name}", values=(self._fmt_size(size),))
        except Exception as e:
            self._log(f"[LỖI] Đọc thư mục local: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # DOWNLOAD
    # ─────────────────────────────────────────────────────────────────────

    def _download_selected(self):
        if not self.ftp:
            messagebox.showinfo("Thông báo", "Chưa kết nối FTP.")
            return

        iid = self.ftp_tree.focus()
        if not iid or iid not in self._node_map:
            messagebox.showinfo("Thông báo", "Vui lòng chọn file hoặc thư mục cần tải.")
            return

        node = self._node_map[iid]
        local_dir = filedialog.askdirectory(title="Chọn thư mục lưu về máy")
        if not local_dir:
            return

        self._transfer_cancel = False
        self.btn_cancel_transfer.configure(state="normal")
        threading.Thread(
            target=self._download_thread,
            args=(node, local_dir),
            daemon=True
        ).start()

    def _download_thread(self, node, local_dir):
        try:
            if node["type"] == "file":
                self._download_file(node["path"], local_dir)
            else:
                self._download_dir_recursive(node["path"], local_dir)
            self.after(0, lambda: self._on_transfer_done("Tải xuống hoàn thành!"))
        except Exception as e:
            self.after(0, lambda err=e: self._log(f"[LỖI] Tải xuống: {err}"))
            self.after(0, lambda: self._on_transfer_done("Tải xuống thất bại."))

    def _download_file(self, ftp_path, local_dir):
        if self._transfer_cancel:
            return
        filename = PurePosixPath(ftp_path).name
        local_path = os.path.join(local_dir, filename)
        self.after(0, lambda p=ftp_path: self._log(f"[↓] {p}"))
        self.after(0, lambda p=ftp_path: self.lbl_status.configure(text=f"↓ {p}"))

        # Lấy kích thước file
        try:
            with self.ftp_lock:
                total_size = self.ftp.size(ftp_path)
        except Exception:
            total_size = 0

        downloaded = [0]

        def progress_cb(data):
            downloaded[0] += len(data)
            if total_size > 0:
                pct = downloaded[0] / total_size
                self.after(0, lambda p=pct: self.progressbar.set(p))
                self.after(0, lambda p=pct: self.lbl_prog_pct.configure(text=f"{int(p*100)}%"))

        with open(local_path, "wb") as f:
            with self.ftp_lock:
                self.ftp.retrbinary(f"RETR {ftp_path}", lambda d: (f.write(d), progress_cb(d)), blocksize=65536)

    def _download_dir_recursive(self, ftp_dir, local_parent):
        if self._transfer_cancel:
            return
        dir_name = PurePosixPath(ftp_dir).name or "ftp_root"
        local_dir = os.path.join(local_parent, dir_name)
        os.makedirs(local_dir, exist_ok=True)
        self.after(0, lambda d=ftp_dir: self._log(f"[↓📁] {d}"))

        entries_raw = []
        with self.ftp_lock:
            self.ftp.retrlines(f"LIST {ftp_dir}", entries_raw.append)

        for line in entries_raw:
            if self._transfer_cancel:
                break
            parsed = self._parse_list_line(line, ftp_dir)
            if not parsed:
                continue
            if parsed["type"] == "dir":
                self._download_dir_recursive(parsed["path"], local_dir)
            else:
                self._download_file(parsed["path"], local_dir)

    # ─────────────────────────────────────────────────────────────────────
    # UPLOAD
    # ─────────────────────────────────────────────────────────────────────

    def _upload_to_selected(self):
        if not self.ftp:
            messagebox.showinfo("Thông báo", "Chưa kết nối FTP.")
            return

        iid = self.ftp_tree.focus()
        node = self._node_map.get(iid) if iid else None
        # Mặc định upload vào thư mục đang chọn hoặc gốc
        if node and node["type"] == "dir":
            ftp_target = node["path"]
        elif node and node["type"] == "file":
            ftp_target = str(PurePosixPath(node["path"]).parent)
        else:
            ftp_target = "/"

        # Hỏi: upload file hay thư mục?
        choice = messagebox.askquestion(
            "Chọn loại upload",
            f"Tải lên thư mục FTP: {ftp_target}\n\nChọn 'Yes' để upload Thư mục.\nChọn 'No' để upload File.",
            icon="question"
        )

        if choice == "yes":
            local_path = filedialog.askdirectory(title="Chọn thư mục cần upload")
        else:
            local_path = filedialog.askopenfilename(title="Chọn file cần upload")

        if not local_path:
            return

        self._transfer_cancel = False
        self.btn_cancel_transfer.configure(state="normal")
        threading.Thread(
            target=self._upload_thread,
            args=(local_path, ftp_target),
            daemon=True
        ).start()

    def _upload_thread(self, local_path, ftp_target):
        try:
            if os.path.isdir(local_path):
                self._upload_dir_recursive(local_path, ftp_target)
            else:
                self._upload_file(local_path, ftp_target)
            self.after(0, lambda: self._on_transfer_done("Tải lên hoàn thành!"))
            self.after(500, self._refresh_tree)
        except Exception as e:
            self.after(0, lambda err=e: self._log(f"[LỖI] Tải lên: {err}"))
            self.after(0, lambda: self._on_transfer_done("Tải lên thất bại."))

    def _upload_file(self, local_path, ftp_dir):
        if self._transfer_cancel:
            return
        filename = os.path.basename(local_path)
        ftp_path = str(PurePosixPath(ftp_dir) / filename)
        total_size = os.path.getsize(local_path)
        self.after(0, lambda p=ftp_path: self._log(f"[↑] {p}"))
        self.after(0, lambda p=ftp_path: self.lbl_status.configure(text=f"↑ {p}"))

        uploaded = [0]

        class ProgressReader:
            def __init__(self, f, total, cb):
                self.f = f
                self.total = total
                self.cb = cb

            def read(self, size=-1):
                data = self.f.read(size)
                uploaded[0] += len(data)
                if self.total > 0:
                    self.cb(uploaded[0] / self.total)
                return data

        def on_progress(pct):
            self.after(0, lambda p=pct: self.progressbar.set(p))
            self.after(0, lambda p=pct: self.lbl_prog_pct.configure(text=f"{int(p*100)}%"))

        with open(local_path, "rb") as f:
            reader = ProgressReader(f, total_size, on_progress)
            with self.ftp_lock:
                self.ftp.storbinary(f"STOR {ftp_path}", reader, blocksize=65536)

    def _upload_dir_recursive(self, local_dir, ftp_parent):
        if self._transfer_cancel:
            return
        dir_name = os.path.basename(local_dir)
        ftp_dir = str(PurePosixPath(ftp_parent) / dir_name)
        self.after(0, lambda d=ftp_dir: self._log(f"[↑📁] Tạo thư mục FTP: {d}"))
        try:
            with self.ftp_lock:
                self.ftp.mkd(ftp_dir)
        except ftplib.error_perm:
            pass  # Đã tồn tại

        for item in os.listdir(local_dir):
            if self._transfer_cancel:
                break
            full = os.path.join(local_dir, item)
            if os.path.isdir(full):
                self._upload_dir_recursive(full, ftp_dir)
            else:
                self._upload_file(full, ftp_dir)

    # ─────────────────────────────────────────────────────────────────────
    # TIỆN ÍCH
    # ─────────────────────────────────────────────────────────────────────

    def _cancel_transfer(self):
        self._transfer_cancel = True
        self._log("[⛔] Đang dừng truyền dữ liệu...")
        self.btn_cancel_transfer.configure(state="disabled")

    def _on_transfer_done(self, msg):
        self.btn_cancel_transfer.configure(state="disabled")
        self.progressbar.set(0)
        self.lbl_prog_pct.configure(text="")
        self.lbl_status.configure(text=msg)
        self._log(f"✅ {msg}")
        self._refresh_local_tree()

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    @staticmethod
    def _fmt_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        elif size < 1024 ** 2:
            return f"{size/1024:.1f} KB"
        elif size < 1024 ** 3:
            return f"{size/1024**2:.1f} MB"
        else:
            return f"{size/1024**3:.1f} GB"
