import time
from PySide6 import QtWidgets, QtCore, QtGui


class BaseCommTab(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self, get_global_format, parent=None):
        super().__init__(parent)
        self.get_global_format = get_global_format
        self.max_recv_lines = 2000
        self._build_base_ui()

    def _build_base_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.top_group = QtWidgets.QGroupBox()
        self.top_group.setTitle('配置')
        self.top_group.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self.top_vbox = QtWidgets.QVBoxLayout(self.top_group)
        self.top_vbox.setContentsMargins(6, 6, 6, 6)
        self.top_vbox.setSpacing(4)
        layout.addWidget(self.top_group)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        left_group = QtWidgets.QGroupBox('发送')
        left_group_layout = QtWidgets.QVBoxLayout(left_group)
        left_group_layout.setContentsMargins(8, 8, 8, 8)
        left_group_layout.setSpacing(4)
        self.send_rows = []
        for i in range(5):
            item = QtWidgets.QWidget()
            item_vbox = QtWidgets.QVBoxLayout(item)
            item_vbox.setContentsMargins(4, 4, 4, 4)
            item_vbox.setSpacing(4)

            row1 = QtWidgets.QWidget()
            row1_layout = QtWidgets.QHBoxLayout(row1)
            row1_layout.setContentsMargins(0, 0, 0, 0)
            row1_layout.setSpacing(6)
            label = QtWidgets.QLabel(f'[{i+1}] 数据')
            data_edit = QtWidgets.QLineEdit()
            data_edit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            row1_layout.addWidget(label)
            row1_layout.addWidget(data_edit, 1)
            item_vbox.addWidget(row1)

            row2 = QtWidgets.QWidget()
            row2_layout = QtWidgets.QHBoxLayout(row2)
            row2_layout.setContentsMargins(0, 0, 0, 0)
            row2_layout.setSpacing(6)
            interval_label = QtWidgets.QLabel('时间间隔')
            interval_edit = QtWidgets.QLineEdit()
            interval_edit.setFixedWidth(70)
            ms_label = QtWidgets.QLabel('ms')
            auto_cb = QtWidgets.QCheckBox('自动发送')
            send_btn = QtWidgets.QPushButton('发送')
            auto_cb.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            send_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            send_btn.setFixedWidth(64)
            row2_layout.addWidget(interval_label)
            row2_layout.addWidget(interval_edit)
            row2_layout.addWidget(ms_label)
            row2_layout.addWidget(auto_cb)
            row2_layout.addWidget(send_btn)
            row2_layout.addStretch(1)
            item_vbox.addWidget(row2)

            left_group_layout.addWidget(item)

            timer = QtCore.QTimer(self)
            timer.setSingleShot(False)
            timer.timeout.connect(lambda checked=False, idx=i: self._on_send_clicked(idx))
            auto_cb.toggled.connect(lambda checked, idx=i, t=timer, e=interval_edit: self._toggle_auto(idx, t, e, checked))
            send_btn.clicked.connect(lambda checked=False, idx=i: self._on_send_clicked(idx))
            self.send_rows.append({
                'data_edit': data_edit,
                'interval_edit': interval_edit,
                'auto_cb': auto_cb,
                'send_btn': send_btn,
                'timer': timer
            })

        right_group = QtWidgets.QGroupBox('接收')
        right_group_layout = QtWidgets.QVBoxLayout(right_group)
        right_group_layout.setContentsMargins(8, 8, 8, 8)
        right_group_layout.setSpacing(6)

        self.recv_text = QtWidgets.QTextEdit()
        self.recv_text.setReadOnly(True)
        right_group_layout.addWidget(self.recv_text)

        stats_bar = QtWidgets.QHBoxLayout()
        stats_bar.setContentsMargins(0, 0, 0, 0)
        stats_bar.setSpacing(8)
        self.clear_recv_btn = QtWidgets.QPushButton('清空')
        stats_bar.addWidget(self.clear_recv_btn)
        stats_bar.addSpacing(10)
        stats_bar.addWidget(QtWidgets.QLabel('行数:'))
        self.lines_value = QtWidgets.QLabel('0')
        stats_bar.addWidget(self.lines_value)
        stats_bar.addSpacing(10)
        stats_bar.addWidget(QtWidgets.QLabel('大小:'))
        self.bytes_value = QtWidgets.QLabel('0/10KB')
        stats_bar.addWidget(self.bytes_value)
        stats_bar.addSpacing(10)
        stats_bar.addWidget(QtWidgets.QLabel('总计:'))
        self.total_value = QtWidgets.QLabel('0B')
        stats_bar.addWidget(self.total_value)
        stats_bar.addSpacing(10)
        stats_bar.addWidget(QtWidgets.QLabel('速率:'))
        self.speed_value = QtWidgets.QLabel('0B/s')
        stats_bar.addWidget(self.speed_value)
        stats_bar.addStretch(1)
        self.auto_scroll_cb = QtWidgets.QCheckBox('自动滚动')
        self.auto_scroll_cb.setChecked(True)
        self.timestamp_cb = QtWidgets.QCheckBox('显示时间戳')
        stats_bar.addWidget(self.auto_scroll_cb)
        stats_bar.addWidget(self.timestamp_cb)
        right_group_layout.addLayout(stats_bar)
        self.clear_recv_btn.clicked.connect(self._clear_recv)

        self.splitter.addWidget(left_group)
        self.splitter.addWidget(right_group)
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter)
        layout.setStretch(0, 0)
        layout.setStretch(1, 1)

        self.total_recv_bytes = 0
        self.current_recv_bytes = 0
        self.max_recv_bytes = 10 * 1024
        self._prev_total_bytes = 0
        self._speed_timer = QtCore.QTimer(self)
        self._speed_timer.setInterval(1000)
        self._speed_timer.timeout.connect(self._update_speed)
        self._speed_timer.start()

        QtCore.QTimer.singleShot(100, lambda: self.splitter.setSizes([700, 500]))

    def _install_autosave_hooks(self):
        try:
            for row in self.send_rows:
                row['data_edit'].textChanged.connect(lambda _t=None: self.changed.emit())
                row['interval_edit'].textChanged.connect(lambda _t=None: self.changed.emit())
                row['auto_cb'].toggled.connect(lambda _checked: self.changed.emit())
            self.auto_scroll_cb.toggled.connect(lambda _c: self.changed.emit())
            self.timestamp_cb.toggled.connect(lambda _c: self.changed.emit())
            self.splitter.splitterMoved.connect(lambda _pos, _idx: self.changed.emit())
        except Exception:
            pass

    def apply_fonts(self, send_font: QtGui.QFont, recv_font: QtGui.QFont):
        for row in self.send_rows:
            row['data_edit'].setFont(send_font)
        self.recv_text.setFont(recv_font)

    def _log(self, text: str, color: str = 'black'):
        if getattr(self, 'pause_recv', False):
            return
        cursor = self.recv_text.textCursor()
        fmt = QtGui.QTextCharFormat()
        fmt.setForeground(QtGui.QBrush(QtGui.QColor(color)))
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        cursor.setCharFormat(fmt)
        if getattr(self, 'timestamp_cb', None) and self.timestamp_cb.isChecked():
            ts = time.time()
            tm = time.localtime(ts)
            prefix = f"[{time.strftime('%H:%M:%S', tm)}.{int((ts % 1)*1000):03d}] "
            cursor.insertText(prefix + text + '\n')
        else:
            cursor.insertText(text + '\n')
        if self.auto_scroll_cb.isChecked():
            self.recv_text.moveCursor(QtGui.QTextCursor.MoveOperation.End)
        if self.recv_text.document().blockCount() > self.max_recv_lines:
            self.recv_text.clear()
            self.current_recv_bytes = 0
        try:
            self.lines_value.setText(f"{self.recv_text.document().blockCount()}/{self.max_recv_lines}")
        except Exception:
            pass

    def _parse_send_data(self, s: str) -> bytes:
        fmt = self.get_global_format()
        if fmt == 'HEX':
            hexstr = (s or '').replace(' ', '').replace('\n', '').replace('\r', '')
            return bytes.fromhex(hexstr) if hexstr else b''
        return (s or '').encode('utf-8')

    def _toggle_auto(self, idx: int, timer: QtCore.QTimer, interval_edit: QtWidgets.QLineEdit, checked: bool):
        if checked:
            try:
                ms = int(interval_edit.text() or '1000')
            except Exception:
                ms = 1000
            timer.start(ms)
        else:
            timer.stop()

    def _update_recv_stats(self, byte_count: int):
        try:
            self.current_recv_bytes += int(byte_count or 0)
            self.total_recv_bytes += int(byte_count or 0)
            cur = self._format_size(self.current_recv_bytes)
            maxs = self._format_size(self.max_recv_bytes)
            self.bytes_value.setText(f"{cur}/{maxs}")
            self.total_value.setText(self._format_size(self.total_recv_bytes))
        except Exception:
            pass

    def _format_size(self, n: int) -> str:
        try:
            n = int(n)
        except Exception:
            return '0B'
        if n < 1024:
            return f"{n}B"
        elif n < 1024 * 1024:
            return f"{n/1024:.0f}KB"
        else:
            return f"{n/1024/1024:.1f}MB"

    def _update_speed(self):
        try:
            delta = self.total_recv_bytes - self._prev_total_bytes
            self._prev_total_bytes = self.total_recv_bytes
            self.speed_value.setText(f"{self._format_size(delta)}/s")
        except Exception:
            pass

    def _clear_recv(self):
        self.recv_text.clear()
        self.current_recv_bytes = 0
        self.lines_value.setText(f"0/{self.max_recv_lines}")
        self.bytes_value.setText(f"0/{self._format_size(self.max_recv_bytes)}")

    def _on_send_clicked(self, idx: int):
        pass

    def get_config(self) -> dict:
        sizes = self.splitter.sizes()
        ratio = None
        if sizes and sum(sizes) > 0:
            ratio = max(0.05, min(0.95, sizes[0] / float(sum(sizes))))
        send_data = []
        for row in self.send_rows:
            send_data.append({
                'data': row['data_edit'].text(),
                'interval': row['interval_edit'].text(),
                'auto_send': row['auto_cb'].isChecked(),
                'format': self.get_global_format()
            })
        return {
            'send_data': send_data,
            'pane_ratio': ratio,
            'show_timestamp': bool(getattr(self, 'timestamp_cb', None) and self.timestamp_cb.isChecked())
        }

    def load_config(self, cfg: dict):
        try:
            ratio = cfg.get('pane_ratio')
            if ratio:
                def apply_ratio():
                    total = sum(self.splitter.sizes()) or 100
                    left = int(total * float(ratio))
                    right = max(10, total - left)
                    self.splitter.setSizes([left, right])
                QtCore.QTimer.singleShot(200, apply_ratio)
            send_data = cfg.get('send_data', [])
            for i, data in enumerate(send_data):
                if i < len(self.send_rows):
                    self.send_rows[i]['data_edit'].setText(data.get('data', ''))
                    self.send_rows[i]['interval_edit'].setText(str(data.get('interval', '')))
                    self.send_rows[i]['auto_cb'].setChecked(bool(data.get('auto_send', False)))
            try:
                self.timestamp_cb.setChecked(bool(cfg.get('show_timestamp', False)))
            except Exception:
                pass
        except Exception:
            pass

    def shutdown(self):
        for row in self.send_rows:
            try:
                row['timer'].stop()
            except Exception:
                pass