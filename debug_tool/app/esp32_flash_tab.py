from PySide6 import QtWidgets, QtCore, QtGui
import threading
import time
import sys

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except Exception:
    SERIAL_AVAILABLE = False

# Windows USB 设备变化监听
if sys.platform == 'win32':
    try:
        import ctypes
        from ctypes import wintypes
        WINDOWS_USB_AVAILABLE = True
    except Exception:
        WINDOWS_USB_AVAILABLE = False
else:
    WINDOWS_USB_AVAILABLE = False


class USBDeviceMonitor(QtCore.QAbstractNativeEventFilter):
    """Windows USB 设备插拔监听器"""
    
    # Windows 消息常量
    WM_DEVICECHANGE = 0x0219
    DBT_DEVICEARRIVAL = 0x8000
    DBT_DEVICEREMOVECOMPLETE = 0x8004
    
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
    
    def nativeEventFilter(self, eventType, message):
        if WINDOWS_USB_AVAILABLE and sys.platform == 'win32':
            try:
                if eventType == "windows_generic_MSG" or eventType == "windows_dispatcher_MSG":
                    msg = ctypes.wintypes.MSG.from_address(int(message))
                    if msg.message == self.WM_DEVICECHANGE:
                        if msg.wParam in (self.DBT_DEVICEARRIVAL, self.DBT_DEVICEREMOVECOMPLETE):
                            # USB 设备插入或拔出
                            QtCore.QTimer.singleShot(500, self.callback)
            except Exception:
                pass
        return False, 0


