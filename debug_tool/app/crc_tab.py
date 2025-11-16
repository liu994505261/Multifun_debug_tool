import zlib
from PySide6 import QtWidgets, QtCore, QtGui

from app.crc_utils import crc8, crc16_modbus, crc32


class CRCTab(QtWidgets.QWidget):
    changed = QtCore.Signal()
    def __init__(self, get_global_format_callable, parent=None):
        super().__init__(parent)
        self.get_global_format = get_global_format_callable
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel('算法:'))
        self.algo_combo = QtWidgets.QComboBox()
        self.algo_combo.addItems(['CRC-16(Modbus)', 'CRC-8', 'CRC-32'])
        self.algo_combo.setCurrentText('CRC-16(Modbus)')
        top.addWidget(self.algo_combo)
        self.calc_btn = QtWidgets.QPushButton('计算')
        self.clear_btn = QtWidgets.QPushButton('清空')
        top.addWidget(self.calc_btn)
        top.addWidget(self.clear_btn)
        top.addStretch(1)
        layout.addLayout(top)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.addWidget(QtWidgets.QLabel('数据输入'))
        self.input_edit = QtWidgets.QTextEdit()
        self.input_edit.setPlaceholderText('ASCII 模式按文本计算；HEX 模式按字节序列计算')
        left_layout.addWidget(self.input_edit)

        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.addWidget(QtWidgets.QLabel('计算结果'))
        self.result_view = QtWidgets.QTextEdit()
        self.result_view.setReadOnly(True)
        right_layout.addWidget(self.result_view)

        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setSizes([1, 1])
        layout.addWidget(self.splitter)

        self.calc_btn.clicked.connect(self.compute_crc)
        self.clear_btn.clicked.connect(self.clear)
        try:
            self.algo_combo.currentTextChanged.connect(lambda _t: self.changed.emit())
            self.input_edit.textChanged.connect(lambda: self.changed.emit())
            self.splitter.splitterMoved.connect(lambda _pos, _idx: self.changed.emit())
        except Exception:
            pass

    def _parse_input(self, raw: str, fmt: str) -> bytes:
        raw = (raw or '').strip()
        if not raw:
            return b''
        if fmt == 'HEX':
            hexstr = raw.replace(' ', '').replace('\n', '').replace('\r', '')
            return bytes.fromhex(hexstr)
        return raw.encode('utf-8')

    def compute_crc(self):
        fmt = self.get_global_format()
        algo = self.algo_combo.currentText()
        raw = self.input_edit.toPlainText()
        try:
            data = self._parse_input(raw, fmt)
        except Exception as e:
            self.result_view.setPlainText(f'解析输入失败: {e}')
            return

        try:
            if algo == 'CRC-8':
                val = crc8(data)
                self.result_view.setPlainText(f'CRC-8: {val:02X}')
            elif algo == 'CRC-16(Modbus)':
                val = crc16_modbus(data)
                self.result_view.setPlainText(f'CRC-16(Modbus): {val:04X}')
            elif algo == 'CRC-32':
                val = crc32(data)
                self.result_view.setPlainText(f'CRC-32: {val:08X}')
            else:
                self.result_view.setPlainText('不支持的算法')
        except Exception as e:
            self.result_view.setPlainText(f'计算失败: {e}')

    def clear(self):
        self.input_edit.clear()
        self.result_view.clear()

    def apply_fonts(self, send_font: QtGui.QFont, recv_font: QtGui.QFont):
        self.input_edit.setFont(send_font)
        self.result_view.setFont(recv_font)

    def get_config(self) -> dict:
        sizes = self.splitter.sizes()
        ratio = None
        if sizes and sum(sizes) > 0:
            ratio = max(0.05, min(0.95, sizes[0] / float(sum(sizes))))
        return {
            'algorithm': self.algo_combo.currentText(),
            'input': self.input_edit.toPlainText(),
            'pane_ratio': ratio
        }

    def load_config(self, cfg: dict):
        try:
            self.algo_combo.setCurrentText(cfg.get('algorithm', 'CRC-16(Modbus)'))
            self.input_edit.setPlainText(cfg.get('input', ''))
            ratio = cfg.get('pane_ratio')
            if ratio:
                def apply_ratio():
                    total = sum(self.splitter.sizes()) or 100
                    left = int(total * float(ratio))
                    right = max(10, total - left)
                    self.splitter.setSizes([left, right])
                QtCore.QTimer.singleShot(200, apply_ratio)
        except Exception:
            pass