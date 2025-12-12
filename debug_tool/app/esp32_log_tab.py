import serial
import serial.tools.list_ports
import threading
import time
import os
from datetime import datetime
from PySide6 import QtWidgets, QtCore, QtGui

from app.base_comm import BaseCommTab

class LogSearchHighlighter(QtGui.QSyntaxHighlighter):
    def __init__(self, document, base_size=10):
        super().__init__(document)
        self.query = None
        self.active_range = None
        try:
            self.base_size = int(base_size or 10)
        except Exception:
            self.base_size = 10

    def set_base_size(self, size):
        try:
            self.base_size = int(size or 10)
        except Exception:
            self.base_size = 10
        self.rehighlight()

    def set_query(self, query):
        self.query = (query or None)
        self.active_range = None
        self.rehighlight()

    def set_active_range(self, start, end):
        self.active_range = (int(start), int(end))
        self.rehighlight()

    def highlightBlock(self, text):
        if not self.query:
            return
        q = self.query
        # 所有匹配项：红色背景，绿色前景，加粗，字号+3
        fmt = QtGui.QTextCharFormat()
        try:
            fmt.setFontWeight(QtGui.QFont.Weight.Bold)
        except Exception:
            fmt.setFontWeight(75)
        fmt.setFontPointSize(self.base_size + 3)
        fmt.setForeground(QtGui.QBrush(QtGui.QColor(43, 174, 133)))
        fmt.setBackground(QtGui.QBrush(QtGui.QColor(249, 193, 22)))

        start_index = 0
        while True:
            i = text.find(q, start_index)
            if i == -1:
                break
            self.setFormat(i, len(q), fmt)
            start_index = i + len(q)

        # 当前点击项叠加：加下划线与更深红色背景
        if self.active_range:
            block_pos = self.currentBlock().position()
            s, e = self.active_range
            os = max(block_pos, s)
            oe = min(block_pos + len(text), e)
            if oe > os:
                i = os - block_pos
                l = oe - os
                a_fmt = QtGui.QTextCharFormat()
                try:
                    a_fmt.setFontWeight(QtGui.QFont.Weight.Bold)
                except Exception:
                    a_fmt.setFontWeight(75)
                a_fmt.setFontPointSize(self.base_size + 3)
                a_fmt.setForeground(QtGui.QBrush(QtGui.QColor(0, 255, 0)))
                a_fmt.setBackground(QtGui.QBrush(QtGui.QColor(255, 64, 64)))
                a_fmt.setFontUnderline(True)
                self.setFormat(i, l, a_fmt)

