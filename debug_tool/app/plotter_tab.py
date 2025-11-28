from PySide6 import QtWidgets, QtCore, QtGui

class PlotterTab(QtWidgets.QWidget):
    changed = QtCore.Signal()
    def __init__(self, get_global_format, parent=None):
        super().__init__(parent)
        self.get_global_format = get_global_format
        self.top_group = QtWidgets.QGroupBox('绘图配置')
        self.top_vbox = QtWidgets.QVBoxLayout(self.top_group)
        
        # 绘图配置
        row1 = QtWidgets.QWidget()
        row1_layout = QtWidgets.QHBoxLayout(row1)
        row1_layout.setContentsMargins(0,0,0,0)
        
        row1_layout.addWidget(QtWidgets.QLabel('数据来源:'))
        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.addItems(['所有来源', 'TCP客户端', 'UDP通信', '串口调试', 'Modbus'])
        self.source_combo.setMinimumWidth(100)
        row1_layout.addWidget(self.source_combo)
        
        self.enable_plot_cb = QtWidgets.QCheckBox('启用绘图')
        row1_layout.addWidget(self.enable_plot_cb)
        
        row1_layout.addWidget(QtWidgets.QLabel('匹配规则(正则):'))
        self.regex_input = QtWidgets.QLineEdit()
        self.regex_input.setPlaceholderText(r'Value: (\d+)')
        self.regex_input.setText(r'(\d+)') # 默认匹配任意数字
        row1_layout.addWidget(self.regex_input)
        
        row1_layout.addWidget(QtWidgets.QLabel('Y轴范围:'))
        self.y_min = QtWidgets.QSpinBox()
        self.y_min.setRange(-99999, 99999)
        self.y_min.setValue(0)
        self.y_max = QtWidgets.QSpinBox()
        self.y_max.setRange(-99999, 99999)
        self.y_max.setValue(100)
        row1_layout.addWidget(self.y_min)
        row1_layout.addWidget(QtWidgets.QLabel('-'))
        row1_layout.addWidget(self.y_max)
        
        self.clear_btn = QtWidgets.QPushButton('清空画布')
        row1_layout.addWidget(self.clear_btn)
        row1_layout.addStretch(1)
        self.top_vbox.addWidget(row1)

        # 画布区域 (这里使用简单的 QPainter 自定义 Widget 作为画布，避免引入 matplotlib/pyqtgraph 依赖)
        self.canvas = SimpleChartWidget()
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.top_group)
        layout.addWidget(self.canvas)
        
        # 信号连接
        self.canvas.y_range_changed.connect(self._on_canvas_y_changed)
        self.y_min.valueChanged.connect(lambda v: self.canvas.set_y_range(v, self.y_max.value()))
        self.y_max.valueChanged.connect(lambda v: self.canvas.set_y_range(self.y_min.value(), v))
        self.clear_btn.clicked.connect(self.canvas.clear_data)
        
        # 监听配置变更
        self.source_combo.currentTextChanged.connect(lambda: self.changed.emit())
        self.enable_plot_cb.toggled.connect(lambda: self.changed.emit())
        self.regex_input.textChanged.connect(lambda: self.changed.emit())
        self.y_min.valueChanged.connect(lambda: self.changed.emit())
        self.y_max.valueChanged.connect(lambda: self.changed.emit())

    def _on_canvas_y_changed(self, y_min, y_max):
        self.y_min.blockSignals(True)
        self.y_max.blockSignals(True)
        self.y_min.setValue(y_min)
        self.y_max.setValue(y_max)
        self.y_min.blockSignals(False)
        self.y_max.blockSignals(False)
        self.changed.emit()

    def apply_fonts(self, send_font, recv_font):
        pass # 暂时不需要特殊字体
        
    def add_data_point(self, val: float):
        if self.enable_plot_cb.isChecked():
            self.canvas.add_point(val)

    def process_incoming_data(self, data, source_name: str = None):
        """尝试从文本中提取数据并绘图"""
        if not self.enable_plot_cb.isChecked():
            return
            
        # 过滤来源
        current_source = self.source_combo.currentText()
        if current_source != '所有来源' and source_name and current_source != source_name:
            return
            
        # 解码
        text = ""
        if isinstance(data, bytes):
            try:
                text = data.decode('utf-8', errors='ignore')
            except:
                return
        else:
            text = str(data)

        import re
        try:
            pattern = self.regex_input.text()
            if not pattern: 
                return
            # 查找所有匹配
            matches = re.findall(pattern, text)
            for m in matches:
                # 如果是 tuple (多分组)，取第一个；如果是 str，直接用
                val_str = m[0] if isinstance(m, tuple) else m
                try:
                    val = float(val_str)
                    self.add_data_point(val)
                except ValueError:
                    pass
        except Exception:
            pass

    def get_config(self):
        return {
            'source': self.source_combo.currentText(),
            'enabled': self.enable_plot_cb.isChecked(),
            'regex': self.regex_input.text(),
            'y_min': self.y_min.value(),
            'y_max': self.y_max.value()
        }

    def load_config(self, cfg):
        self.source_combo.setCurrentText(cfg.get('source', '所有来源'))
        self.enable_plot_cb.setChecked(cfg.get('enabled', False))
        self.regex_input.setText(cfg.get('regex', r'(\d+)'))
        self.y_min.setValue(cfg.get('y_min', 0))
        self.y_max.setValue(cfg.get('y_max', 100))
        self.canvas.set_y_range(self.y_min.value(), self.y_max.value())
        
    def shutdown(self):
        pass
        
    def _install_autosave_hooks(self):
        pass


