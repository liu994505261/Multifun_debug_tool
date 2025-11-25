from PySide6 import QtWidgets, QtCore, QtGui
import threading

from app.base_comm import BaseCommTab

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except Exception:
    SERIAL_AVAILABLE = False


class SerialDebugTabQt(BaseCommTab):
    def __init__(self, get_global_format, get_serial_blacklist=None, parent=None):
        super().__init__(get_global_format, parent)
        self.ser = None
        self.running = False
        self.get_serial_blacklist = get_serial_blacklist or (lambda: [])
        self.top_group.setTitle('串口配置')

        row1 = QtWidgets.QWidget()
        row1_layout = QtWidgets.QHBoxLayout(row1)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(6)
        row1_layout.addWidget(QtWidgets.QLabel('串口:'))
        self.port_combo = QtWidgets.QComboBox()
        self.port_combo.setMinimumWidth(140)
        row1_layout.addWidget(self.port_combo)
        self.refresh_btn = QtWidgets.QPushButton('刷新')
        row1_layout.addWidget(self.refresh_btn)
        row1_layout.addWidget(QtWidgets.QLabel('波特率:'))
        self.baud_combo = QtWidgets.QComboBox()
        self.baud_combo.addItems(['9600', '19200', '38400', '57600', '115200'])
        row1_layout.addWidget(self.baud_combo)
        row1_layout.addWidget(QtWidgets.QLabel('数据位:'))
        self.databits_combo = QtWidgets.QComboBox()
        self.databits_combo.addItems(['5', '6', '7', '8'])
        self.databits_combo.setCurrentText('8')
        self.databits_combo.setFixedWidth(60)
        row1_layout.addWidget(self.databits_combo)
        row1_layout.addStretch(1)
        self.top_vbox.addWidget(row1)

        row2 = QtWidgets.QWidget()
        row2_layout = QtWidgets.QHBoxLayout(row2)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(6)
        row2_layout.addWidget(QtWidgets.QLabel('校验位:'))
        self.parity_combo = QtWidgets.QComboBox()
        self.parity_combo.addItems(['None', 'Even', 'Odd', 'Mark', 'Space'])
        self.parity_combo.setFixedWidth(100)
        row2_layout.addWidget(self.parity_combo)
        row2_layout.addWidget(QtWidgets.QLabel('停止位:'))
        self.stopbits_combo = QtWidgets.QComboBox()
        self.stopbits_combo.addItems(['1', '1.5', '2'])
        self.stopbits_combo.setFixedWidth(80)
        row2_layout.addWidget(self.stopbits_combo)
        self.toggle_btn = QtWidgets.QPushButton('打开串口')
        row2_layout.addWidget(self.toggle_btn)
        self.status_label = QtWidgets.QLabel('未连接')
        self.status_label.setStyleSheet('color: red;')
        row2_layout.addWidget(self.status_label)
        row2_layout.addStretch(1)
        self.top_vbox.addWidget(row2)

        self.refresh_btn.clicked.connect(self._refresh_ports)
        self.toggle_btn.clicked.connect(self._toggle)
        self._refresh_ports()
        try:
            self.port_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.baud_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.databits_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.parity_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.stopbits_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
        except Exception:
            pass

    def _toggle(self):
        if self.running:
            self._close()
        else:
            self._open()

    def _refresh_ports(self):
        if not SERIAL_AVAILABLE:
            self._log('串口库不可用', 'red')
            return
        try:
            bl = []
            try:
                bl = list(self.get_serial_blacklist() or [])
            except Exception:
                bl = []
            self.port_combo.clear()
            for info in serial.tools.list_ports.comports():
                if info.device in bl:
                    continue
                label = f"{info.device} - {getattr(info, 'description', None) or getattr(info, 'hwid', '')}"
                self.port_combo.addItem(label, info.device)
        except Exception as e:
            self._log(f'刷新失败: {e}', 'red')

    def _open(self):
        if not SERIAL_AVAILABLE:
            self._log('串口库不可用', 'red')
            return
        try:
            port = self.port_combo.currentData() or self.port_combo.currentText()
            baud = int(self.baud_combo.currentText())
            self.ser = serial.Serial(port=port, baudrate=baud, timeout=0.2)
            self.running = True
            threading.Thread(target=self._recv_loop, daemon=True).start()
            self._log(f'串口已打开: {port}@{baud}', 'blue')
            self.toggle_btn.setText('关闭串口')
            self.port_combo.setEnabled(False)
            self.baud_combo.setEnabled(False)
            self.refresh_btn.setEnabled(False)
            self.databits_combo.setEnabled(False)
            self.parity_combo.setEnabled(False)
            self.stopbits_combo.setEnabled(False)
            self.status_label.setText('已打开')
            self.status_label.setStyleSheet('color: green;')
        except Exception as e:
            self._log(f'打开失败: {e}', 'red')

    def _close(self):
        self.running = False
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        self._log('串口已关闭', 'blue')
        self.toggle_btn.setText('打开串口')
        self.port_combo.setEnabled(True)
        self.baud_combo.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.databits_combo.setEnabled(True)
        self.parity_combo.setEnabled(True)
        self.stopbits_combo.setEnabled(True)
        self.status_label.setText('未连接')
        self.status_label.setStyleSheet('color: red;')

    def _recv_loop(self):
        while self.running and self.ser:
            try:
                data = self.ser.read(4096)
                if data:
                    self._update_recv_stats(len(data))
                    self._log(self._format_recv(data), 'green')
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
        if not self.ser:
            self._log('未打开串口', 'red')
            return
        try:
            self.ser.write(data)
            self._log(self._format_by(data, fmt), 'blue')
        except Exception as e:
            self._log(f'发送失败: {e}', 'red')

    def shutdown(self):
        super().shutdown()
        self._close()

    def get_config(self) -> dict:
        cfg = super().get_config()
        try:
            cfg.update({
                'port': self.port_combo.currentData() or self.port_combo.currentText(),
                'baud': self.baud_combo.currentText(),
                'databits': self.databits_combo.currentText(),
                'parity': self.parity_combo.currentText(),
                'stopbits': self.stopbits_combo.currentText()
            })
        except Exception:
            pass
        return cfg

    def load_config(self, cfg: dict):
        super().load_config(cfg)
        try:
            last_port = cfg.get('port')
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
            self.baud_combo.setCurrentText(str(cfg.get('baud', self.baud_combo.currentText())))
            self.databits_combo.setCurrentText(str(cfg.get('databits', self.databits_combo.currentText())))
            self.parity_combo.setCurrentText(str(cfg.get('parity', self.parity_combo.currentText())))
            self.stopbits_combo.setCurrentText(str(cfg.get('stopbits', self.stopbits_combo.currentText())))
        except Exception:
            pass
