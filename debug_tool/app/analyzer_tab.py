from PySide6 import QtWidgets, QtCore, QtGui

class ProtocolAnalyzerTab(QtWidgets.QWidget):
    changed = QtCore.Signal()
    def __init__(self, get_global_format, parent=None):
        super().__init__(parent)
        self.get_global_format = get_global_format
        
        # Left Side: Definition
        self.left_group = QtWidgets.QGroupBox('协议定义')
        self.left_layout = QtWidgets.QVBoxLayout(self.left_group)
        
        self.def_editor = QtWidgets.QPlainTextEdit()
        self.def_editor.setPlaceholderText(
            "# 定义协议结构 (每行一个字段)\n"
            "# 格式: 字段名: 字节数: 类型\n"
            "# 类型支持: int, uint, float, hex\n"
            "Header: 1: hex\n"
            "ID: 1: uint\n"
            "Temp: 2: int\n"
            "Voltage: 4: float"
        )
        self.left_layout.addWidget(self.def_editor)
        self.apply_btn = QtWidgets.QPushButton('应用定义')
        self.left_layout.addWidget(self.apply_btn)

        # Right Side: Live Analysis
        self.right_group = QtWidgets.QGroupBox('实时解析')
        self.right_layout = QtWidgets.QVBoxLayout(self.right_group)
        
        # Source Selection
        source_row = QtWidgets.QHBoxLayout()
        source_row.addWidget(QtWidgets.QLabel('数据来源:'))
        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.addItems(['所有来源', 'TCP客户端', 'UDP通信', '串口调试', 'Modbus'])
        source_row.addWidget(self.source_combo)
        source_row.addStretch(1)
        self.right_layout.addLayout(source_row)
        
        self.result_table = QtWidgets.QTableWidget()
        self.result_table.setColumnCount(2)
        self.result_table.setHorizontalHeaderLabels(['字段', '值'])
        self.result_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.right_layout.addWidget(self.result_table)
        
        # Main Layout
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.left_group)
        self.splitter.addWidget(self.right_group)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.splitter)
        
        # State
        self.fields = []
        self.apply_btn.clicked.connect(self.parse_definition)
        self.def_editor.textChanged.connect(lambda: self.changed.emit())

    def parse_definition(self):
        text = self.def_editor.toPlainText()
        new_fields = []
        try:
            for line in text.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(':')
                if len(parts) >= 3:
                    name = parts[0].strip()
                    size = int(parts[1].strip())
                    dtype = parts[2].strip().lower()
                    new_fields.append({'name': name, 'size': size, 'type': dtype})
            self.fields = new_fields
            # QtWidgets.QMessageBox.information(self, '成功', f'已加载 {len(self.fields)} 个字段定义')
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, '错误', f'解析定义失败: {e}')

    def process_incoming_data(self, data: bytes, source_name: str = None):
        """
        Attempt to parse binary data according to definition.
        Only parses the beginning of the packet for simplicity.
        """
        # Filter source
        current_source = self.source_combo.currentText()
        if current_source != '所有来源' and source_name and current_source != source_name:
            return

        if not self.fields or not data:
            return
            
        self.result_table.setRowCount(len(self.fields))
        offset = 0
        import struct
        
        for i, field in enumerate(self.fields):
            name = field['name']
            size = field['size']
            dtype = field['type']
            
            val_str = 'N/A'
            if offset + size <= len(data):
                chunk = data[offset:offset+size]
                try:
                    if dtype == 'hex':
                        val_str = ' '.join(f'{b:02X}' for b in chunk)
                    elif dtype == 'uint':
                        val = int.from_bytes(chunk, byteorder='big', signed=False)
                        val_str = str(val)
                    elif dtype == 'int':
                        val = int.from_bytes(chunk, byteorder='big', signed=True)
                        val_str = str(val)
                    elif dtype == 'float':
                        if size == 4:
                            val = struct.unpack('>f', chunk)[0]
                            val_str = f'{val:.4f}'
                        elif size == 8:
                            val = struct.unpack('>d', chunk)[0]
                            val_str = f'{val:.4f}'
                        else:
                            val_str = 'ErrSize'
                    else:
                        val_str = 'UnknownType'
                except Exception:
                    val_str = 'ParseErr'
            else:
                val_str = 'Incomplete'
                
            offset += size
            
            self.result_table.setItem(i, 0, QtWidgets.QTableWidgetItem(name))
            self.result_table.setItem(i, 1, QtWidgets.QTableWidgetItem(val_str))

    def apply_fonts(self, send_font, recv_font):
        self.def_editor.setFont(send_font)
        self.result_table.setFont(recv_font)

    def get_config(self):
        return {
            'source': self.source_combo.currentText(),
            'definition': self.def_editor.toPlainText()
        }

    def load_config(self, cfg):
        self.source_combo.setCurrentText(cfg.get('source', '所有来源'))
        self.def_editor.setPlainText(cfg.get('definition', ''))
        self.parse_definition() # Auto apply on load
        
    def shutdown(self):
        pass
        
    def _install_autosave_hooks(self):
        pass