class SimpleChartWidget(QtWidgets.QWidget):
    y_range_changed = QtCore.Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []
        self.max_points = 200
        self.y_min = 0
        self.y_max = 100
        self.setBackgroundRole(QtGui.QPalette.Base)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True) # Allow QSS background
        self.setStyleSheet("background-color: #1e1e1e; border: 1px solid #555;") # Default dark bg
        self.setMouseTracking(True) # For potential crosshair

    def set_y_range(self, y_min, y_max):
        self.y_min = y_min
        self.y_max = y_max
        self.update()

    def add_point(self, val):
        self.data.append(val)
        if len(self.data) > self.max_points:
            self.data.pop(0)
        self.update()

    def clear_data(self):
        self.data = []
        self.update()

    def wheelEvent(self, event: QtGui.QWheelEvent):
        # 鼠标滚轮缩放 Y 轴范围
        delta = event.angleDelta().y()
        if delta == 0:
            return
        
        # 缩放比例
        scale_factor = 0.9 if delta > 0 else 1.1
        
        center = (self.y_min + self.y_max) / 2
        span = self.y_max - self.y_min
        if span == 0: span = 10
        
        new_span = span * scale_factor
        new_min = int(center - new_span / 2)
        new_max = int(center + new_span / 2)
        
        if new_max == new_min:
            new_max += 1
            
        self.y_min = new_min
        self.y_max = new_max
        self.y_range_changed.emit(self.y_min, self.y_max)
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        # Margins for ruler
        left_margin = 40
        bottom_margin = 20
        plot_w = w - left_margin
        plot_h = h - bottom_margin
        
        painter.translate(left_margin, 0)
        
        # Draw Background Grid & Ruler
        painter.setPen(QtGui.QPen(QtGui.QColor(80, 80, 80), 1, QtCore.Qt.DotLine))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        
        # Horizontal lines (Y-axis)
        steps = 5
        for i in range(steps + 1):
            y_ratio = i / steps
            y_pos = y_ratio * plot_h
            
            # Grid line
            painter.setPen(QtGui.QPen(QtGui.QColor(80, 80, 80), 1, QtCore.Qt.DotLine))
            painter.drawLine(0, int(y_pos), plot_w, int(y_pos))
            
            # Ruler Text (Left side)
            val = self.y_max - (self.y_max - self.y_min) * y_ratio
            text = f"{val:.1f}"
            painter.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
            painter.drawText(QtCore.QRect(-left_margin, int(y_pos) - 10, left_margin - 5, 20), 
                             QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, text)

        # Vertical lines (X-axis time/count)
        x_steps = 10
        for i in range(x_steps + 1):
            x_ratio = i / x_steps
            x_pos = x_ratio * plot_w
            
            painter.setPen(QtGui.QPen(QtGui.QColor(80, 80, 80), 1, QtCore.Qt.DotLine))
            painter.drawLine(int(x_pos), 0, int(x_pos), plot_h)

        # Draw Data
        if len(self.data) < 2:
            return

        # Pen for line
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 120, 212), 2))
        
        x_step = plot_w / (self.max_points - 1)
        
        # Map value to Y coordinate
        def map_y(val):
            if self.y_max == self.y_min:
                return plot_h / 2
            # Invert Y because screen Y grows downwards
            ratio = (val - self.y_min) / (self.y_max - self.y_min)
            return plot_h - (ratio * plot_h)

        path = QtGui.QPainterPath()
        
        first_pt = True
        # Draw only visible latest points filling the screen
        # We align right? Or always fill?
        # Let's fill from left.
        
        for i, val in enumerate(self.data):
            x = i * x_step
            y = map_y(val)
            # Clamp y for safety
            y = max(-10, min(plot_h + 10, y))
            
            if first_pt:
                path.moveTo(x, y)
                first_pt = False
            else:
                path.lineTo(x, y)
        
        # Set clip to avoid drawing outside plot area
        painter.setClipRect(0, 0, plot_w, plot_h)
        painter.drawPath(path)