class ESP32LogTab(BaseCommTab):
    log_batch_received = QtCore.Signal(list)

    def __init__(self, get_global_format, get_serial_blacklist=None, parent=None):
        super().__init__(get_global_format, parent)
        self.serial = None
        self.read_thread = None
        self.running = False
        self.get_serial_blacklist = get_serial_blacklist or (lambda: [])
        
        # 保存功能相关变量
        self.is_saving = False
        self.save_file = None
        self.save_filepath = None

        # 串口配置
        self.top_group.setTitle('ESP32 日志')
        row1 = QtWidgets.QWidget()
        row1_layout = QtWidgets.QHBoxLayout(row1)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(6)
        row1_layout.addWidget(QtWidgets.QLabel('串口号:'))
        self.port_combo = QtWidgets.QComboBox()
        row1_layout.addWidget(self.port_combo)

        row1_layout.addWidget(QtWidgets.QLabel('波特率:'))
        self.baud_combo = QtWidgets.QComboBox()
        self.baud_combo.setEditable(True)
        self.baud_combo.addItems(['9600', '19200', '38400', '57600', '115200', '921600','1000000'])
        self.baud_combo.setCurrentText('115200')
        # 设置波特率下拉框的最小宽度c
        self.baud_combo.setMinimumWidth(120)
        row1_layout.addWidget(self.baud_combo)

        self.refresh_btn = QtWidgets.QPushButton('刷新')
        row1_layout.addWidget(self.refresh_btn)

        # 打开/关闭按钮保留在后面
        self.toggle_btn = QtWidgets.QPushButton('打开')
        row1_layout.addWidget(self.toggle_btn)
        
        # 添加保存按钮
        self.save_btn = QtWidgets.QPushButton('开始保存')
        self.save_btn.setToolTip('开始实时保存串口接收数据到txt文件')
        row1_layout.addWidget(self.save_btn)
        
        row1_layout.addStretch(1)
        self.top_vbox.addWidget(row1)
        
        # 将查找控件移动到“刷新”右侧
        row1_layout.addWidget(QtWidgets.QLabel('查找:'))
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText('在日志中查找关键字')
        self.search_edit.setMinimumWidth(180)
        row1_layout.addWidget(self.search_edit)
        self.search_btn = QtWidgets.QPushButton('查找')
        row1_layout.addWidget(self.search_btn)

        # 日志级别控制
        row2 = QtWidgets.QWidget()
        row2_layout = QtWidgets.QHBoxLayout(row2)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(6)
        row2_layout.addWidget(QtWidgets.QLabel('日志级别:'))
        self.log_level_checks = {}
        for level in ['Error', 'Warning', 'Info', 'Debug', 'Verbose']:
            checkbox = QtWidgets.QCheckBox(level)
            checkbox.setChecked(True)
            self.log_level_checks[level] = checkbox
            row2_layout.addWidget(checkbox)
        row2_layout.addStretch(1)
        self.top_vbox.addWidget(row2)

        # 查找功能已移至第一行

        # 隐藏发送区
        self.splitter.widget(0).setVisible(False)

        # 重构接收区：在右侧分割出查找结果面板
        try:
            right_group = self.recv_text.parentWidget()
            right_layout = right_group.layout()
            if right_layout:
                right_layout.removeWidget(self.recv_text)
                self.right_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
                self.right_splitter.setChildrenCollapsible(False)
                self.right_splitter.addWidget(self.recv_text)

                self.search_result_panel = QtWidgets.QWidget()
                sr_layout = QtWidgets.QVBoxLayout(self.search_result_panel)
                sr_layout.setContentsMargins(8, 8, 8, 8)
                sr_layout.setSpacing(6)
                self.search_result_label = QtWidgets.QLabel('查找结果')
                sr_layout.addWidget(self.search_result_label)
                self.search_result_list = QtWidgets.QListWidget()
                sr_layout.addWidget(self.search_result_list, 1)

                self.right_splitter.addWidget(self.search_result_panel)
                right_layout.insertWidget(0, self.right_splitter)
                # 初始隐藏查找结果面板
                self.search_result_panel.setVisible(False)

                # 列表点击跳转
                self.search_result_list.itemActivated.connect(self._jump_from_item)
                self.search_result_list.itemClicked.connect(self._jump_from_item)
        except Exception:
            pass

        # 事件绑定
        self.refresh_btn.clicked.connect(self._refresh_ports)
        self.toggle_btn.clicked.connect(self._toggle)
        self.search_btn.clicked.connect(self._search_logs)
        self.save_btn.clicked.connect(self._save_logs)

        self.log_batch_received.connect(self._update_log_from_batch)
        
        # 为接收区域设置右键菜单
        self.recv_text.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.recv_text.customContextMenuRequested.connect(self._show_recv_context_menu)

        self._refresh_ports()
        self._install_autosave_hooks()
        # 搜索高亮器
        try:
            base_size = self.recv_text.font().pointSize() or 10
        except Exception:
            base_size = 10
        self._highlighter = LogSearchHighlighter(self.recv_text.document(), base_size=base_size)
        # 清空时移除高亮
        try:
            self.clear_recv_btn.clicked.connect(self._clear_search_highlight)
        except Exception:
            pass

    def _install_autosave_hooks(self):
        super()._install_autosave_hooks()
        self.port_combo.currentTextChanged.connect(lambda: self.changed.emit())
        self.baud_combo.currentTextChanged.connect(lambda: self.changed.emit())
        for checkbox in self.log_level_checks.values():
            checkbox.stateChanged.connect(lambda: self.changed.emit())
        try:
            self.search_edit.textChanged.connect(lambda: self.changed.emit())
        except Exception:
            pass

    def load_config(self, cfg: dict):
        super().load_config(cfg)
        try:
            last_port = cfg.get('port', '')
            if last_port:
                matched = False
                for i in range(self.port_combo.count()):
                    if self.port_combo.itemData(i) == last_port:
                        self.port_combo.setCurrentIndex(i)
                        matched = True
                        break
                if not matched:
                    self.port_combo.insertItem(0, str(last_port), str(last_port))
                    self.port_combo.setCurrentIndex(0)
        except Exception:
            pass
        self.baud_combo.setCurrentText(cfg.get('baudrate', '115200'))
        log_levels = cfg.get('log_levels', {})
        for level, checkbox in self.log_level_checks.items():
            checkbox.setChecked(log_levels.get(level, True))

    def get_config(self) -> dict:
        cfg = super().get_config()
        cfg.update({
            'port': self.port_combo.currentData() or self.port_combo.currentText(),
            'baudrate': self.baud_combo.currentText(),
            'log_levels': {level: checkbox.isChecked() for level, checkbox in self.log_level_checks.items()},
        })
        return cfg

    def _toggle(self):
        if self.serial is not None and self.serial.is_open:
            self._stop_read_thread()
            self.toggle_btn.setText('打开')
            self.port_combo.setEnabled(True)
            self.baud_combo.setEnabled(True)
            return

        port = self.port_combo.currentData() or self.port_combo.currentText()
        if not port:
            return

        try:
            baudrate = int(self.baud_combo.currentText())
        except ValueError:
            self._log('[ERROR] 无效的波特率', 'red')
            return

        try:
            self.serial = serial.Serial(port, baudrate, timeout=0.1)
            # DTR/RTS 信号触发 ESP32 复位进入下载模式
            self.serial.dtr = True
            self.serial.rts = True
            time.sleep(0.5)
            self.serial.dtr = False
            self.serial.rts = False
        except serial.SerialException as e:
            self._log(f'[ERROR] {e}', 'red')
            return

        self._start_read_thread()
        self.toggle_btn.setText('关闭')
        self.port_combo.setEnabled(False)
        self.baud_combo.setEnabled(False)

    def _start_read_thread(self):
        self.read_thread = threading.Thread(target=self._read_serial, daemon=True)
        self.running = True
        self.read_thread.start()

    def _update_log_from_batch(self, log_batch: list):
        for text, color in log_batch:
            self._log(text, color)
            # 如果正在保存，将数据写入文件
            if self.is_saving and self.save_file:
                try:
                    self.save_file.write(f'{text}\n')
                    self.save_file.flush()  # 立即写入磁盘
                except Exception as e:
                    self._log(f'[ERROR] 写入保存文件失败: {str(e)}', 'red')
                    self._stop_saving()  # 出错时停止保存

    def _search_logs(self):
        # 获取查询关键字
        query = (self.search_edit.text() or '').strip()
        if not query:
            text, ok = QtWidgets.QInputDialog.getText(self, '查找', '关键字:')
            if not ok:
                return
            query = (text or '').strip()
            if not query:
                return

        doc = self.recv_text.document()
        pos = 0
        results = []
        # 收集所有匹配项
        while True:
            cursor = doc.find(query, pos)
            if not cursor or cursor.isNull():
                break
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            block = cursor.block()
            line_no = block.blockNumber() + 1
            line_text = block.text()
            results.append({'start': start, 'end': end, 'line': line_no, 'line_text': line_text})
            pos = end

        if not results:
            QtWidgets.QMessageBox.information(self, '查找', '未找到匹配项')
            return

        # 应用高亮（红底绿字，字号+3）
        self._apply_search_highlight(query)

        self._show_search_results_dialog(query, results)

    def _show_search_results_dialog(self, query: str, results: list):
        # 使用接收区右侧面板展示查找结果（分割显示）
        try:
            self.search_result_label.setText(f"查找结果: {query} ({len(results)}项)")
            self.search_result_list.clear()
            for r in results:
                preview = r['line_text']
                if len(preview) > 200:
                    preview = preview[:200] + '…'
                item = QtWidgets.QListWidgetItem(f"第{r['line']}行: {preview}")
                item.setData(QtCore.Qt.ItemDataRole.UserRole, (r['start'], r['end']))
                self.search_result_list.addItem(item)

            # 显示查找结果面板
            if hasattr(self, 'search_result_panel'):
                self.search_result_panel.setVisible(True)
            
            # 展示右侧面板宽度（约 30% 或至少 280px）
            sizes = self.right_splitter.sizes() if hasattr(self, 'right_splitter') else []
            total = sum(sizes) or 1000
            right = min(400, max(280, int(total * 0.3)))
            left = max(10, total - right)
            if hasattr(self, 'right_splitter'):
                self.right_splitter.setSizes([left, right])
            self.search_result_list.setFocus()
        except Exception:
            pass

    def _jump_to_result(self, start_pos: int, end_pos: int):
        cursor = self.recv_text.textCursor()
        # 仅定位光标，避免系统选中样式覆盖自定义高亮
        cursor.setPosition(int(start_pos), QtGui.QTextCursor.MoveMode.MoveAnchor)
        self.recv_text.setTextCursor(cursor)
        self.recv_text.ensureCursorVisible()

        # 强化当前匹配项的高亮（叠加背景以便更醒目）
        self._highlight_active_result(int(start_pos), int(end_pos))

    def _jump_from_item(self, item: QtWidgets.QListWidgetItem):
        data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if data:
            start, end = data
            self._jump_to_result(start, end)

    def _apply_search_highlight(self, query: str):
        base_size = self.recv_text.font().pointSize()
        if not base_size or base_size <= 0:
            base_size = 10
        if not getattr(self, '_highlighter', None):
            self._highlighter = LogSearchHighlighter(self.recv_text.document(), base_size=base_size)
        else:
            self._highlighter.set_base_size(base_size)
        self._highlighter.set_query(query)
        try:
            # 移除可能存在的旧 ExtraSelections
            self.recv_text.setExtraSelections([])
        except Exception:
            pass

    def _highlight_active_result(self, start_pos: int, end_pos: int):
        if getattr(self, '_highlighter', None):
            self._highlighter.set_active_range(int(start_pos), int(end_pos))

    def _clear_search_highlight(self):
        try:
            if getattr(self, '_highlighter', None):
                self._highlighter.set_query(None)
        except Exception:
            pass
        try:
            self.recv_text.setExtraSelections([])
            # 隐藏查找结果面板
            self._hide_search_panel()
        except Exception:
            pass

    def _read_serial(self):
        log_batch = []
        while self.running:
            try:
                line = self.serial.readline()
                if line:
                    self._update_recv_stats(len(line))
                    try:
                        text = line.decode('utf-8', errors='ignore').strip()
                        if not text:
                            continue

                        color = 'black'
                        level = None
                        if text.startswith('E ('):
                            color = 'red'
                            level = 'Error'
                        elif text.startswith('W ('):
                            color = 'orange'
                            level = 'Warning'
                        elif text.startswith('I ('):
                            color = 'green'
                            level = 'Info'
                        elif text.startswith('D ('):
                            color = 'blue'
                            level = 'Debug'
                        elif text.startswith('V ('):
                            color = 'purple'
                            level = 'Verbose'

                        if level and not self.log_level_checks[level].isChecked():
                            continue

                        log_batch.append((text, color))
                    except UnicodeDecodeError:
                        pass

                if not line or len(log_batch) >= 50:
                    if log_batch:
                        self.log_batch_received.emit(log_batch)
                        log_batch = []
            except serial.SerialException:
                self._log('[ERROR] 串口断开', 'red')
                self.running = False
                break

        if log_batch:
            self.log_batch_received.emit(log_batch)

    def _stop_read_thread(self):
        self.running = False
        if self.read_thread:
            self.read_thread.join(timeout=1)
            self.read_thread = None
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.serial = None

    def _refresh_ports(self):
        current_port = self.port_combo.currentData() or self.port_combo.currentText()
        self.port_combo.clear()
        bl = []
        try:
            bl = list(self.get_serial_blacklist() or [])
        except Exception:
            bl = []
        ports = serial.tools.list_ports.comports()
        for info in ports:
            if info.device in bl:
                continue
            label = f"{info.device} - {getattr(info, 'description', None) or getattr(info, 'hwid', '')}"
            self.port_combo.addItem(label, info.device)
        
        if current_port:
            for i in range(self.port_combo.count()):
                if self.port_combo.itemData(i) == current_port:
                    self.port_combo.setCurrentIndex(i)
                    break

    def _show_recv_context_menu(self, pos):
        """显示接收区域的右键菜单"""
        menu = QtWidgets.QMenu(self.recv_text)
        
        # 清空内容选项
        clear_action = menu.addAction('清空内容')
        clear_action.triggered.connect(self._clear_recv_content)
        
        # 关闭查找结果框选项（仅在查找结果面板可见时显示）
        if self._is_search_panel_visible():
            menu.addSeparator()
            close_search_action = menu.addAction('关闭查找结果框')
            close_search_action.triggered.connect(self._hide_search_panel)
        
        # 在鼠标位置显示菜单
        menu.exec(self.recv_text.mapToGlobal(pos))
    
    def _clear_recv_content(self):
        """清空接收区域的内容"""
        self.recv_text.clear()
        # 同时清除搜索高亮
        self._clear_search_highlight()
    
    def _is_search_panel_visible(self):
        """检查查找结果面板是否可见"""
        if not hasattr(self, 'search_result_panel'):
            return False
        return self.search_result_panel.isVisible()
    
    def _hide_search_panel(self):
        """隐藏查找结果面板"""
        if hasattr(self, 'search_result_panel'):
            self.search_result_panel.setVisible(False)
        # 清空查找结果
        if hasattr(self, 'search_result_list'):
            self.search_result_list.clear()
        if hasattr(self, 'search_result_label'):
            self.search_result_label.setText('查找结果')

    def _save_logs(self):
        """开始/停止实时保存串口数据"""
        if not self.is_saving:
            # 开始保存
            self._start_saving()
        else:
            # 停止保存
            self._stop_saving()
    
    def _start_saving(self):
        """开始实时保存"""
        # 让用户选择保存目录
        save_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self, 
            '选择保存目录', 
            os.path.expanduser('~')  # 默认为用户主目录
        )
        
        if not save_dir:
            return  # 用户取消了选择
        
        # 生成文件名：ESP32_Log_YYYYMMDD_HHMMSS.txt
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'ESP32_Log_{timestamp}.txt'
        self.save_filepath = os.path.join(save_dir, filename)
        
        try:
            # 打开文件用于写入
            self.save_file = open(self.save_filepath, 'w', encoding='utf-8')
            
            # 写入文件头信息
            self.save_file.write(f'ESP32 日志文件\n')
            self.save_file.write(f'开始保存时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            self.save_file.write(f'串口: {self.port_combo.currentText()}\n')
            self.save_file.write(f'波特率: {self.baud_combo.currentText()}\n')
            self.save_file.write('=' * 50 + '\n\n')
            self.save_file.flush()  # 立即写入磁盘
            
            # 更新状态
            self.is_saving = True
            self.save_btn.setText('停止保存')
            self.save_btn.setToolTip('停止保存串口数据')
            
            # 在接收区域显示保存开始信息
            self._log(f'[INFO] 开始保存日志至: {self.save_filepath}', 'green')
            
        except Exception as e:
            # 显示错误消息
            error_msg = f'开始保存失败: {str(e)}'
            self._log(f'[ERROR] {error_msg}', 'red')
            QtWidgets.QMessageBox.critical(self, '保存失败', error_msg)
    
    def _stop_saving(self):
        """停止实时保存"""
        if self.save_file:
            try:
                # 写入结束信息
                self.save_file.write(f'\n\n结束保存时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
                self.save_file.close()
                self.save_file = None
                
                # 在接收区域显示保存完成信息
                self._log(f'[INFO] 日志保存完成: {self.save_filepath}', 'green')
                
                # 显示成功消息
                QtWidgets.QMessageBox.information(
                    self, 
                    '保存完成', 
                    f'日志已成功保存至:\n{self.save_filepath}'
                )
                
            except Exception as e:
                error_msg = f'停止保存失败: {str(e)}'
                self._log(f'[ERROR] {error_msg}', 'red')
        
        # 更新状态
        self.is_saving = False
        self.save_btn.setText('开始保存')
        self.save_btn.setToolTip('开始实时保存串口接收数据到txt文件')
        self.save_filepath = None

    def shutdown(self):
        super().shutdown()
        self._stop_read_thread()
        # 确保保存文件正确关闭
        if self.is_saving:
            self._stop_saving()
