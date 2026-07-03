from PySide6 import QtWidgets, QtCore, QtGui
import os
import sys
import glob
import json
import re
from datetime import datetime

# 导入 release_output_binV2 中的核心函数
# 确保 tool 目录在 path 中
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from tool.release_output_binV2 import (
    read_project_version,
    read_firmware_from_flasher_args,
    merge_esp32_firmwares,
)


def get_datetime_sec_str():
    """返回当前日期+秒字符串，格式 YYYYMMDD_HHMMSS (24小时制)"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class DropLineEdit(QtWidgets.QLineEdit):
    """支持拖放目录的 QLineEdit，拖入文件夹后自动填入路径"""
    dir_dropped = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._default_style = ""
        self._drag_over_style = """
            QLineEdit {
                border: 2px dashed #0078D4;
                background-color: rgba(0, 120, 212, 0.08);
            }
        """

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            if url.isLocalFile():
                path = url.toLocalFile()
                if os.path.isdir(path):
                    self._default_style = self.styleSheet()
                    self.setStyleSheet(self._drag_over_style)
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._default_style)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent):
        self.setStyleSheet(self._default_style)
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            if url.isLocalFile():
                path = url.toLocalFile()
                if os.path.isdir(path):
                    self.setText(path)
                    self.dir_dropped.emit(path)
                    event.acceptProposedAction()
                    return
        event.ignore()


class FirmwareMergeTab(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.layout = QtWidgets.QVBoxLayout(self)

        # ========== 1. 顶部配置区 ==========
        config_group = QtWidgets.QGroupBox("合并配置")
        config_layout = QtWidgets.QGridLayout(config_group)

        # 项目根目录选择
        config_layout.addWidget(QtWidgets.QLabel("项目根目录:"), 0, 0)
        self.root_dir_edit = DropLineEdit()
        self.root_dir_edit.setPlaceholderText("选择或拖放 ESP-IDF 项目根目录（包含 CMakeLists.txt 和 build 目录）")
        self.root_dir_edit.setToolTip("选择或拖放文件夹后会自动扫描 build/flasher_args.json 中的固件文件")
        self.root_dir_edit.dir_dropped.connect(self._on_root_dir_dropped)
        config_layout.addWidget(self.root_dir_edit, 0, 1)
        self.browse_root_btn = QtWidgets.QPushButton("浏览...")
        self.browse_root_btn.clicked.connect(self._browse_root_dir)
        config_layout.addWidget(self.browse_root_btn, 0, 2)

        # 自动扫描按钮
        self.scan_btn = QtWidgets.QPushButton("自动扫描Bin文件")
        self.scan_btn.setToolTip("扫描 build/flasher_args.json 和 build 目录下的 .bin 文件")
        self.scan_btn.clicked.connect(self._scan_build_dir)
        config_layout.addWidget(self.scan_btn, 0, 3)

        # 输出文件名称预览行
        config_layout.addWidget(QtWidgets.QLabel("输出文件名:"), 1, 0)
        self.output_name_label = QtWidgets.QLabel("merged_firmware.bin")
        self.output_name_label.setStyleSheet("QLabel { font-weight: bold; color: #0078D4; }")
        config_layout.addWidget(self.output_name_label, 1, 1, 1, 2)

        # 输出目录选择
        config_layout.addWidget(QtWidgets.QLabel("输出目录:"), 2, 0)
        self.output_dir_edit = DropLineEdit()
        self.output_dir_edit.setPlaceholderText("默认为项目根目录，可拖放文件夹")
        self.output_dir_edit.setToolTip("合并后固件的保存目录，留空则保存到项目根目录")
        config_layout.addWidget(self.output_dir_edit, 2, 1)
        self.browse_output_dir_btn = QtWidgets.QPushButton("浏览...")
        self.browse_output_dir_btn.clicked.connect(self._browse_output_dir)
        config_layout.addWidget(self.browse_output_dir_btn, 2, 2)

        # 文件名格式选项
        fmt_group = QtWidgets.QGroupBox("输出文件名格式选项")
        fmt_layout = QtWidgets.QHBoxLayout(fmt_group)

        self.add_date_check = QtWidgets.QCheckBox("添加日期时间（精确到秒）")
        self.add_date_check.setToolTip("格式: YYYYMMDD_HHMMSS，例如 20260703_143025")
        self.add_date_check.setChecked(True)
        self.add_date_check.stateChanged.connect(self._update_output_name_preview)

        self.add_version_check = QtWidgets.QCheckBox("添加版本号")
        self.add_version_check.setToolTip("从 CMakeLists.txt 中读取 PROJECT_VER 版本号")
        self.add_version_check.setChecked(True)
        self.add_version_check.stateChanged.connect(self._update_output_name_preview)

        self.add_project_name_check = QtWidgets.QCheckBox("添加项目名称")
        self.add_project_name_check.setToolTip("从 CMakeLists.txt 中解析项目名称，若无法解析则使用目录名")
        self.add_project_name_check.setChecked(False)
        self.add_project_name_check.stateChanged.connect(self._update_output_name_preview)

        fmt_layout.addWidget(self.add_date_check)
        fmt_layout.addWidget(self.add_version_check)
        fmt_layout.addWidget(self.add_project_name_check)
        fmt_layout.addStretch()

        config_layout.addWidget(fmt_group, 3, 0, 1, 3)

        self.layout.addWidget(config_group)

        # ========== 2. Bin 文件列表区 ==========
        list_group = QtWidgets.QGroupBox("Bin 文件列表 (按偏移地址升序合并)")
        list_layout = QtWidgets.QVBoxLayout(list_group)

        # 表格
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["偏移地址 (Hex)", "Bin文件路径", "操作"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        list_layout.addWidget(self.table)

        # 表格操作按钮
        btn_layout = QtWidgets.QHBoxLayout()
        self.add_row_btn = QtWidgets.QPushButton("添加行")
        self.add_row_btn.setToolTip("手动添加一个 bin 文件和偏移地址")
        self.add_row_btn.clicked.connect(self._add_row)
        self.clear_table_btn = QtWidgets.QPushButton("清空列表")
        self.clear_table_btn.clicked.connect(lambda: self.table.setRowCount(0))
        btn_layout.addWidget(self.add_row_btn)
        btn_layout.addWidget(self.clear_table_btn)

        # 芯片和 Flash 信息显示
        self.chip_info_label = QtWidgets.QLabel("芯片: 未知")
        self.flash_info_label = QtWidgets.QLabel("Flash大小: 未知")
        self.freq_info_label = QtWidgets.QLabel("频率: 未知")

        info_style = "QLabel { font-weight: bold; color: #0055A4; padding: 0px 10px; }"
        self.chip_info_label.setStyleSheet(info_style)
        self.flash_info_label.setStyleSheet(info_style)
        self.freq_info_label.setStyleSheet(info_style)

        info_widget = QtWidgets.QFrame()
        info_widget.setStyleSheet("QFrame { border: 1px solid #cccccc; border-radius: 4px; background-color: #f8f9fa; }")
        info_inner_layout = QtWidgets.QHBoxLayout(info_widget)
        info_inner_layout.setContentsMargins(5, 2, 5, 2)
        info_inner_layout.addWidget(self.chip_info_label)
        info_inner_layout.addWidget(self.flash_info_label)
        info_inner_layout.addWidget(self.freq_info_label)

        btn_layout.addWidget(info_widget)
        btn_layout.addStretch()

        self.merge_btn = QtWidgets.QPushButton("合并固件")
        self.merge_btn.setMinimumHeight(35)
        self.merge_btn.setStyleSheet("QPushButton { font-weight: bold; }")
        self.merge_btn.clicked.connect(self._merge_firmware)
        btn_layout.addWidget(self.merge_btn)

        list_layout.addLayout(btn_layout)
        self.layout.addWidget(list_group)

        # ========== 3. 日志输出区 ==========
        log_group = QtWidgets.QGroupBox("执行日志")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        self.layout.addWidget(log_group)

        # 默认添加一行空白行
        self._add_row("0x0000", "")

        # 启动时尝试读取上次保存的配置
        self._current_version = None
        self._current_project_name = None
        self._update_output_name_preview()

    # ==================== 目录浏览 ====================

    def _browse_root_dir(self):
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择项目根目录")
        if dir_path:
            self.root_dir_edit.setText(dir_path)
            self._auto_scan_if_valid(dir_path)
            self.changed.emit()

    def _on_root_dir_dropped(self, dir_path):
        """拖放目录到输入框后的处理"""
        if dir_path and os.path.isdir(dir_path):
            self._log(f"已拖放目录: {dir_path}")
            self._auto_scan_if_valid(dir_path)
            self.changed.emit()

    def _browse_output_dir(self):
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self.output_dir_edit.setText(dir_path)
            self.changed.emit()

    # ==================== 自动扫描 ====================

    def _auto_scan_if_valid(self, root_dir):
        """当目录有效时自动触发扫描"""
        if not root_dir or not os.path.isdir(root_dir):
            return
        build_dir = os.path.join(root_dir, "build")
        flasher_json = os.path.join(build_dir, "flasher_args.json")
        if os.path.exists(flasher_json):
            self._log("检测到 build/flasher_args.json，自动扫描中...")
            self._scan_build_dir()

    def _scan_build_dir(self):
        """扫描项目根目录下的 build/flasher_args.json 和 build 目录下的 .bin 文件"""
        root_dir = self.root_dir_edit.text().strip()
        if not root_dir or not os.path.isdir(root_dir):
            self._log("请先选择有效的项目根目录", "red")
            return

        build_dir = os.path.join(root_dir, "build")
        if not os.path.isdir(build_dir):
            self._log(f"错误: 项目根目录下未找到 build 目录 ({build_dir})", "red")
            self._log("请先在项目根目录执行 idf.py build 编译项目", "orange")
            return

        self._log(f"开始扫描: {build_dir} ...")
        self.table.setRowCount(0)
        found_count = 0

        # 每次扫描前重置芯片信息
        self._update_chip_info("未知", "未知", "未知")

        # 尝试解析 CMakeLists.txt 获取版本号和项目名
        self._current_version = read_project_version(root_dir)
        self._current_project_name = self._read_project_name(root_dir)
        self._update_output_name_preview()

        if self._current_version:
            self._log(f"从 CMakeLists.txt 读取到版本号: V{self._current_version}")
        if self._current_project_name:
            self._log(f"从 CMakeLists.txt 读取到项目名称: {self._current_project_name}")

        # 尝试读取 flasher_args.json
        flasher_args_path = os.path.join(build_dir, "flasher_args.json")

        if os.path.exists(flasher_args_path):
            self._log(f"发现配置文件: {flasher_args_path}，正在解析...")
            try:
                with open(flasher_args_path, 'r', encoding='utf-8') as f:
                    flasher_data = json.load(f)

                # 提取芯片和 Flash 信息
                flash_settings = flasher_data.get("flash_settings", {})
                extra_args = flasher_data.get("extra_esptool_args", {})

                chip = extra_args.get("chip", "未知")
                flash_size = flash_settings.get("flash_size", "未知")
                flash_freq = flash_settings.get("flash_freq", "未知")

                self._update_chip_info(chip, flash_size, flash_freq)
                self._log(f"解析到芯片信息: {chip}, Flash: {flash_size}, 频率: {flash_freq}")

                flash_files = flasher_data.get("flash_files", {})
                added_paths = set()
                if flash_files:
                    for offset_str, rel_path in flash_files.items():
                        full_path = os.path.abspath(os.path.join(build_dir, rel_path))
                        if os.path.exists(full_path):
                            self._add_row(offset_str, full_path)
                            found_count += 1
                            added_paths.add(full_path)
                            self._log(f"找到: {os.path.basename(full_path)} (偏移: {offset_str})")
                        else:
                            self._log(f"警告: 配置文件中提到的文件不存在: {full_path}", "orange")

                # 扫描 build 目录下额外未被配置文件覆盖的 .bin 文件
                for bin_path in glob.glob(os.path.join(build_dir, "*.bin")):
                    abs_path = os.path.abspath(bin_path)
                    if abs_path not in added_paths:
                        self._add_row("", abs_path)
                        found_count += 1
                        added_paths.add(abs_path)
                        self._log(f"找到额外文件: {os.path.basename(abs_path)} (未指定偏移地址，合并时请手动填写)", "orange")

                self._log(f"扫描完成，共添加 {found_count} 个文件。")
                return
            except Exception as e:
                self._log(f"解析 flasher_args.json 失败: {str(e)}，将回退到默认扫描方式", "orange")
        else:
            self._log("未找到 flasher_args.json，使用默认特征文件扫描...")

        # 回退：ESP32 通用特征文件扫描
        target_files = {
            "bootloader.bin": ("bootloader/bootloader.bin", 0x0000),
            "partition-table.bin": ("partition_table/partition-table.bin", 0x8000),
            "partitions.bin": ("partitions.bin", 0x8000),
            "firmware.bin": ("firmware.bin", 0x10000),
            "minimax.bin": ("minimax.bin", 0x200000),
            "generated_assets.bin": ("generated_assets.bin", 0xA00000),
        }

        for key, (rel_path, offset) in target_files.items():
            full_path = os.path.join(build_dir, rel_path)
            if not os.path.exists(full_path):
                full_path = os.path.join(build_dir, key)

            if os.path.exists(full_path):
                self._add_row(f"0x{offset:X}", full_path)
                found_count += 1
                self._log(f"找到: {os.path.basename(full_path)} (偏移: 0x{offset:X})")

        if found_count == 0:
            self._log("未在 build 目录下找到常见的预设 bin 文件，您可以手动添加。", "orange")
        else:
            self._log(f"扫描完成，找到 {found_count} 个文件。")

    def _read_project_name(self, root_dir):
        """从 CMakeLists.txt 中读取项目名称"""
        cmake_path = os.path.join(root_dir, "CMakeLists.txt")
        if not os.path.exists(cmake_path):
            return None
        try:
            with open(cmake_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 匹配 project(xxx) 或 project( xxx )
            match = re.search(r'project\s*\(\s*([^\s)]+)', content)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    # ==================== 输出文件名预览 ====================

    def _update_output_name_preview(self):
        """根据勾选项动态生成输出文件名预览"""
        parts = ["merged_firmware"]

        if self.add_project_name_check.isChecked():
            name = self._current_project_name or "project"
            parts.append(name)

        if self.add_version_check.isChecked():
            ver = self._current_version or "X.Y.Z"
            parts.append(f"V{ver}")

        if self.add_date_check.isChecked():
            date_sec = get_datetime_sec_str()
            parts.append(date_sec)

        filename = "-".join(parts) + ".bin"
        self.output_name_label.setText(filename)

    def _get_output_filename(self):
        """获取实际输出文件名（使用实时时间）"""
        parts = ["merged_firmware"]

        if self.add_project_name_check.isChecked():
            name = self._current_project_name or "project"
            parts.append(name)

        if self.add_version_check.isChecked():
            ver = self._current_version or "unknown"
            parts.append(f"V{ver}")

        if self.add_date_check.isChecked():
            date_sec = get_datetime_sec_str()
            parts.append(date_sec)

        return "-".join(parts) + ".bin"

    # ==================== 表格操作 ====================

    def _add_row(self, offset="", file_path=""):
        row = self.table.rowCount()
        self.table.insertRow(row)

        offset_item = QtWidgets.QTableWidgetItem(offset)
        self.table.setItem(row, 0, offset_item)

        # 文件路径单元格：文本框 + 浏览按钮
        file_widget = QtWidgets.QWidget()
        file_layout = QtWidgets.QHBoxLayout(file_widget)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(2)

        path_edit = QtWidgets.QLineEdit(file_path)
        browse_btn = QtWidgets.QPushButton("...")
        browse_btn.setFixedWidth(30)
        browse_btn.clicked.connect(lambda _, edit=path_edit: self._browse_row_file(edit))

        file_layout.addWidget(path_edit)
        file_layout.addWidget(browse_btn)
        self.table.setCellWidget(row, 1, file_widget)

        # 删除按钮
        del_btn = QtWidgets.QPushButton("删除")
        del_btn.clicked.connect(lambda _, r=row: self._remove_row(self.sender()))
        self.table.setCellWidget(row, 2, del_btn)

    def _browse_row_file(self, line_edit):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择 Bin 文件", "",
            "Bin Files (*.bin);;All Files (*)"
        )
        if file_path:
            line_edit.setText(file_path)
            self.changed.emit()

    def _remove_row(self, sender_btn):
        for i in range(self.table.rowCount()):
            if self.table.cellWidget(i, 2) == sender_btn:
                self.table.removeRow(i)
                break
        self.changed.emit()

    # ==================== 日志与芯片信息 ====================

    def _log(self, msg, color="black"):
        timestamp = datetime.now().strftime("[%H:%M:%S] ")
        html = f'<span style="color:{color}">{timestamp}{msg}</span>'
        self.log_text.append(html)

    def _update_chip_info(self, chip, flash_size, flash_freq):
        if hasattr(self, 'chip_info_label'):
            self.chip_info_label.setText(f"芯片: {chip}")
        if hasattr(self, 'flash_info_label'):
            self.flash_info_label.setText(f"Flash大小: {flash_size}")
        if hasattr(self, 'freq_info_label'):
            self.freq_info_label.setText(f"频率: {flash_freq}")

    # ==================== 固件合并 ====================

    def _merge_firmware(self):
        """使用 release_output_binV2 的核心逻辑进行合并"""
        # 收集表格中的有效项
        firmware_items = []
        for row in range(self.table.rowCount()):
            offset_text = self.table.item(row, 0).text().strip() if self.table.item(row, 0) else ""
            file_widget = self.table.cellWidget(row, 1)
            file_path = ""
            if file_widget:
                line_edit = file_widget.findChild(QtWidgets.QLineEdit)
                if line_edit:
                    file_path = line_edit.text().strip()

            if not offset_text or not file_path:
                continue

            try:
                offset = int(offset_text, 16) if offset_text.lower().startswith("0x") else int(offset_text)
            except ValueError:
                self._log(f"行 {row+1}: 偏移地址 '{offset_text}' 无效，必须是十六进制或十进制整数！", "red")
                return

            if not os.path.exists(file_path):
                self._log(f"行 {row+1}: 文件 '{file_path}' 不存在！", "red")
                return

            firmware_items.append((offset, file_path))

        if not firmware_items:
            self._log("没有有效的合并项！", "red")
            return

        # 按偏移地址排序
        firmware_items.sort(key=lambda x: x[0])

        # 确定输出路径
        output_filename = self._get_output_filename()
        output_dir = self.output_dir_edit.text().strip()
        root_dir = self.root_dir_edit.text().strip()

        if output_dir and os.path.isdir(output_dir):
            output_file = os.path.join(output_dir, output_filename)
        elif root_dir and os.path.isdir(root_dir):
            output_file = os.path.join(root_dir, output_filename)
        else:
            output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), output_filename)

        # 确保输出目录存在
        out_dir = os.path.dirname(output_file)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir)

        try:
            self._log(f"开始合并，目标文件: {output_file} ...")
            self._log(f"文件名包含: 日期={'是' if self.add_date_check.isChecked() else '否'}, "
                      f"版本号={'是' if self.add_version_check.isChecked() else '否'}, "
                      f"项目名={'是' if self.add_project_name_check.isChecked() else '否'}")

            firmware_paths = [item[1] for item in firmware_items]
            offsets = [item[0] for item in firmware_items]

            # 使用 release_output_binV2 的合并函数
            merge_esp32_firmwares(firmware_paths, offsets, output_file)

            file_size = os.path.getsize(output_file)
            self._log(f"合并成功！文件已保存到: {output_file}", "green")
            self._log(f"文件大小: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)", "green")

        except Exception as e:
            self._log(f"合并失败: {str(e)}", "red")

    # ==================== 配置持久化 ====================

    def get_config(self):
        return {
            'root_dir': self.root_dir_edit.text(),
            'output_dir': self.output_dir_edit.text(),
            'add_date': self.add_date_check.isChecked(),
            'add_version': self.add_version_check.isChecked(),
            'add_project_name': self.add_project_name_check.isChecked(),
        }

    def load_config(self, cfg: dict):
        if cfg:
            self.root_dir_edit.setText(cfg.get('root_dir', ''))
            self.output_dir_edit.setText(cfg.get('output_dir', ''))
            self.add_date_check.setChecked(cfg.get('add_date', True))
            self.add_version_check.setChecked(cfg.get('add_version', True))
            self.add_project_name_check.setChecked(cfg.get('add_project_name', False))
            self._update_output_name_preview()

            # 加载配置后自动尝试扫描
            root = cfg.get('root_dir', '')
            if root:
                self._auto_scan_if_valid(root)

    def apply_fonts(self, send_font, recv_font):
        pass

    def _install_autosave_hooks(self):
        self.root_dir_edit.textChanged.connect(lambda text: self.changed.emit())
        self.output_dir_edit.textChanged.connect(lambda text: self.changed.emit())
        self.add_date_check.stateChanged.connect(lambda: self.changed.emit())
        self.add_version_check.stateChanged.connect(lambda: self.changed.emit())
        self.add_project_name_check.stateChanged.connect(lambda: self.changed.emit())

