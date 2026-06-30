"""
gui.py — 八米编译器图形界面
单文件实现，基于 tkinter/ttk。
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import shutil
import threading
from io import StringIO
from pathlib import Path


# ==================================================================
# 路径工具
# ==================================================================

def _get_base_dir() -> str:
    """获取应用根目录（exe 或脚本所在目录）。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def _get_bundled_dir() -> str:
    """获取 PyInstaller 打包后的临时数据目录。"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


def _ensure_source_files() -> None:
    """确保 source/ 目录存在并包含必要的源文件。"""
    base = _get_base_dir()
    local_source = os.path.join(base, "source")
    bundled_source = os.path.join(_get_bundled_dir(), "source")
    if os.path.isdir(local_source) and os.path.isfile(os.path.join(local_source, "tinyReg.txt")):
        return
    if os.path.isdir(bundled_source):
        os.makedirs(local_source, exist_ok=True)
        for fname in os.listdir(bundled_source):
            src = os.path.join(bundled_source, fname)
            dst = os.path.join(local_source, fname)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)


def _get_default_path(filename: str) -> str:
    """获取源文件的默认路径（优先 source/ 目录）。"""
    base = _get_base_dir()
    # 优先用 source/ 下的文件
    candidate = os.path.join(base, "source", filename)
    if os.path.isfile(candidate):
        return os.path.normpath(candidate)
    # 回退到旧路径
    legacy = os.path.join(base, "..", "伪代码转c++", filename)
    return os.path.normpath(legacy)


class CompilerGUI:
    """八米编译器主界面。"""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("八米编译器 v2.0")
        self.root.geometry("860x750")
        self.root.minsize(700, 550)
        self._log_buffer: StringIO = StringIO()
        # 编译模式: "project" | "merged" | "single"，默认工程模式
        self._compile_mode = tk.StringVar(value="project")
        _ensure_source_files()
        self._build_ui()
        self._refresh_ext_list()

    # ==================================================================
    # 界面构建
    # ==================================================================

    def _build_ui(self) -> None:
        """构建完整界面布局。"""
        # 主容器
        main = ttk.Frame(self.root, padding="10")
        main.pack(fill=tk.BOTH, expand=True)

        # ── 标题 ──
        title = ttk.Label(main, text="八米编译器 v2.0", font=("Microsoft YaHei", 16, "bold"))
        title.pack(pady=(0, 10))

        # ── 模式切换（三选一，默认工程模式）──
        mode_frame = ttk.LabelFrame(main, text=" 编译模式 ", padding="8")
        mode_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Radiobutton(mode_frame, text="工程模式 — 多文件输出（推荐）",
                        variable=self._compile_mode, value="project",
                        command=self._on_mode_changed).pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(mode_frame, text="工程模式 — 合并为单文件 output.c",
                        variable=self._compile_mode, value="merged",
                        command=self._on_mode_changed).pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(mode_frame, text="单文件模式 — 传统 .c 文件输入",
                        variable=self._compile_mode, value="single",
                        command=self._on_mode_changed).pack(anchor=tk.W, pady=2)

        # ── 输入文件区 ──
        file_frame = ttk.LabelFrame(main, text=" 输入文件 ", padding="8")
        file_frame.pack(fill=tk.X, pady=(0, 8))

        # spec 文件行
        self._spec_frame = ttk.Frame(file_frame)
        self._spec_frame.pack(fill=tk.X, pady=2)
        ttk.Label(self._spec_frame, text="Spec 文件:", width=10).pack(side=tk.LEFT)
        self._spec_var = tk.StringVar(value=_get_default_path("8mSpec_0821.c"))
        self._spec_entry = ttk.Entry(self._spec_frame, textvariable=self._spec_var)
        self._spec_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self._spec_btn = ttk.Button(self._spec_frame, text="浏览...", command=self._browse_spec)
        self._spec_btn.pack(side=tk.RIGHT)
        # 工程模式下的 spec 标签
        self._spec_label = ttk.Label(self._spec_frame, text="Spec 文件:", width=10)

        # reg 文件区 — 改为多文件选择
        reg_row = ttk.Frame(file_frame)
        reg_row.pack(fill=tk.X, pady=2)
        ttk.Label(reg_row, text="Reg 文件:", width=10).pack(side=tk.LEFT)

        # 用一个 Frame 装 listbox + 按钮
        reg_list_frame = ttk.Frame(reg_row)
        reg_list_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self._reg_list = tk.Listbox(reg_list_frame, height=3, font=("Consolas", 9))
        self._reg_list.pack(side=tk.LEFT, fill=tk.X, expand=True)
        reg_scroll = ttk.Scrollbar(reg_list_frame, orient=tk.VERTICAL,
                                   command=self._reg_list.yview)
        reg_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._reg_list.config(yscrollcommand=reg_scroll.set)

        # 按钮列
        reg_btn_frame = ttk.Frame(reg_row)
        reg_btn_frame.pack(side=tk.RIGHT)
        ttk.Button(reg_btn_frame, text="添加...", command=self._browse_reg_add).pack(
            side=tk.TOP, fill=tk.X, pady=(0,2))
        ttk.Button(reg_btn_frame, text="移除", command=self._browse_reg_remove).pack(
            side=tk.TOP, fill=tk.X)

        # 预填默认 reg 文件
        default_reg = _get_default_path("tinyReg.txt")
        if default_reg and os.path.isfile(default_reg):
            self._reg_list.insert(tk.END, os.path.normpath(default_reg))

        # ── 扩展文件区 ──
        ext_frame = ttk.LabelFrame(main, text=" 扩展文件 (.ext) ", padding="8")
        ext_frame.pack(fill=tk.X, pady=(0, 8))

        ext_top = ttk.Frame(ext_frame)
        ext_top.pack(fill=tk.X)
        ttk.Label(ext_top, text="已加载的扩展：").pack(side=tk.LEFT)
        btn_remove = ttk.Button(ext_top, text="移除选中", command=self._remove_ext)
        btn_remove.pack(side=tk.RIGHT, padx=(4, 0))
        btn_import = ttk.Button(ext_top, text="导入 .ext...", command=self._import_ext)
        btn_import.pack(side=tk.RIGHT)

        # 扩展列表
        self._ext_list = tk.Listbox(ext_frame, height=4, font=("Consolas", 9))
        self._ext_list.pack(fill=tk.X, pady=(4, 0))
        scroll_ext = ttk.Scrollbar(ext_frame, orient=tk.VERTICAL, command=self._ext_list.yview)
        scroll_ext.pack(side=tk.RIGHT, fill=tk.Y)
        self._ext_list.config(yscrollcommand=scroll_ext.set)

        # ── 输出目录区 ──
        out_frame = ttk.LabelFrame(main, text=" 输出目录 ", padding="8")
        out_frame.pack(fill=tk.X, pady=(0, 8))
        out_row = ttk.Frame(out_frame)
        out_row.pack(fill=tk.X)
        self._out_var = tk.StringVar(value="./output")
        self._out_entry = ttk.Entry(out_row, textvariable=self._out_var)
        self._out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(out_row, text="浏览...", command=self._browse_output).pack(side=tk.RIGHT)

        # ── 按钮区 ──
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 8))
        self._compile_btn = ttk.Button(btn_frame, text="  编  译  ", command=self._compile)
        self._compile_btn.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="  清除日志  ", command=self._clear_log).pack(side=tk.LEFT)

        # ── 状态标签 ──
        self._status_var = tk.StringVar(value="● 就绪")
        self._status_label = ttk.Label(main, textvariable=self._status_var,
                                       foreground="gray", font=("Microsoft YaHei", 9))
        self._status_label.pack(anchor=tk.W, pady=(0, 6))

        # ── 日志区 ──
        log_frame = ttk.LabelFrame(main, text=" 输出日志 ", padding="4")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self._log_text = tk.Text(log_frame, wrap=tk.WORD, font=("Consolas", 9),
                                 state=tk.DISABLED, bg="#1e1e1e", fg="#d4d4d4",
                                 insertbackground="white")
        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_log = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self._log_text.yview)
        scroll_log.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.config(yscrollcommand=scroll_log.set)

    def _build_file_row(self, parent: ttk.Frame, label: str, row: int,
                        default: str, callback) -> None:
        """构建一个文件选择行（标签 + 输入框 + 浏览按钮）。"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=2)
        ttk.Label(frame, text=label, width=10).pack(side=tk.LEFT)
        var = tk.StringVar(value=default)
        entry = ttk.Entry(frame, textvariable=var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(frame, text="浏览...", command=callback).pack(side=tk.RIGHT)
        # 保存引用（现在只用于 spec 文件行）
        self._spec_var = var
        self._spec_entry = entry

    # ==================================================================
    # 文件浏览回调
    # ==================================================================

    def _on_mode_changed(self) -> None:
        """编译模式切换时更新界面。"""
        mode = self._compile_mode.get()
        if mode == "single":
            self._spec_label.config(text="Spec 文件:")
            self._spec_var.set(_get_default_path("8mSpec_0821.c"))
            self._spec_btn.config(command=self._browse_spec)
        else:
            self._spec_label.config(text="工程目录:")
            self._spec_var.set(_get_default_path("text") or "")
            self._spec_btn.config(command=self._browse_spec_dir)

    def _browse_spec(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 Spec 文件",
            filetypes=[("C/伪C 文件", "*.c *.txt"), ("所有文件", "*.*")]
        )
        if path:
            self._spec_var.set(os.path.normpath(path))

    def _browse_spec_dir(self) -> None:
        """工程模式：选择伪代码工程目录。"""
        path = filedialog.askdirectory(title="选择伪代码工程目录")
        if path:
            self._spec_var.set(os.path.normpath(path))

    def _browse_reg_add(self) -> None:
        """添加 reg 文件（支持多选）。"""
        paths = filedialog.askopenfilenames(
            title="选择 Reg 文件（可多选）",
            filetypes=[("TXT 文件", "*.txt"), ("所有文件", "*.*")]
        )
        for p in paths:
            np = os.path.normpath(p)
            # 避免重复添加
            existing = list(self._reg_list.get(0, tk.END))
            if np not in existing:
                self._reg_list.insert(tk.END, np)

    def _browse_reg_remove(self) -> None:
        """移除选中的 reg 文件。"""
        selected = self._reg_list.curselection()
        # 从后往前删，避免索引错位
        for i in reversed(selected):
            self._reg_list.delete(i)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self._out_var.set(os.path.normpath(path))

    # ==================================================================
    # 扩展管理
    # ==================================================================

    def _get_source_dir(self) -> str:
        """获取 source/ 目录的绝对路径。"""
        return os.path.join(_get_base_dir(), "source")

    def _import_ext(self) -> None:
        """导入 .ext 文件到 source/ 目录。"""
        files = filedialog.askopenfilenames(
            title="选择扩展文件",
            filetypes=[("扩展文件", "*.ext"), ("所有文件", "*.*")]
        )
        if not files:
            return
        source_dir = self._get_source_dir()
        os.makedirs(source_dir, exist_ok=True)
        copied = 0
        for f in files:
            dest = os.path.join(source_dir, os.path.basename(f))
            if os.path.abspath(f) != os.path.abspath(dest):
                shutil.copy2(f, dest)
                copied += 1
        self._refresh_ext_list()
        self._log(f"已导入 {copied} 个扩展文件到 {source_dir}")

    def _remove_ext(self) -> None:
        """移除选中的 .ext 文件。"""
        sel = self._ext_list.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选择要移除的扩展文件。")
            return
        item_text = self._ext_list.get(sel[0])
        fname = item_text.split()[1] if len(item_text.split()) > 1 else ""
        if not fname or not fname.endswith(".ext"):
            messagebox.showwarning("错误", "无法解析选中的文件名。")
            return
        if not messagebox.askyesno("确认移除", f"确定要删除 {fname} 吗？"):
            return
        filepath = os.path.join(self._get_source_dir(), fname)
        try:
            os.remove(filepath)
            self._log(f"已移除: {fname}")
        except OSError as e:
            messagebox.showerror("错误", f"删除失败: {e}")
        self._refresh_ext_list()

    def _refresh_ext_list(self) -> None:
        """刷新扩展列表显示。"""
        self._ext_list.delete(0, tk.END)
        source_dir = self._get_source_dir()
        if not os.path.isdir(source_dir):
            return
        for f in sorted(os.listdir(source_dir)):
            if not f.endswith(".ext") or f.upper().startswith("README"):
                continue
            info = self._parse_ext_info(os.path.join(source_dir, f))
            self._ext_list.insert(tk.END, info)

    def _parse_ext_info(self, filepath: str) -> str:
        """解析 .ext 文件，返回一行摘要信息。"""
        filename = os.path.basename(filepath)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
            # 尝试解析第一个定义块
            blocks = [b.strip() for b in text.split("\n---\n") if b.strip()]
            if not blocks:
                blocks = [text.strip()]
            parts = []
            for block in blocks:
                info = self._parse_block_info(block)
                if info:
                    parts.append(info)
            if parts:
                return f"✓ {filename:30s} {' | '.join(parts)}"
            return f"✓ {filename:30s} (空扩展)"
        except Exception:
            return f"✗ {filename:30s} (解析失败)"

    @staticmethod
    def _parse_block_info(block: str) -> str:
        """解析单个扩展定义块，返回 '类型: 关键字' 字符串。"""
        ext_type = ""
        keyword = ""
        operator = ""
        for line in block.split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key == "类型":
                ext_type = value
            elif key == "关键字":
                keyword = value
            elif key == "操作符":
                operator = value
        if ext_type == "hardware_primitive":
            return f"硬件原语: {keyword}"
        elif ext_type == "statement":
            return f"控制流: {keyword}"
        elif ext_type == "expression":
            return f"表达式: {operator}"
        return ""

    # ==================================================================
    # 编译
    # ==================================================================

    def _compile(self) -> None:
        """启动编译线程。"""
        spec = self._spec_var.get().strip()
        reg_list = list(self._reg_list.get(0, tk.END))
        reg_list = [r.strip() for r in reg_list if r.strip()]
        out_dir = self._out_var.get().strip()

        if not spec or not reg_list:
            messagebox.showwarning("输入不完整", "请先选择 Spec 文件和至少一个 Reg 文件。")
            return

        # 刷新扩展列表
        self._refresh_ext_list()

        self._compile_btn.config(state=tk.DISABLED)
        self._status_var.set("● 编译中...")
        self._status_label.config(foreground="orange")
        self._clear_log()

        thread = threading.Thread(target=self._compile_thread,
                                  args=(spec, reg_list, out_dir), daemon=True)
        thread.start()

    def _compile_thread(self, spec: str, reg_list: list, out_dir: str) -> None:
        """后台编译线程。"""
        try:
            from compiler.pipeline import CompilerPipeline
            from compiler.main import _resolve_spec_files

            mode = self._compile_mode.get()

            if mode in ("project", "merged"):
                h_files, c_files = _resolve_spec_files(spec)
                pipeline = CompilerPipeline(
                    spec_path=spec,
                    reg_paths=reg_list,
                    output_dir=out_dir,
                    target="c",
                    verbose=True,
                    h_files=h_files,
                    c_files=c_files,
                    project_mode=True,
                    merge_only=(mode == "merged"),
                )
            else:
                pipeline = CompilerPipeline(
                    spec_path=spec,
                    reg_paths=reg_list,
                    output_dir=out_dir,
                    target="c",
                    verbose=True,
                )

            old_stdout = sys.stdout
            sys.stdout = self._log_buffer = StringIO()
            pipeline.run()
            sys.stdout = old_stdout
            log_text = self._log_buffer.getvalue()
            self.root.after(0, self._compile_done, log_text)
        except Exception as e:
            import traceback
            err_msg = f"{e}\n{traceback.format_exc()}"
            self.root.after(0, self._compile_error, err_msg)

    def _compile_done(self, log_text: str) -> None:
        """编译完成回调（主线程）。"""
        self._log(log_text)
        out_dir = self._out_var.get().strip()
        files_info = []

        # 列出传统输出文件
        for name in ["reg_drv.h", "reg_drv.c", "output.c",
                     "reg_drv_common.h", "reg_drv_tinyReg.h", "reg_drv_tinyReg2.h"]:
            fpath = os.path.join(out_dir, name)
            if os.path.isfile(fpath):
                size = os.path.getsize(fpath)
                files_info.append(f"  {fpath}  ({size} bytes)")

        # 工程模式：列出 c_project 文件
        proj_dir = os.path.join(out_dir, "c_project")
        if os.path.isdir(proj_dir):
            inc_dir = os.path.join(proj_dir, "include")
            src_dir = os.path.join(proj_dir, "src")
            if os.path.isdir(inc_dir):
                files_info.append(f"\n─ 头文件 ({inc_dir}) ─")
                for f in sorted(os.listdir(inc_dir)):
                    fpath = os.path.join(inc_dir, f)
                    if os.path.isfile(fpath):
                        files_info.append(f"  {fpath}  ({os.path.getsize(fpath)} bytes)")
            if os.path.isdir(src_dir):
                files_info.append(f"\n─ 源文件 ({src_dir}) ─")
                for f in sorted(os.listdir(src_dir)):
                    fpath = os.path.join(src_dir, f)
                    if os.path.isfile(fpath):
                        files_info.append(f"  {fpath}  ({os.path.getsize(fpath)} bytes)")

        if files_info:
            self._log("✓ 编译完成! 生成文件:\n" + "\n".join(files_info))
        self._status_var.set("✓ 编译完成")
        self._status_label.config(foreground="green")
        self._compile_btn.config(state=tk.NORMAL)

    def _compile_error(self, err_msg: str) -> None:
        """编译错误回调（主线程）。"""
        self._log(f"✗ 编译失败:\n{err_msg}")
        self._status_var.set("✗ 编译失败")
        self._status_label.config(foreground="red")
        self._compile_btn.config(state=tk.NORMAL)

    # ==================================================================
    # 日志
    # ==================================================================

    def _log(self, text: str) -> None:
        """向日志区追加文本（线程安全）。"""
        self._log_text.config(state=tk.NORMAL)
        self._log_text.insert(tk.END, text + "\n")
        self._log_text.see(tk.END)
        self._log_text.config(state=tk.DISABLED)

    def _clear_log(self) -> None:
        """清空日志区。"""
        self._log_text.config(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.config(state=tk.DISABLED)


if __name__ == "__main__":
    app = CompilerGUI()
    app.root.mainloop()
