from PySide6 import QtWidgets, QtCore, QtGui
import os
import glob
import json

class FirmwareMergeTab(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QtWidgets.QVBoxLayout(self)
        
        # 1. 顶部配置区
        config_group = QtWidgets.QGroupBox("合并配置")
        config_layout = QtWidgets.QGridLayout(config_group)
        
        # Build 目录选择
        config_layout.addWidget(QtWidgets.QLabel("Build目录:"), 0, 0)
        self.build_dir_edit = QtWidgets.QLineEdit()
        self.build_dir_edit.setPlaceholderText("选择或输入 build 目录路径")
        config_layout.addWidget(self.build_dir_edit, 0, 1)
        self.browse_build_btn = QtWidgets.QPushButton("浏览...")
        self.browse_build_btn.clicked.connect(self._browse_build_dir)
        config_layout.addWidget(self.browse_build_btn, 0, 2)
        
        # 自动扫描按钮
        self.scan_btn = QtWidgets.QPushButton("自动扫描Bin文件")
        self.scan_btn.clicked.connect(self._scan_build_dir)
        config_layout.addWidget(self.scan_btn, 0, 3)


        # 输出文件选择
        config_layout.addWidget(QtWidgets.QLabel("输出文件:"), 1, 0)
        self.output_file_edit = QtWidgets.QLineEdit()
        self.output_file_edit.setText("merged_firmware.bin")
        config_layout.addWidget(self.output_file_edit, 1, 1)
        self.browse_output_btn = QtWidgets.QPushButton("浏览...")
        self.browse_output_btn.clicked.connect(self._browse_output_file)
        config_layout.addWidget(self.browse_output_btn, 1, 2)
        
        self.layout.addWidget(config_group)

        
        # 2. Bin 文件列表区
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
        self.add_row_btn.clicked.connect(self._add_row)
        self.clear_table_btn = QtWidgets.QPushButton("清空列表")
        self.clear_table_btn.clicked.connect(lambda: self.table.setRowCount(0))
        btn_layout.addWidget(self.add_row_btn)
        btn_layout.addWidget(self.clear_table_btn)
        
        # 芯片和 Flash 信息显示 (放在清空列表按钮右侧)
        self.chip_info_label = QtWidgets.QLabel("芯片: 未知")
        self.flash_info_label = QtWidgets.QLabel("Flash大小: 未知")
        self.freq_info_label = QtWidgets.QLabel("频率: 未知")
        
        # 设置样式，使其居中并具有颜色区分
        info_style = "QLabel { font-weight: bold; color: #0055A4; padding: 0px 10px; }"
        self.chip_info_label.setStyleSheet(info_style)
        self.flash_info_label.setStyleSheet(info_style)
        self.freq_info_label.setStyleSheet(info_style)
        
        # 使用水平布局包裹信息标签并加上边框
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
        
        # 3. 日志输出区
        log_group = QtWidgets.QGroupBox("执行日志")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        self.layout.addWidget(log_group)

        # 默认项
        self._add_row("0x0000", "")

    def _browse_build_dir(self):
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择 Build 目录")
        if dir_path:
            self.build_dir_edit.setText(dir_path)
            self.changed.emit()

    def _browse_output_file(self):
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "保存合并后的固件", "merged_firmware.bin", "Bin Files (*.bin);;All Files (*)")
        if file_path:
            self.output_file_edit.setText(file_path)
            self.changed.emit()

    def _add_row(self, offset="", file_path=""):
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        offset_item = QtWidgets.QTableWidgetItem(offset)
        self.table.setItem(row, 0, offset_item)
        
        # 文件路径单元格：包含文本框和浏览按钮
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
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 Bin 文件", "", "Bin Files (*.bin);;All Files (*)")
        if file_path:
            line_edit.setText(file_path)
            self.changed.emit()

    def _remove_row(self, sender_btn):
        for i in range(self.table.rowCount()):
            if self.table.cellWidget(i, 2) == sender_btn:
                self.table.removeRow(i)
                break
        self.changed.emit()

    def _scan_build_dir(self):
        build_dir = self.build_dir_edit.text().strip()
        if not build_dir or not os.path.exists(build_dir):
            self._log("请先选择有效的 Build 目录", "red")
            return
            
        self._log(f"开始扫描目录: {build_dir} ...")
        self.table.setRowCount(0)
        found_count = 0
        
        # 尝试读取 flasher_args.json
        flasher_args_path = os.path.join(build_dir, "flasher_args.json")
        
        # 每次扫描前重置芯片信息显示
        self._update_chip_info("未知", "未知", "未知")
        
        if os.path.exists(flasher_args_path):
            self._log(f"发现配置文件: {flasher_args_path}，正在解析...")
            try:
                with open(flasher_args_path, 'r', encoding='utf-8') as f:
                    flasher_data = json.load(f)
                
                # 提取并更新芯片和 Flash 信息
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
                    for offset, rel_path in flash_files.items():
                        full_path = os.path.abspath(os.path.join(build_dir, rel_path))
                        if os.path.exists(full_path):
                            self._add_row(offset, full_path)
                            found_count += 1
                            added_paths.add(full_path)
                            self._log(f"找到: {full_path} (偏移: {offset})")
                        else:
                            self._log(f"警告: 配置文件中提到的文件不存在: {full_path}", "orange")

                for bin_path in glob.glob(os.path.join(build_dir, "*.bin")):
                    abs_path = os.path.abspath(bin_path)
                    if abs_path not in added_paths:
                        self._add_row("", abs_path)
                        found_count += 1
                        added_paths.add(abs_path)
                        self._log(f"找到额外文件: {abs_path} (未指定偏移地址，合并时将跳过)")

                self._log(f"扫描完成，共添加 {found_count} 个文件。")
                return
            except Exception as e:
                self._log(f"解析 flasher_args.json 失败: {str(e)}，将回退到默认扫描方式", "orange")
        else:
            self._log("未找到 flasher_args.json，使用默认特征文件扫描...")

        # 回退：ESP32S3 通用配置及默认名称映射
        # 这里参考 release_output_bin.py
        target_files = {
            "bootloader.bin": ("bootloader/bootloader.bin", 0x0000),
            "partition-table.bin": ("partition_table/partition-table.bin", 0x8000),
            "partitions.bin": ("partitions.bin", 0x8000),
            "firmware.bin": ("firmware.bin", 0x10000),
            "minimax.bin": ("minimax.bin", 0x200000),
            "generated_assets.bin": ("generated_assets.bin", 0xA00000) # 或者 0x800000 参考 release_output_bin.py 里的两种
        }
        
        # 特别扫描已知特征文件
        for key, (rel_path, offset) in target_files.items():
            full_path = os.path.join(build_dir, rel_path)
            # 如果按子目录没找到，试试直接在 build 目录找
            if not os.path.exists(full_path):
                full_path = os.path.join(build_dir, key)
                
            if os.path.exists(full_path):
                self._add_row(f"0x{offset:X}", full_path)
                found_count += 1
                self._log(f"找到: {full_path} (偏移: 0x{offset:X})")
                
        if found_count == 0:
            self._log("未在目录下找到常见的预设 bin 文件，您可以手动添加。")
        else:
            self._log(f"扫描完成，找到 {found_count} 个文件。")

    def _log(self, msg, color="black"):
        html = f'<span style="color:{color}">{msg}</span>'
        self.log_text.append(html)

    def _update_chip_info(self, chip, flash_size, flash_freq):
        if hasattr(self, 'chip_info_label'):
            self.chip_info_label.setText(f"芯片: {chip}")
        if hasattr(self, 'flash_info_label'):
            self.flash_info_label.setText(f"Flash大小: {flash_size}")
        if hasattr(self, 'freq_info_label'):
            self.freq_info_label.setText(f"频率: {flash_freq}")

    def _merge_firmware(self):
        output_file = self.output_file_edit.text().strip()
        if not output_file:
            self._log("请指定输出文件！", "red")
            return
            
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
                offset = int(offset_text, 16) if offset_text.startswith("0x") or offset_text.startswith("0X") else int(offset_text)
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
        
        try:
            self._log(f"开始合并，目标文件: {output_file} ...")
            
            max_length = 0
            for offset, file_path in firmware_items:
                file_size = os.path.getsize(file_path)
                end_address = offset + file_size
                if end_address > max_length:
                    max_length = end_address
                    
            merged_firmware = bytearray(max_length)
            # 初始化为0xFF（Flash默认擦除状态）
            for i in range(max_length):
                merged_firmware[i] = 0xFF
                
            for offset, file_path in firmware_items:
                with open(file_path, "rb") as f:
                    firmware_data = f.read()
                    merged_firmware[offset : offset + len(firmware_data)] = firmware_data
                    self._log(f"已写入: {os.path.basename(file_path)} (地址: 0x{offset:X}, 大小: {len(firmware_data)} bytes)")
                    
            # 确保输出目录存在
            out_dir = os.path.dirname(os.path.abspath(output_file))
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir)
                
            with open(output_file, "wb") as f:
                f.write(merged_firmware)
                
            self._log(f"合并成功！合并后的固件已保存到: {output_file}", "green")
            
        except Exception as e:
            self._log(f"合并失败: {str(e)}", "red")

    def get_config(self):
        return {
            'build_dir': self.build_dir_edit.text(),
            'output_file': self.output_file_edit.text()
        }

    def load_config(self, cfg: dict):
        if cfg:
            self.build_dir_edit.setText(cfg.get('build_dir', ''))
            self.output_file_edit.setText(cfg.get('output_file', 'merged_firmware.bin'))

    def apply_fonts(self, send_font, recv_font):
        pass

    def _install_autosave_hooks(self):
        self.build_dir_edit.textChanged.connect(lambda text: self.changed.emit())
        self.output_file_edit.textChanged.connect(lambda text: self.changed.emit())