class ESP32FlashTab(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self, get_global_format, get_serial_blacklist=None, parent=None):
        super().__init__(parent)
        self.get_global_format = get_global_format
        self.get_serial_blacklist = get_serial_blacklist or (lambda: [])
        self.ser = None
        self.running = False
        self.reconnecting = False
        self.last_port = None
        self.last_baud = None
        self.usb_monitor = None
        self.previous_ports = set()  # 记录之前的端口列表
        self._build_ui()
        self._setup_usb_monitor()

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 顶部水平分割：左侧（串口设置+下载功能） | 右侧（操作日志）
        top_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        
        # === 左侧区域 ===
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # 1. 串口设置组
        serial_group = QtWidgets.QGroupBox('串口设置')
        serial_layout = QtWidgets.QHBoxLayout(serial_group)
        serial_layout.setContentsMargins(8, 8, 8, 8)
        serial_layout.setSpacing(6)
        
        serial_layout.addWidget(QtWidgets.QLabel('端口号:'))
        self.port_combo = QtWidgets.QComboBox()
        self.port_combo.setMinimumWidth(140)
        serial_layout.addWidget(self.port_combo)
        
        self.refresh_btn = QtWidgets.QPushButton('刷新')
        serial_layout.addWidget(self.refresh_btn)
        
        serial_layout.addWidget(QtWidgets.QLabel('波特率:'))
        self.baud_combo = QtWidgets.QComboBox()
        self.baud_combo.addItems(['115200', '230400', '460800', '921600'])
        self.baud_combo.setCurrentText('115200')
        serial_layout.addWidget(self.baud_combo)
        
        self.open_btn = QtWidgets.QPushButton('打开串口')
        self.open_btn.setFixedWidth(100)
        serial_layout.addWidget(self.open_btn)
        
        self.reset_btn = QtWidgets.QPushButton('重启')
        self.reset_btn.setFixedWidth(80)
        self.reset_btn.setEnabled(False)
        serial_layout.addWidget(self.reset_btn)
        
        self.auto_reconnect_cb = QtWidgets.QCheckBox('自动重连')
        self.auto_reconnect_cb.setChecked(True)
        self.auto_reconnect_cb.setToolTip('串口异常断开时自动尝试重连')
        serial_layout.addWidget(self.auto_reconnect_cb)
        
        self.status_label = QtWidgets.QLabel('未连接')
        self.status_label.setStyleSheet('color: red; font-weight: bold;')
        serial_layout.addWidget(self.status_label)
        serial_layout.addStretch(1)
        
        left_layout.addWidget(serial_group)

        # 2. 下载功能组
        download_group = QtWidgets.QGroupBox('下载功能')
        download_layout = QtWidgets.QVBoxLayout(download_group)
        download_layout.setContentsMargins(8, 8, 8, 8)
        download_layout.setSpacing(4)
        
        self.flash_rows = []
        for i in range(4):
            row_widget = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            
            checkbox = QtWidgets.QCheckBox()
            checkbox.setChecked(i == 0)  # 默认第一行选中
            row_layout.addWidget(checkbox)
            
            row_layout.addWidget(QtWidgets.QLabel('烧录地址:'))
            addr_edit = QtWidgets.QLineEdit()
            addr_edit.setPlaceholderText('0x1000')
            addr_edit.setFixedWidth(100)
            # 设置默认地址
            default_addrs = ['0x1000', '0x8000', '0xe000', '0x10000']
            addr_edit.setText(default_addrs[i])
            row_layout.addWidget(addr_edit)
            
            row_layout.addWidget(QtWidgets.QLabel('Bin文件:'))
            bin_edit = QtWidgets.QLineEdit()
            bin_edit.setPlaceholderText('选择bin文件路径')
            row_layout.addWidget(bin_edit, 1)
            
            browse_btn = QtWidgets.QPushButton('浏览...')
            browse_btn.setFixedWidth(80)
            row_layout.addWidget(browse_btn)
            
            download_layout.addWidget(row_widget)
            
            self.flash_rows.append({
                'checkbox': checkbox,
                'addr_edit': addr_edit,
                'bin_edit': bin_edit,
                'browse_btn': browse_btn
            })
            
            # 连接浏览按钮
            browse_btn.clicked.connect(lambda checked=False, idx=i: self._browse_bin_file(idx))
        
        # 底部按钮和进度条
        bottom_layout = QtWidgets.QHBoxLayout()
        bottom_layout.setSpacing(10)
        
        self.erase_btn = QtWidgets.QPushButton('擦除')
        self.erase_btn.setFixedWidth(100)
        self.erase_btn.setEnabled(False)
        bottom_layout.addWidget(self.erase_btn)
        
        self.flash_btn = QtWidgets.QPushButton('烧录')
        self.flash_btn.setFixedWidth(100)
        self.flash_btn.setEnabled(False)
        bottom_layout.addWidget(self.flash_btn)
        
        bottom_layout.addSpacing(20)
        bottom_layout.addWidget(QtWidgets.QLabel('进度:'))
        
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        bottom_layout.addWidget(self.progress_bar, 1)
        
        download_layout.addLayout(bottom_layout)
        left_layout.addWidget(download_group)
        left_layout.addStretch(1)

        # === 右侧区域：操作日志 ===
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        
        log_label = QtWidgets.QLabel('操作日志')
        log_label.setStyleSheet('font-weight: bold;')
        right_layout.addWidget(log_label)
        
        self.operation_log = QtWidgets.QTextEdit()
        self.operation_log.setReadOnly(True)
        self.operation_log.setMaximumHeight(300)
        right_layout.addWidget(self.operation_log)
        
        clear_log_btn = QtWidgets.QPushButton('清空日志')
        clear_log_btn.setFixedWidth(100)
        clear_log_btn.clicked.connect(self.operation_log.clear)
        right_layout.addWidget(clear_log_btn)
        right_layout.addStretch(1)

        # 添加到顶部分割器
        top_splitter.addWidget(left_widget)
        top_splitter.addWidget(right_widget)
        top_splitter.setStretchFactor(0, 3)
        top_splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(top_splitter)

        # === 底部：串口Log显示 ===
        serial_log_group = QtWidgets.QGroupBox('串口Log')
        serial_log_layout = QtWidgets.QVBoxLayout(serial_log_group)
        serial_log_layout.setContentsMargins(8, 8, 8, 8)
        serial_log_layout.setSpacing(4)
        
        self.serial_log = QtWidgets.QTextEdit()
        self.serial_log.setReadOnly(True)
        self.serial_log.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.serial_log.customContextMenuRequested.connect(self._show_serial_log_context_menu)
        serial_log_layout.addWidget(self.serial_log, 1)  # stretch factor = 1，让它占满空间
        
        log_bottom_layout = QtWidgets.QHBoxLayout()
        self.auto_scroll_cb = QtWidgets.QCheckBox('自动滚动')
        self.auto_scroll_cb.setChecked(True)
        log_bottom_layout.addWidget(self.auto_scroll_cb)
        log_bottom_layout.addStretch(1)
        
        serial_log_layout.addLayout(log_bottom_layout)
        main_layout.addWidget(serial_log_group, 1)  # stretch factor = 1，让group也能伸展

        # 连接信号
        self.refresh_btn.clicked.connect(self._refresh_ports)
        self.open_btn.clicked.connect(self._toggle_serial)
        self.reset_btn.clicked.connect(self._reset_device)
        self.erase_btn.clicked.connect(self._erase_flash)
        self.flash_btn.clicked.connect(self._flash_firmware)
        
        # 初始化串口列表
        self._refresh_ports()

    def _refresh_ports(self, auto_select_new=False):
        """刷新串口列表
        
        Args:
            auto_select_new: 是否自动选中新插入的设备
        """
        if not SERIAL_AVAILABLE:
            self._log_operation('错误: 串口库不可用', 'red')
            return
        try:
            bl = list(self.get_serial_blacklist() or [])
            
            # 获取当前端口列表
            current_ports = set()
            port_infos = []
            for info in serial.tools.list_ports.comports():
                if info.device not in bl:
                    current_ports.add(info.device)
                    port_infos.append(info)
            
            # 检测新插入的设备
            new_ports = current_ports - self.previous_ports
            
            # 更新下拉框
            self.port_combo.clear()
            for info in port_infos:
                label = f"{info.device} - {getattr(info, 'description', None) or getattr(info, 'hwid', '')}"
                self.port_combo.addItem(label, info.device)
            
            # 如果有新设备插入且需要自动选中
            if auto_select_new and new_ports:
                new_port = sorted(new_ports)[0]  # 选择第一个新设备
                for i in range(self.port_combo.count()):
                    if self.port_combo.itemData(i) == new_port:
                        self.port_combo.setCurrentIndex(i)
                        self._log_operation(f'检测到新设备: {new_port}，已自动选中', 'green')
                        break
            
            # 更新记录的端口列表
            self.previous_ports = current_ports
            
            self._log_operation(f'刷新串口列表，找到 {self.port_combo.count()} 个端口', 'blue')
        except Exception as e:
            self._log_operation(f'刷新串口失败: {e}', 'red')

    def _toggle_serial(self):
        if self.running:
            self._close_serial()
        else:
            self._open_serial()

    def _open_serial(self):
        if not SERIAL_AVAILABLE:
            self._log_operation('错误: 串口库不可用', 'red')
            return
        try:
            port = self.port_combo.currentData() or self.port_combo.currentText()
            baud = int(self.baud_combo.currentText())
            
            self.ser = serial.Serial(port=port, baudrate=baud, timeout=0.2)
            self.running = True
            self.reconnecting = False
            self.last_port = port
            self.last_baud = baud
            
            # 启动接收线程
            threading.Thread(target=self._recv_loop, daemon=True).start()
            
            self._log_operation(f'串口已打开: {port} @ {baud}', 'green')
            self.open_btn.setText('关闭串口')
            self.status_label.setText('已连接')
            self.status_label.setStyleSheet('color: green; font-weight: bold;')
            
            # 禁用配置控件
            self.port_combo.setEnabled(False)
            self.baud_combo.setEnabled(False)
            self.refresh_btn.setEnabled(False)
            
            # 启用功能按钮
            self.reset_btn.setEnabled(True)
            self.erase_btn.setEnabled(True)
            self.flash_btn.setEnabled(True)
            
        except Exception as e:
            self._log_operation(f'打开串口失败: {e}', 'red')

    def _close_serial(self):
        self.running = False
        self.reconnecting = False
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        
        self._log_operation('串口已关闭', 'blue')
        self.open_btn.setText('打开串口')
        self.status_label.setText('未连接')
        self.status_label.setStyleSheet('color: red; font-weight: bold;')
        
        # 启用配置控件
        self.port_combo.setEnabled(True)
        self.baud_combo.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        
        # 禁用功能按钮
        self.reset_btn.setEnabled(False)
        self.erase_btn.setEnabled(False)
        self.flash_btn.setEnabled(False)

    def _recv_loop(self):
        """串口接收循环"""
        while self.running and self.ser:
            try:
                data = self.ser.read(4096)
                if data:
                    self._log_serial(data)
            except Exception as e:
                if self.running:
                    self._log_operation(f'串口异常断开: {e}', 'red')
                    # 串口异常，启动重连
                    QtCore.QMetaObject.invokeMethod(
                        self,
                        "_start_reconnect",
                        QtCore.Qt.ConnectionType.QueuedConnection
                    )
                break

    @QtCore.Slot()
    def _start_reconnect(self):
        """开始重连流程"""
        print('_start_reconnect ')
        if not self.running or self.reconnecting:
            return
        
        # 检查是否启用自动重连
        if not self.auto_reconnect_cb.isChecked():
            print('串口已断开，自动重连已禁用')
            self._log_operation('串口已断开，自动重连已禁用', 'red')
            # 停止运行标志
            self.running = False
            # 关闭串口
            try:
                if self.ser:
                    self.ser.close()
            except Exception:
                pass
            self.ser = None
            # 在主线程中更新UI
            QtCore.QMetaObject.invokeMethod(
                self,
                "_update_ui_disconnected",
                QtCore.Qt.ConnectionType.QueuedConnection
            )
            return
        
        self.reconnecting = True
        self._log_operation('开始尝试重连...', 'blue')
        self.status_label.setText('重连中...')
        self.status_label.setStyleSheet('color: orange; font-weight: bold;')
        
        # 关闭当前串口
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        
        # 启动重连线程
        threading.Thread(target=self._reconnect_loop, daemon=True).start()

    @QtCore.Slot()
    def _update_ui_disconnected(self):
        """更新UI为断开状态"""
        self.open_btn.setText('打开串口')
        self.status_label.setText('未连接')
        self.status_label.setStyleSheet('color: red; font-weight: bold;')
        
        # 启用配置控件
        self.port_combo.setEnabled(True)
        self.baud_combo.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        
        # 禁用功能按钮
        self.reset_btn.setEnabled(False)
        self.erase_btn.setEnabled(False)
        self.flash_btn.setEnabled(False)

    def _reconnect_loop(self):
        """重连循环"""
        retry_count = 0
        while self.running and self.reconnecting:
            retry_count += 1
            try:
                # 尝试重新打开串口
                self.ser = serial.Serial(port=self.last_port, baudrate=self.last_baud, timeout=0.2)
                
                # 重连成功
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_reconnect_success",
                    QtCore.Qt.ConnectionType.QueuedConnection
                )
                return
                
            except Exception as e:
                # 每5次尝试记录一次日志，避免刷屏
                if retry_count % 5 == 1:
                    QtCore.QMetaObject.invokeMethod(
                        self,
                        "_log_operation",
                        QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, f'重连尝试 {retry_count}: {e}'),
                        QtCore.Q_ARG(str, 'orange')
                    )
                time.sleep(1)  # 等待1秒后重试

    @QtCore.Slot()
    def _reconnect_success(self):
        """重连成功"""
        if not self.running:
            return
        
        self.reconnecting = False
        self._log_operation(f'重连成功: {self.last_port} @ {self.last_baud}', 'green')
        self.status_label.setText('已连接')
        self.status_label.setStyleSheet('color: green; font-weight: bold;')
        
        # 启动新的接收线程
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def _browse_bin_file(self, idx: int):
        """浏览选择bin文件"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            '选择Bin文件',
            '',
            'Bin Files (*.bin);;All Files (*.*)'
        )
        if file_path:
            self.flash_rows[idx]['bin_edit'].setText(file_path)
            self._log_operation(f'选择文件[{idx+1}]: {file_path}', 'blue')

    def _reset_device(self):
        """重启设备"""
        if not self.ser:
            self._log_operation('错误: 串口未打开', 'red')
            return
        
        try:
            self._log_operation('正在重启设备...', 'blue')
            # ESP32重启：拉低EN引脚
            self.ser.setDTR(False)
            self.ser.setRTS(True)
            time.sleep(0.1)
            self.ser.setRTS(False)
            self._log_operation('设备重启完成', 'green')
        except Exception as e:
            self._log_operation(f'重启失败: {e}', 'red')

    def _erase_flash(self):
        """擦除Flash"""
        if not self.ser:
            self._log_operation('错误: 串口未打开', 'red')
            return
        
        reply = QtWidgets.QMessageBox.question(
            self,
            '确认擦除',
            '确定要擦除Flash吗？此操作将清除所有数据！',
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self._log_operation('开始擦除Flash...', 'blue')
            self.progress_bar.setValue(0)
            
            # 在新线程中执行擦除操作
            threading.Thread(target=self._do_erase, daemon=True).start()

    def _do_erase(self):
        """执行擦除操作（模拟）"""
        try:
            for i in range(101):
                time.sleep(0.02)
                QtCore.QMetaObject.invokeMethod(
                    self.progress_bar,
                    "setValue",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(int, i)
                )
            self._log_operation('Flash擦除完成', 'green')
        except Exception as e:
            self._log_operation(f'擦除失败: {e}', 'red')

    def _flash_firmware(self):
        """烧录固件"""
        if not self.ser:
            self._log_operation('错误: 串口未打开', 'red')
            return
        
        # 收集选中的烧录任务
        tasks = []
        for i, row in enumerate(self.flash_rows):
            if row['checkbox'].isChecked():
                addr = row['addr_edit'].text().strip()
                bin_path = row['bin_edit'].text().strip()
                
                if not addr or not bin_path:
                    self._log_operation(f'错误: 第{i+1}行地址或文件路径为空', 'red')
                    return
                
                tasks.append({
                    'index': i + 1,
                    'addr': addr,
                    'path': bin_path
                })
        
        if not tasks:
            self._log_operation('错误: 请至少选择一个烧录任务', 'red')
            return
        
        self._log_operation(f'开始烧录，共 {len(tasks)} 个文件...', 'blue')
        self.progress_bar.setValue(0)
        
        # 在新线程中执行烧录操作
        threading.Thread(target=self._do_flash, args=(tasks,), daemon=True).start()

    def _do_flash(self, tasks):
        """执行烧录操作（模拟）"""
        try:
            total_steps = len(tasks) * 100
            current_step = 0
            
            for task in tasks:
                self._log_operation(
                    f'烧录文件[{task["index"]}]: {task["path"]} -> {task["addr"]}',
                    'blue'
                )
                
                # 模拟烧录进度
                for i in range(100):
                    time.sleep(0.01)
                    current_step += 1
                    progress = int((current_step / total_steps) * 100)
                    QtCore.QMetaObject.invokeMethod(
                        self.progress_bar,
                        "setValue",
                        QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(int, progress)
                    )
                
                self._log_operation(f'文件[{task["index"]}]烧录完成', 'green')
            
            self._log_operation('所有文件烧录完成！', 'green')
            QtCore.QMetaObject.invokeMethod(
                self.progress_bar,
                "setValue",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(int, 100)
            )
        except Exception as e:
            self._log_operation(f'烧录失败: {e}', 'red')

    def _log_operation(self, text: str, color: str = 'black'):
        """记录操作日志"""
        cursor = self.operation_log.textCursor()
        fmt = QtGui.QTextCharFormat()
        fmt.setForeground(QtGui.QBrush(QtGui.QColor(color)))
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        cursor.setCharFormat(fmt)
        
        ts = time.time()
        tm = time.localtime(ts)
        prefix = f"[{time.strftime('%H:%M:%S', tm)}] "
        cursor.insertText(prefix + text + '\n')
        
        self.operation_log.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def _log_serial(self, data: bytes):
        """记录串口日志"""
        cursor = self.serial_log.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        
        try:
            text = data.decode('utf-8', errors='replace')
        except Exception:
            text = repr(data)
        
        cursor.insertText(text)
        
        if self.auto_scroll_cb.isChecked():
            self.serial_log.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def _show_serial_log_context_menu(self, pos):
        """显示串口log右键菜单"""
        menu = QtWidgets.QMenu(self)
        
        clear_action = menu.addAction('清空')
        clear_action.triggered.connect(self.serial_log.clear)
        
        menu.addSeparator()
        
        copy_action = menu.addAction('复制')
        copy_action.triggered.connect(self.serial_log.copy)
        copy_action.setEnabled(self.serial_log.textCursor().hasSelection())
        
        select_all_action = menu.addAction('全选')
        select_all_action.triggered.connect(self.serial_log.selectAll)
        
        menu.exec(self.serial_log.mapToGlobal(pos))

    def apply_fonts(self, send_font: QtGui.QFont, recv_font: QtGui.QFont):
        """应用字体"""
        self.operation_log.setFont(recv_font)
        self.serial_log.setFont(recv_font)

    def get_config(self) -> dict:
        """获取配置"""
        flash_data = []
        for row in self.flash_rows:
            flash_data.append({
                'checked': row['checkbox'].isChecked(),
                'addr': row['addr_edit'].text(),
                'bin_path': row['bin_edit'].text()
            })
        
        return {
            'port': self.port_combo.currentData() or self.port_combo.currentText(),
            'baud': self.baud_combo.currentText(),
            'flash_data': flash_data,
            'auto_scroll': self.auto_scroll_cb.isChecked(),
            'auto_reconnect': self.auto_reconnect_cb.isChecked()
        }

    def load_config(self, cfg: dict):
        """加载配置"""
        try:
            last_port = cfg.get('port')
            if last_port:
                for i in range(self.port_combo.count()):
                    if self.port_combo.itemData(i) == last_port:
                        self.port_combo.setCurrentIndex(i)
                        break
            
            self.baud_combo.setCurrentText(str(cfg.get('baud', '115200')))
            
            flash_data = cfg.get('flash_data', [])
            for i, data in enumerate(flash_data):
                if i < len(self.flash_rows):
                    self.flash_rows[i]['checkbox'].setChecked(data.get('checked', False))
                    self.flash_rows[i]['addr_edit'].setText(data.get('addr', ''))
                    self.flash_rows[i]['bin_edit'].setText(data.get('bin_path', ''))
            
            self.auto_scroll_cb.setChecked(cfg.get('auto_scroll', True))
            self.auto_reconnect_cb.setChecked(cfg.get('auto_reconnect', True))
        except Exception:
            pass

    def _setup_usb_monitor(self):
        """设置 USB 设备监听"""
        if WINDOWS_USB_AVAILABLE and sys.platform == 'win32':
            try:
                self.usb_monitor = USBDeviceMonitor(self._on_usb_device_change)
                app = QtCore.QCoreApplication.instance()
                if app:
                    app.installNativeEventFilter(self.usb_monitor)
                    self._log_operation('USB 设备监听已启动', 'blue')
            except Exception as e:
                self._log_operation(f'USB 监听启动失败: {e}', 'orange')
    
    @QtCore.Slot()
    def _on_usb_device_change(self):
        """USB 设备变化回调"""
        if not self.running:
            # 只在串口未打开时自动刷新，并自动选中新设备
            self._log_operation('检测到 USB 设备变化，自动刷新串口列表', 'blue')
            self._refresh_ports(auto_select_new=True)

    def shutdown(self):
        """关闭tab"""
        self._close_serial()
        # 移除 USB 监听器
        if self.usb_monitor:
            try:
                app = QtCore.QCoreApplication.instance()
                if app:
                    app.removeNativeEventFilter(self.usb_monitor)
            except Exception:
                pass

    def _install_autosave_hooks(self):
        """安装自动保存钩子"""
        try:
            self.port_combo.currentIndexChanged.connect(lambda: self.changed.emit())
            self.baud_combo.currentIndexChanged.connect(lambda: self.changed.emit())
            for row in self.flash_rows:
                row['checkbox'].toggled.connect(lambda: self.changed.emit())
                row['addr_edit'].textChanged.connect(lambda: self.changed.emit())
                row['bin_edit'].textChanged.connect(lambda: self.changed.emit())
            self.auto_scroll_cb.toggled.connect(lambda: self.changed.emit())
            self.auto_reconnect_cb.toggled.connect(lambda: self.changed.emit())
        except Exception:
            pass
