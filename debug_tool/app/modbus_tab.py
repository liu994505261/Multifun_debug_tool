from PySide6 import QtWidgets, QtCore, QtGui
import threading

from app.base_comm import BaseCommTab
from app.crc_utils import crc16_modbus

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except Exception:
    SERIAL_AVAILABLE = False


class ModbusTab(BaseCommTab):
    def __init__(self, get_global_format, get_serial_blacklist=None, parent=None):
        super().__init__(get_global_format, parent)
        self.ser = None
        self.running = False
        self.get_serial_blacklist = get_serial_blacklist or (lambda: [])
        self.top_group.setTitle('Modbus (RTU) 配置')

        # Row 1: Port Settings
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
        row1_layout.addStretch(1)
        self.top_vbox.addWidget(row1)

        # Row 2: Controls
        row2 = QtWidgets.QWidget()
        row2_layout = QtWidgets.QHBoxLayout(row2)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(6)
        self.toggle_btn = QtWidgets.QPushButton('打开串口')
        row2_layout.addWidget(self.toggle_btn)
        self.status_label = QtWidgets.QLabel('未连接')
        self._set_label_status(self.status_label, 'error')
        row2_layout.addWidget(self.status_label)
        
        self.auto_crc_cb = QtWidgets.QCheckBox('自动附加CRC-16')
        self.auto_crc_cb.setChecked(True)
        row2_layout.addWidget(self.auto_crc_cb)

        # 醒目匹配
        row2_layout.addWidget(QtWidgets.QLabel('醒目:'))
        self.highlight_edit = QtWidgets.QLineEdit()
        self.highlight_edit.setPlaceholderText('匹配内容')
        self.highlight_edit.setMaximumWidth(100)
        row2_layout.addWidget(self.highlight_edit)
        
        row2_layout.addStretch(1)
        self.top_vbox.addWidget(row2)

        # Row 3: CRC Calculator Tool
        row3 = QtWidgets.QGroupBox('CRC计算工具')
        row3_layout = QtWidgets.QHBoxLayout(row3)
        row3_layout.setContentsMargins(10, 10, 10, 10)
        row3_layout.addWidget(QtWidgets.QLabel('指令(Hex):'))
        self.crc_input = QtWidgets.QLineEdit()
        self.crc_input.setPlaceholderText('例如: 01 03 00 00 00 01')
        row3_layout.addWidget(self.crc_input)
        
        self.calc_crc_btn = QtWidgets.QPushButton('计算并填充')
        row3_layout.addWidget(self.calc_crc_btn)
        
        row3_layout.addWidget(QtWidgets.QLabel('结果(含CRC):'))
        self.crc_result = QtWidgets.QLineEdit()
        row3_layout.addWidget(self.crc_result)
        
        self.copy_to_send_btn = QtWidgets.QPushButton('填入发送区')
        row3_layout.addWidget(self.copy_to_send_btn)
        
        self.top_vbox.addWidget(row3)

        # Connections
        self.refresh_btn.clicked.connect(self._refresh_ports)
        self.toggle_btn.clicked.connect(self._toggle)
        self.calc_crc_btn.clicked.connect(self._calculate_crc)
        self.copy_to_send_btn.clicked.connect(self._copy_crc_to_send)
        
        self._refresh_ports()
        try:
            self.port_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.baud_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.auto_crc_cb.toggled.connect(lambda _c: self.changed.emit())
            self.highlight_edit.textChanged.connect(self._on_highlight_pattern_changed)
            self.highlight_edit.textChanged.connect(lambda _t: self.changed.emit())
        except Exception:
            pass

    def _calculate_crc(self):
        text = self.crc_input.text().strip()
        if not text:
            return
        try:
            # Parse Hex
            hex_str = text.replace(' ', '')
            data = bytes.fromhex(hex_str)
            val = crc16_modbus(data)
            # Append CRC (Low byte first)
            full_data = data + bytes([val & 0xFF, (val >> 8) & 0xFF])
            
            res_str = ' '.join(f'{b:02X}' for b in full_data)
            self.crc_result.setText(res_str)
        except Exception as e:
            self.crc_result.setText(f'错误: {e}')

    def _copy_crc_to_send(self):
        res = self.crc_result.text()
        if res and not res.startswith('错误'):
            # Find the first send row
            if self.send_rows:
                self.send_rows[0]['data_edit'].setText(res)
                self.send_rows[0]['fmt_combo'].setCurrentText('HEX')

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
            self._log(f'Modbus 串口已打开: {port}@{baud}', 'blue')
            self.toggle_btn.setText('关闭串口')
            self.port_combo.setEnabled(False)
            self.baud_combo.setEnabled(False)
            self.refresh_btn.setEnabled(False)
            self.status_label.setText('已打开')
            self._set_label_status(self.status_label, 'success')
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
        self._log('Modbus 串口已关闭', 'blue')
        self.toggle_btn.setText('打开串口')
        self.port_combo.setEnabled(True)
        self.baud_combo.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.status_label.setText('未连接')
        self._set_label_status(self.status_label, 'error')

    def _recv_loop(self):
        while self.running and self.ser:
            try:
                data = self.ser.read(4096)
                if data:
                    self._update_recv_stats(len(data))
                    self._log(self._format_recv(data), 'green')
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
        text_data = row['data_edit'].text()
        
        # If auto CRC is enabled, and we are in HEX mode, we might want to append CRC if not already there?
        # Actually, standard RS485 tab logic was: calculate CRC and append.
        # But here we have a dedicated tool. 
        # If 'Auto Append CRC' is checked, we append it dynamically.
        
        data = self._parse_send_data(text_data, fmt)
        
        if self.auto_crc_cb.isChecked():
            # Only for HEX mode makes sense usually, but let's try generic
            # Modbus is usually HEX (RTU)
            if fmt == 'HEX' or True: 
                val = crc16_modbus(data)
                data = data + bytes([val & 0xFF, (val >> 8) & 0xFF])
        
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
                'auto_crc': self.auto_crc_cb.isChecked()
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
            self.auto_crc_cb.setChecked(bool(cfg.get('auto_crc', self.auto_crc_cb.isChecked())))
        except Exception:
            pass

    def _on_highlight_pattern_changed(self, text):
        self.highlight_pattern = text
