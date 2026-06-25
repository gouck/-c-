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


class CompilerGUI:
    """八米编译器主界面。"""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("八米编译器 v1.0")
        self.root.geometry("860x700")
        self.root.minsize(700, 500)
        self._log_buffer: StringIO = StringIO()
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
        title = ttk.Label(main, text="八米编译器 v1.0", font=("Microsoft YaHei", 16, "bold"))
        title.pack(pady=(0, 10))

        # ── 输入文件区 ──
        file_frame = ttk.LabelFrame(main, text=" 输入文件 ", padding="8")
        file_frame.pack(fill=tk.X, pady=(0, 8))

        # spec 文件行
        self._build_file_row(file_frame, "Spec 文件:", 0,
                             default=r"../伪代码转c++/8mSpec_0821.c",
                             callback=self._browse_spec)

        # reg 文件行
        self._build_file_row(file_frame, "Reg 文件:", 1,
                             default=r"../伪代码转c++/tinyReg.txt",
                             callback=self._browse_reg)

        # ── 扩展文件区 ──
        ext_frame = ttk.LabelFrame(main, text=" 扩展文件 (.ext) ", padding="8")
        ext_frame.pack(fill=tk.X, pady=(0, 8))

        ext_top = ttk.Frame(ext_frame)
        ext_top.pack(fill=tk.X)
        ttk.Label(ext_top, text="已加载的扩展：").pack(side=tk.LEFT)
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
        # 保存引用
        if row == 0:
            self._spec_var = var
            self._spec_entry = entry
        else:
            self._reg_var = var
            self._reg_entry = entry

    # ==================================================================
    # 文件浏览回调
    # ==================================================================

    def _browse_spec(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 Spec 文件",
            filetypes=[("C/伪C 文件", "*.c *.txt"), ("所有文件", "*.*")]
        )
        if path:
            self._spec_var.set(os.path.normpath(path))

    def _browse_reg(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 Reg 文件",
            filetypes=[("TXT 文件", "*.txt"), ("所有文件", "*.*")]
        )
        if path:
            self._reg_var.set(os.path.normpath(path))

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self._out_var.set(os.path.normpath(path))

    # ==================================================================
    # 扩展管理
    # ==================================================================

    def _get_source_dir(self) -> str:
        """获取 source/ 目录的绝对路径。"""
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "source")

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
        reg = self._reg_var.get().strip()
        out_dir = self._out_var.get().strip()

        if not spec or not reg:
            messagebox.showwarning("输入不完整", "请先选择 Spec 文件和 Reg 文件。")
            return

        # 刷新扩展列表（编译前重新加载）
        self._refresh_ext_list()

        self._compile_btn.config(state=tk.DISABLED)
        self._status_var.set("● 编译中...")
        self._status_label.config(foreground="orange")
        self._clear_log()

        thread = threading.Thread(target=self._compile_thread, args=(spec, reg, out_dir), daemon=True)
        thread.start()

    def _compile_thread(self, spec: str, reg: str, out_dir: str) -> None:
        """后台编译线程。"""
        try:
            from compiler.pipeline import CompilerPipeline
            pipeline = CompilerPipeline(spec, reg, out_dir, "c", True)
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
        # 列出生成文件
        out_dir = self._out_var.get().strip()
        files_info = []
        for name in ["reg_drv.h", "reg_drv.c", "output.c"]:
            fpath = os.path.join(out_dir, name)
            if os.path.isfile(fpath):
                size = os.path.getsize(fpath)
                files_info.append(f"  {fpath}  ({size} bytes)")
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
