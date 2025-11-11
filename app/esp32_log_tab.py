import serial
import serial.tools.list_ports
import threading
import time
from PySide6 import QtWidgets, QtCore, QtGui

from app.base_comm import BaseCommTab


class ESP32LogTab(BaseCommTab):
    log_batch_received = QtCore.Signal(list)

    def __init__(self, get_global_format, parent=None):
        super().__init__(get_global_format, parent)
        self.serial = None
        self.read_thread = None
        self.running = False

        # 串口配置
        self.top_group.setTitle('ESP32 日志')
        row1 = QtWidgets.QWidget()
        row1_layout = QtWidgets.QHBoxLayout(row1)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(6)
        row1_layout.addWidget(QtWidgets.QLabel('串口号:'))
        self.port_combo = QtWidgets.QComboBox()
        row1_layout.addWidget(self.port_combo)
        self.refresh_btn = QtWidgets.QPushButton('刷新')
        row1_layout.addWidget(self.refresh_btn)
        self.toggle_btn = QtWidgets.QPushButton('打开')
        row1_layout.addWidget(self.toggle_btn)
        row1_layout.addStretch(1)
        self.top_vbox.addWidget(row1)

        # 隐藏发送区
        self.splitter.widget(0).setVisible(False)

        # 事件绑定
        self.refresh_btn.clicked.connect(self._refresh_ports)
        self.toggle_btn.clicked.connect(self._toggle)

        self.log_batch_received.connect(self._update_log_from_batch)

        self._refresh_ports()
        self._install_autosave_hooks()

    def _install_autosave_hooks(self):
        super()._install_autosave_hooks()
        self.port_combo.currentTextChanged.connect(lambda: self.changed.emit())

    def load_config(self, cfg: dict):
        super().load_config(cfg)
        self.port_combo.setCurrentText(cfg.get('port', ''))

    def get_config(self) -> dict:
        cfg = super().get_config()
        cfg.update({
            'port': self.port_combo.currentText(),
        })
        return cfg

    def _toggle(self):
        if self.serial is not None and self.serial.is_open:
            self._stop_read_thread()
            self.toggle_btn.setText('打开')
            self.port_combo.setEnabled(True)
            return

        port = self.port_combo.currentText()
        if not port:
            return

        try:
            self.serial = serial.Serial(port, 115200, timeout=0.1)
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

    def _start_read_thread(self):
        self.read_thread = threading.Thread(target=self._read_serial, daemon=True)
        self.running = True
        self.read_thread.start()

    def _update_log_from_batch(self, log_batch: list):
        for text, color in log_batch:
            self._log(text, color)

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
                        if text.startswith('E ('):
                            color = 'red'
                        elif text.startswith('W ('):
                            color = 'orange'
                        elif text.startswith('I ('):
                            color = 'green'
                        elif text.startswith('D ('):
                            color = 'blue'
                        elif text.startswith('V ('):
                            color = 'purple'

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
        current_port = self.port_combo.currentText()
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)
        
        if current_port and self.port_combo.findText(current_port) != -1:
            self.port_combo.setCurrentText(current_port)

    def shutdown(self):
        super().shutdown()
        self._stop_read_thread()

