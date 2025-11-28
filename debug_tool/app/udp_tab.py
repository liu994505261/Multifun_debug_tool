from PySide6 import QtWidgets, QtCore, QtGui
import socket
import threading

from app.base_comm import BaseCommTab


class UDPCommTabQt(BaseCommTab):
    def __init__(self, get_global_format, parent=None):
        super().__init__(get_global_format, parent)
        self.sock = None
        self.running = False
        self.top_group.setTitle('UDP配置')

        row1 = QtWidgets.QWidget()
        row1_layout = QtWidgets.QHBoxLayout(row1)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(6)
        row1_layout.addWidget(QtWidgets.QLabel('工作模式:'))
        self.mode_client_rb = QtWidgets.QRadioButton('客户端')
        self.mode_server_rb = QtWidgets.QRadioButton('服务端')
        self.mode_client_rb.setChecked(True)
        row1_layout.addWidget(self.mode_client_rb)
        row1_layout.addWidget(self.mode_server_rb)
        self.toggle_btn = QtWidgets.QPushButton('启动')
        row1_layout.addWidget(self.toggle_btn)
        self.status_label = QtWidgets.QLabel('未连接')
        self._set_label_status(self.status_label, 'error')
        row1_layout.addWidget(self.status_label)
        
        # 醒目匹配
        row1_layout.addWidget(QtWidgets.QLabel('醒目:'))
        self.highlight_edit = QtWidgets.QLineEdit()
        self.highlight_edit.setPlaceholderText('匹配内容')
        self.highlight_edit.setMaximumWidth(100)
        row1_layout.addWidget(self.highlight_edit)
        
        row1_layout.addStretch(1)
        self.top_vbox.addWidget(row1)

        row2 = QtWidgets.QWidget()
        row2_layout = QtWidgets.QHBoxLayout(row2)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(6)
        row2_layout.addWidget(QtWidgets.QLabel('本地地址:'))
        self.local_host = QtWidgets.QComboBox()
        self.local_host.setEditable(True)
        self.local_host.setMinimumWidth(140)
        self.local_host.addItem('0.0.0.0')
        self.local_host.setCurrentText('0.0.0.0')
        row2_layout.addWidget(self.local_host)
        row2_layout.addWidget(QtWidgets.QLabel('本地端口:'))
        self.local_port = QtWidgets.QComboBox()
        self.local_port.setEditable(True)
        self.local_port.setFixedWidth(80)
        self.local_port.addItem('8001')
        self.local_port.setCurrentText('8001')
        row2_layout.addWidget(self.local_port)
        self.remote_label1 = QtWidgets.QLabel('远程地址:')
        row2_layout.addWidget(self.remote_label1)
        self.remote_host = QtWidgets.QComboBox()
        self.remote_host.setEditable(True)
        self.remote_host.setMinimumWidth(140)
        self.remote_host.addItem('127.0.0.1')
        self.remote_host.setCurrentText('127.0.0.1')
        row2_layout.addWidget(self.remote_host)
        self.remote_label2 = QtWidgets.QLabel('远程端口:')
        row2_layout.addWidget(self.remote_label2)
        self.remote_port = QtWidgets.QComboBox()
        self.remote_port.setEditable(True)
        self.remote_port.setFixedWidth(80)
        self.remote_port.addItem('8001')
        self.remote_port.setCurrentText('8001')
        row2_layout.addWidget(self.remote_port)
        row2_layout.addStretch(1)
        self.top_vbox.addWidget(row2)

        row3 = QtWidgets.QWidget()
        row3_layout = QtWidgets.QHBoxLayout(row3)
        row3_layout.setContentsMargins(0, 0, 0, 0)
        row3_layout.setSpacing(6)
        self.broadcast_cb = QtWidgets.QCheckBox('广播模式')
        row3_layout.addWidget(self.broadcast_cb)
        self.multicast_cb = QtWidgets.QCheckBox('组播模式')
        row3_layout.addWidget(self.multicast_cb)
        self.multicast_group = QtWidgets.QLineEdit('224.1.1.1')
        self.multicast_group.setEnabled(False)
        self.multicast_group.setFixedWidth(120)
        row3_layout.addWidget(self.multicast_group)
        row3_layout.addStretch(1)
        self.top_vbox.addWidget(row3)

        self.toggle_btn.clicked.connect(self._toggle)
        self.mode_client_rb.toggled.connect(self._update_mode_ui)
        self.mode_server_rb.toggled.connect(self._update_mode_ui)
        self.multicast_cb.toggled.connect(self._on_multicast_change)
        self._update_mode_ui()
        try:
            self.mode_client_rb.toggled.connect(lambda _c: self.changed.emit())
            self.mode_server_rb.toggled.connect(lambda _c: self.changed.emit())
            self.local_host.editTextChanged.connect(lambda _t: self.changed.emit())
            self.local_host.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.local_port.editTextChanged.connect(lambda _t: self.changed.emit())
            self.local_port.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.remote_host.editTextChanged.connect(lambda _t: self.changed.emit())
            self.remote_host.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.remote_port.editTextChanged.connect(lambda _t: self.changed.emit())
            self.remote_port.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.broadcast_cb.toggled.connect(lambda _c: self.changed.emit())
            self.multicast_cb.toggled.connect(lambda _c: self.changed.emit())
            self.multicast_group.textChanged.connect(lambda _t: self.changed.emit())
            self.highlight_edit.textChanged.connect(self._on_highlight_pattern_changed)
            self.highlight_edit.textChanged.connect(lambda _t: self.changed.emit())
        except Exception:
            pass

    def _toggle(self):
        if self.running:
            self._stop()
        else:
            self._start()

    def _current_mode(self) -> str:
        return '客户端' if self.mode_client_rb.isChecked() else '服务端'

    def _start(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            if self._current_mode() == '服务端':
                self.sock.bind((self.local_host.currentText().strip(), int(self.local_port.currentText().strip() or '0')))
                self._log('UDP 服务端已启动', 'blue')
            else:
                self.sock.bind((self.local_host.currentText().strip(), int(self.local_port.currentText().strip() or '0')))
                self._log('UDP 客户端已启动', 'blue')
            self.running = True
            threading.Thread(target=self._recv_loop, daemon=True).start()
            self.toggle_btn.setText('停止')
            self.mode_client_rb.setEnabled(False)
            self.mode_server_rb.setEnabled(False)
            self.local_host.setEnabled(False)
            self.local_port.setEnabled(False)
            self.remote_host.setEnabled(False)
            self.remote_port.setEnabled(False)
            self.status_label.setText('运行中')
            self._set_label_status(self.status_label, 'success')
            try:
                self._add_history(self.local_host, self.local_host.currentText())
                self._add_history(self.local_port, self.local_port.currentText())
                if self._current_mode() == '客户端':
                    self._add_history(self.remote_host, self.remote_host.currentText())
                    self._add_history(self.remote_port, self.remote_port.currentText())
            except Exception:
                pass
        except Exception as e:
            self._log(f'启动失败: {e}', 'red')

    def _stop(self):
        self.running = False
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        self.sock = None
        self._log('UDP 已停止', 'blue')
        self.toggle_btn.setText('启动')
        self.mode_client_rb.setEnabled(True)
        self.mode_server_rb.setEnabled(True)
        self.local_host.setEnabled(True)
        self.local_port.setEnabled(True)
        self.remote_host.setEnabled(True)
        self.remote_port.setEnabled(True)
        self.status_label.setText('未连接')
        self._set_label_status(self.status_label, 'error')

    def _recv_loop(self):
        while self.running and self.sock:
            try:
                data, addr = self.sock.recvfrom(4096)
                self._update_recv_stats(len(data))
                self._log(f'来自 {addr[0]}:{addr[1]}: ' + self._format_recv(data), 'green')
                self.data_received.emit(data)
            except Exception as e:
                if self.running:
                    self._log(f'接收错误: {e}', 'red')
                break

    def _format_recv(self, data: bytes) -> str:
        if self.get_global_format() == 'HEX':
            return ' '.join(f'{b:02X}' for b in data)
        try:
            return data.decode('utf-8', errors='replace')
        except Exception:
            return repr(data)

    def _on_send_clicked(self, idx: int):
        row = self.send_rows[idx]
        fmt = row['fmt_combo'].currentText()
        data = self._parse_send_data(row['data_edit'].text(), fmt)
        if not self.sock:
            self._log('未启动', 'red')
            return
        try:
            addr = (self.remote_host.currentText().strip(), int(self.remote_port.currentText().strip() or '0'))
            self.sock.sendto(data, addr)
            self._log(self._format_by(data, fmt), 'blue')
            self._add_history(self.remote_host, self.remote_host.currentText())
            self._add_history(self.remote_port, self.remote_port.currentText())
        except Exception as e:
            self._log(f'发送失败: {e}', 'red')

    def shutdown(self):
        super().shutdown()
        self._stop()

    def _on_multicast_change(self, checked: bool):
        self.multicast_group.setEnabled(bool(checked))

    def _update_mode_ui(self):
        is_client = self._current_mode() == '客户端'
        self.remote_label1.setVisible(is_client)
        self.remote_label2.setVisible(is_client)
        self.remote_host.setVisible(is_client)
        self.remote_port.setVisible(is_client)

    def _add_history(self, combo: QtWidgets.QComboBox, value: str):
        try:
            value = (value or '').strip()
            if not value:
                return
            existing = [combo.itemText(i) for i in range(combo.count())]
            if value not in existing:
                combo.insertItem(0, value)
            combo.setCurrentText(value)
            if combo.count() > 20:
                for _ in range(combo.count() - 20):
                    combo.removeItem(combo.count() - 1)
        except Exception:
            pass

    def get_config(self) -> dict:
        cfg = super().get_config()
        try:
            cfg.update({
                'mode': self._current_mode(),
                'local_host_history': [self.local_host.itemText(i) for i in range(self.local_host.count())],
                'local_port_history': [self.local_port.itemText(i) for i in range(self.local_port.count())],
                'remote_host_history': [self.remote_host.itemText(i) for i in range(self.remote_host.count())],
                'remote_port_history': [self.remote_port.itemText(i) for i in range(self.remote_port.count())],
                'last_local_host': self.local_host.currentText(),
                'last_local_port': self.local_port.currentText(),
                'last_remote_host': self.remote_host.currentText(),
                'last_remote_port': self.remote_port.currentText(),
                'broadcast': self.broadcast_cb.isChecked(),
                'multicast': self.multicast_cb.isChecked(),
                'multicast_group': self.multicast_group.text()
            })
        except Exception:
            pass
        return cfg

    def load_config(self, cfg: dict):
        super().load_config(cfg)
        try:
            mode = cfg.get('mode', '客户端')
            if mode == '服务端':
                self.mode_server_rb.setChecked(True)
            else:
                self.mode_client_rb.setChecked(True)
            def load_hist(combo: QtWidgets.QComboBox, items, last):
                combo.clear()
                for it in items or []:
                    combo.addItem(str(it))
                if last:
                    combo.setCurrentText(str(last))
            load_hist(self.local_host, cfg.get('local_host_history', []), cfg.get('last_local_host'))
            load_hist(self.local_port, cfg.get('local_port_history', []), cfg.get('last_local_port'))
            load_hist(self.remote_host, cfg.get('remote_host_history', []), cfg.get('last_remote_host'))
            load_hist(self.remote_port, cfg.get('remote_port_history', []), cfg.get('last_remote_port'))
            self.broadcast_cb.setChecked(bool(cfg.get('broadcast', False)))
            self.multicast_cb.setChecked(bool(cfg.get('multicast', False)))
            self.multicast_group.setText(cfg.get('multicast_group', self.multicast_group.text()))
            self._on_multicast_change(self.multicast_cb.isChecked())
            self._update_mode_ui()
        except Exception:
            pass

    def _on_highlight_pattern_changed(self, text):
        self.highlight_pattern = text
