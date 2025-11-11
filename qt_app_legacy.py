#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PySide6 前端主入口
提供一个基础骨架：主窗口、状态栏时间、菜单、工具栏（全局格式），以及 CRC 标签页。
后续可按此结构扩展到 TCP/UDP/串口/RS485。
"""

import json
import os
import subprocess
import sys
import zlib
import socket
import threading
import time
import traceback
from typing import Tuple

from PySide6 import QtWidgets, QtCore, QtGui
from app.base_comm import BaseCommTab
from app.esp32_log_tab import ESP32LogTab
from app.tcp_tab import TCPClientTabQt
from app.udp_tab import UDPCommTabQt
from app.serial_tab import SerialDebugTabQt
from app.rs485_tab import RS485TestTabQt
from app.crc_tab import CRCTab


# 配置文件路径：开发环境用源码目录，打包后用可执行文件所在目录
CONFIG_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')


def crc8(data: bytes, poly: int = 0x07, init: int = 0x00) -> int:
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) & 0xFF) ^ poly
            else:
                crc = (crc << 1) & 0xFF
    return crc & 0xFF


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


class CRCTabLegacy(QtWidgets.QWidget):
    changed = QtCore.Signal()
    def __init__(self, get_global_format_callable, parent=None):
        super().__init__(parent)
        self.get_global_format = get_global_format_callable
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # 顶部行：算法选择 + 操作
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

        # 分隔：输入 | 结果
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

        # 事件
        self.calc_btn.clicked.connect(self.compute_crc)
        self.clear_btn.clicked.connect(self.clear)
        # 自动保存：相关控件变更时发出信号
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
                val = zlib.crc32(data) & 0xFFFFFFFF
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


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('通信测试上位机 (PySide6)')
        self.resize(1200, 800)

        # 配置与状态
        self.config = self._load_config()
        self.global_format = self.config.get('format', 'ASCII')

        # 恢复窗口几何（位置/大小/最大化）
        try:
            win_cfg = self.config.get('window', {})
            size = win_cfg.get('size')
            pos = win_cfg.get('pos')
            is_max = bool(win_cfg.get('is_maximized', False))
            if size and isinstance(size, (list, tuple)) and len(size) == 2:
                self.resize(int(size[0]), int(size[1]))
            if pos and isinstance(pos, (list, tuple)) and len(pos) == 2:
                self.move(int(pos[0]), int(pos[1]))
            if is_max:
                QtCore.QTimer.singleShot(0, self.showMaximized)
        except Exception:
            pass

        # 字体（遵循原配置结构 ui.send_font / ui.recv_font）
        self.send_font = QtGui.QFont(self._get_ui_font('send_font', default_family='Consolas', default_size=12))
        self.recv_font = QtGui.QFont(self._get_ui_font('recv_font', default_family='Consolas', default_size=12))

        # 中心区域：标签页
        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)

        # 标签页：TCP / UDP / 串口 / RS485 / CRC
        self.tcp_tab = TCPClientTabQt(self.get_global_format)
        self.udp_tab = UDPCommTabQt(self.get_global_format)
        self.serial_tab = SerialDebugTabQt(self.get_global_format)
        self.rs485_tab = RS485TestTabQt(self.get_global_format)
        self.crc_tab = CRCTab(self.get_global_format)
        self.esp32_log_tab = ESP32LogTab(self.get_global_format)

        # 加载配置与应用字体
        self.tcp_tab.load_config(self.config.get('tcp', {}))
        self.udp_tab.load_config(self.config.get('udp', {}))
        self.serial_tab.load_config(self.config.get('serial', {}))
        self.rs485_tab.load_config(self.config.get('rs485', {}))
        self.crc_tab.load_config(self.config.get('crc', {}))
        self.esp32_log_tab.load_config(self.config.get('esp32_log', {}))

        self.tcp_tab.apply_fonts(self.send_font, self.recv_font)
        self.udp_tab.apply_fonts(self.send_font, self.recv_font)
        self.serial_tab.apply_fonts(self.send_font, self.recv_font)
        self.rs485_tab.apply_fonts(self.send_font, self.recv_font)
        self.crc_tab.apply_fonts(self.send_font, self.recv_font)
        self.esp32_log_tab.apply_fonts(self.send_font, self.recv_font)

        self.tabs.addTab(self.tcp_tab, 'TCP客户端')
        self.tabs.addTab(self.udp_tab, 'UDP通信')
        self.tabs.addTab(self.serial_tab, '串口调试')
        self.tabs.addTab(self.rs485_tab, 'RS485测试')
        self.tabs.addTab(self.crc_tab, 'CRC计算')
        self.tabs.addTab(self.esp32_log_tab, 'ESP32 Log')

        # 状态栏：格式选择 + 时间
        status = self.statusBar()
        status.showMessage('就绪')
        fmt_label = QtWidgets.QLabel('格式:')
        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItems(['ASCII', 'HEX'])
        self.format_combo.setCurrentText(self.global_format)
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        # 放大 ASCII/HEX 切换控件
        fmt_font = QtGui.QFont(self.send_font)
        fmt_font.setPointSize(max(12, self.send_font.pointSize() + 2))
        fmt_label.setFont(fmt_font)
        self.format_combo.setFont(fmt_font)
        self.format_combo.setFixedHeight(28)
        status.addPermanentWidget(fmt_label)
        status.addPermanentWidget(self.format_combo)
        self.clock_label = QtWidgets.QLabel()
        status.addPermanentWidget(self.clock_label)
        self._start_clock()

        # 自动保存定时器（延迟触发以避免频繁写盘）
        self._save_timer = QtCore.QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_config)

        # 页面变更信号接入自动保存
        try:
            for tab in [self.tcp_tab, self.udp_tab, self.serial_tab, self.rs485_tab, self.esp32_log_tab]:
                tab.changed.connect(lambda: self._schedule_save())
                # 安装基础自动保存钩子（发送区/分栏/滚动/时间戳）
                tab._install_autosave_hooks()
            self.crc_tab.changed.connect(lambda: self._schedule_save())
        except Exception:
            pass

        # 菜单：文件、设置、帮助
        menu = self.menuBar()
        file_menu = menu.addMenu('文件')
        file_menu.addAction('保存配置', self._save_config)
        file_menu.addAction('加载配置', self._reload_config)
        file_menu.addSeparator()
        file_menu.addAction('退出', self.close)

        settings_menu = menu.addMenu('设置')
        settings_menu.addAction('字体与大小...', self._show_font_settings)

        help_menu = menu.addMenu('帮助')
        help_menu.addAction('关于', self._show_about)

    # 全局格式接口（给标签页调用）
    def get_global_format(self) -> str:
        return self.global_format

    def _on_format_changed(self, text: str):
        self.global_format = text
        self._schedule_save()

    # 字体读取辅助
    def _get_ui_font(self, key: str, default_family: str, default_size: int) -> QtGui.QFont:
        ui = self.config.get('ui', {})
        family = (ui.get(key, {}).get('family') or default_family)
        size = int(ui.get(key, {}).get('size') or default_size)
        f = QtGui.QFont()
        f.setFamily(family)
        f.setPointSize(size)
        return f

    # 时钟
    def _start_clock(self):
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._update_clock)
        self.timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        now = QtCore.QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm:ss')
        self.clock_label.setText(now)

    # 配置读写
    def _load_config(self) -> dict:
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f'加载配置失败: {e}')
        return {}

    def _save_config(self):
        cfg = self._load_config()
        # 全局格式
        cfg['format'] = self.global_format
        # UI 字体
        cfg.setdefault('ui', {})
        cfg['ui']['send_font'] = {
            'family': self.send_font.family(),
            'size': self.send_font.pointSize()
        }
        cfg['ui']['recv_font'] = {
            'family': self.recv_font.family(),
            'size': self.recv_font.pointSize()
        }
        # 窗口几何
        try:
            is_max = self.isMaximized()
            size = [self.width(), self.height()]
            pos = [self.x(), self.y()]
            cfg['window'] = {
                'size': size,
                'pos': pos,
                'is_maximized': bool(is_max)
            }
        except Exception:
            pass
        # 各标签页配置
        cfg['tcp'] = self.tcp_tab.get_config()
        cfg['udp'] = self.udp_tab.get_config()
        cfg['serial'] = self.serial_tab.get_config()
        cfg['rs485'] = self.rs485_tab.get_config()
        cfg['crc'] = self.crc_tab.get_config()
        cfg['esp32_log'] = self.esp32_log_tab.get_config()
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self.statusBar().showMessage('配置已保存', 3000)
        except Exception as e:
            self.statusBar().showMessage(f'保存失败: {e}', 5000)

    def _reload_config(self):
        self.config = self._load_config()
        self.global_format = self.config.get('format', 'ASCII')
        self.format_combo.setCurrentText(self.global_format)
        # 字体应用
        self.send_font = self._get_ui_font('send_font', default_family='Consolas', default_size=12)
        self.recv_font = self._get_ui_font('recv_font', default_family='Consolas', default_size=12)
        # 应用到所有标签页
        for tab in [self.tcp_tab, self.udp_tab, self.serial_tab, self.rs485_tab, self.crc_tab, self.esp32_log_tab]:
            tab.apply_fonts(self.send_font, self.recv_font)
        # 加载各自配置
        self.tcp_tab.load_config(self.config.get('tcp', {}))
        self.udp_tab.load_config(self.config.get('udp', {}))
        self.serial_tab.load_config(self.config.get('serial', {}))
        self.rs485_tab.load_config(self.config.get('rs485', {}))
        self.crc_tab.load_config(self.config.get('crc', {}))
        self.esp32_log_tab.load_config(self.config.get('esp32_log', {}))
        self.statusBar().showMessage('配置已加载', 3000)

    # 字体设置
    def _show_font_settings(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('字体与大小')
        layout = QtWidgets.QVBoxLayout(dlg)

        db = QtGui.QFontDatabase()
        families = db.families()

        # 发送字体
        send_row = QtWidgets.QHBoxLayout()
        send_row.addWidget(QtWidgets.QLabel('发送字体:'))
        send_family = QtWidgets.QComboBox()
        send_family.addItems(families)
        send_family.setCurrentText(self.send_font.family())
        send_row.addWidget(send_family)
        send_row.addWidget(QtWidgets.QLabel('大小:'))
        send_size = QtWidgets.QSpinBox()
        send_size.setRange(8, 36)
        send_size.setValue(self.send_font.pointSize())
        send_row.addWidget(send_size)
        layout.addLayout(send_row)

        # 接收字体
        recv_row = QtWidgets.QHBoxLayout()
        recv_row.addWidget(QtWidgets.QLabel('接收字体:'))
        recv_family = QtWidgets.QComboBox()
        recv_family.addItems(families)
        recv_family.setCurrentText(self.recv_font.family())
        recv_row.addWidget(recv_family)
        recv_row.addWidget(QtWidgets.QLabel('大小:'))
        recv_size = QtWidgets.QSpinBox()
        recv_size.setRange(8, 36)
        recv_size.setValue(self.recv_font.pointSize())
        recv_row.addWidget(recv_size)
        layout.addLayout(recv_row)

        preview = QtWidgets.QLabel('示例：ABC 123 中文测试')
        layout.addWidget(preview)

        def update_preview():
            f = QtGui.QFont(send_family.currentText(), send_size.value())
            preview.setFont(f)
        send_family.currentTextChanged.connect(lambda _: update_preview())
        send_size.valueChanged.connect(lambda _: update_preview())
        update_preview()

        btns = QtWidgets.QHBoxLayout()
        ok_btn = QtWidgets.QPushButton('应用')
        cancel_btn = QtWidgets.QPushButton('取消')
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

        def apply_and_close():
            self.send_font = QtGui.QFont(send_family.currentText(), send_size.value())
            self.recv_font = QtGui.QFont(recv_family.currentText(), recv_size.value())
            for tab in [self.tcp_tab, self.udp_tab, self.serial_tab, self.rs485_tab, self.crc_tab]:
                try:
                    tab.apply_fonts(self.send_font, self.recv_font)
                except Exception:
                    pass
            # 字体更改后自动保存
            self._schedule_save()
            dlg.accept()

        ok_btn.clicked.connect(apply_and_close)
        cancel_btn.clicked.connect(dlg.reject)
        dlg.exec()

    def _show_about(self):
        QtWidgets.QMessageBox.information(self, '关于', '通信测试上位机\nPySide6 预览版：包含 CRC 计算与全局格式设置。')

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        try:
            # 关闭各标签页连接/线程
            for tab in [self.tcp_tab, self.udp_tab, self.serial_tab, self.rs485_tab]:
                try:
                    tab.shutdown()
                except Exception:
                    pass
            self._save_config()
        finally:
            super().closeEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        try:
            # 窗口尺寸变化时自动保存
            self._schedule_save(600)
        except Exception:
            pass
        super().resizeEvent(event)

    def moveEvent(self, event: QtGui.QMoveEvent) -> None:
        try:
            # 窗口位置变化时自动保存
            self._schedule_save(600)
        except Exception:
            pass
        super().moveEvent(event)

    def _schedule_save(self, delay_ms: int = 400):
        """延迟触发保存，避免频繁写入磁盘。"""
        try:
            self._save_timer.start(int(delay_ms))
        except Exception:
            self._save_config()


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


# 入口调用移动到文件末尾，确保类已定义

########################################
# 以下为各通信标签页的 PySide6 迁移实现
########################################

class TCPClientTabQtLegacy(BaseCommTab):
    def __init__(self, get_global_format, parent=None):
        super().__init__(get_global_format, parent)
        self.sock = None
        self.connected = False
        self.recv_thread = None
        # 连接过程状态
        self._connecting = False
        self._connect_thread = None
        self._connecting_socket = None
        self._cancel_connect_flag = False
        # 连接超时管理（毫秒）
        self._connect_timeout_ms = 5000
        # 顶部分组标题
        self.top_group.setTitle('TCP配置')

        # 第一行：工作模式 + 连接按钮 + 状态
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
        self.connect_btn = QtWidgets.QPushButton('连接')
        row1_layout.addWidget(self.connect_btn)
        self.status_label = QtWidgets.QLabel('未连接')
        self.status_label.setStyleSheet('color: red;')
        row1_layout.addWidget(self.status_label)
        row1_layout.addStretch(1)
        self.top_vbox.addWidget(row1)

        # 第二行：地址端口 + 最大连接（仅服务端）
        row2 = QtWidgets.QWidget()
        row2_layout = QtWidgets.QHBoxLayout(row2)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(6)
        self.addr_label = QtWidgets.QLabel('服务器地址:')
        # 服务器地址下拉历史（可编辑）
        self.host_combo = QtWidgets.QComboBox()
        self.host_combo.setEditable(True)
        self.host_combo.setMinimumWidth(150)
        self.host_combo.addItem('127.0.0.1')
        self.host_combo.setCurrentText('127.0.0.1')
        row2_layout.addWidget(self.addr_label)
        row2_layout.addWidget(self.host_combo)
        row2_layout.addWidget(QtWidgets.QLabel('端口:'))
        self.port_combo = QtWidgets.QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setFixedWidth(80)
        self.port_combo.addItem('8000')
        self.port_combo.setCurrentText('8000')
        row2_layout.addWidget(self.port_combo)
        self.max_clients_label = QtWidgets.QLabel('最大连接:')
        self.max_clients_edit = QtWidgets.QLineEdit('5')
        self.max_clients_edit.setFixedWidth(60)
        row2_layout.addWidget(self.max_clients_label)
        row2_layout.addWidget(self.max_clients_edit)
        row2_layout.addStretch(1)
        self.top_vbox.addWidget(row2)

        # 事件连接
        self.connect_btn.clicked.connect(self._toggle_connect)
        self.mode_client_rb.toggled.connect(self._update_mode_ui)
        self.mode_server_rb.toggled.connect(self._update_mode_ui)
        self._update_mode_ui()
        # 自动保存：控件变更通知
        try:
            self.mode_client_rb.toggled.connect(lambda _c: self.changed.emit())
            self.mode_server_rb.toggled.connect(lambda _c: self.changed.emit())
            self.host_combo.editTextChanged.connect(lambda _t: self.changed.emit())
            self.host_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.port_combo.editTextChanged.connect(lambda _t: self.changed.emit())
            self.port_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.max_clients_edit.textChanged.connect(lambda _t: self.changed.emit())
        except Exception:
            pass

    def _toggle_connect(self):
        if self._connecting:
            self._cancel_connect()
        elif self.connected:
            self._disconnect()
        else:
            self._connect()

    def _cancel_connect(self):
        try:
            self._cancel_connect_flag = True
            if self._connecting_socket:
                try:
                    self._connecting_socket.close()
                except Exception:
                    pass
            self._log('正在取消连接...', 'orange')
            self.connect_btn.setText('连接')
            self.status_label.setText('未连接')
            self.status_label.setStyleSheet('color: red;')
        finally:
            self._connecting = False
            self._connecting_socket = None

    def _current_mode(self) -> str:
        return '客户端' if self.mode_client_rb.isChecked() else '服务端'

    def _connect(self):
        mode = self._current_mode()
        host = self.host_combo.currentText().strip()
        try:
            port = int(self.port_combo.currentText().strip() or '0')
        except ValueError:
            self._log('端口必须是数字', 'red')
            return

        if mode == '客户端':
            # 清理旧的连接状态
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
            self.sock = None
            self.connected = False
            self._connecting = False

            # 开始同步连接
            try:
                if not host or port <= 0:
                    self._log('请输入有效的服务器地址与端口', 'red')
                    return

                self.status_label.setText('连接中...')
                self.status_label.setStyleSheet('color: orange;')
                self.connect_btn.setText('连接中...')
                self.connect_btn.setEnabled(False)
                QtWidgets.QApplication.processEvents()  # 强制刷新UI

                self._log(f'正在连接到 {host}:{port} ...', 'blue')
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5.0)
                s.connect((host, port))

                # 连接成功
                self.sock = s
                self.connected = True
                self._log('已连接到服务器', 'blue')
                self._start_recv_thread()
                self.connect_btn.setText('断开')
                self.host_combo.setEnabled(False)
                self.port_combo.setEnabled(False)
                self.mode_client_rb.setEnabled(False)
                self.mode_server_rb.setEnabled(False)
                self.status_label.setText('已连接')
                self.status_label.setStyleSheet('color: green;')
                self._add_history(self.host_combo, host)
                self._add_history(self.port_combo, str(port))
                self.changed.emit()

            except Exception as e:
                self._log(f'连接失败: {e}', 'red')
                self._log(traceback.format_exc(), 'red')  # 记录详细异常
                self.status_label.setText('未连接')
                self.status_label.setStyleSheet('color: red;')
                if 's' in locals() and s:
                    try:
                        s.close()
                    except:
                        pass
            finally:
                self.connect_btn.setText('连接' if not self.connected else '断开')
                self.connect_btn.setEnabled(True)

        elif mode == '服务端':
            self._log('服务端模式启动中...', 'blue')
            # 服务端逻辑保持异步
            self._connecting = True
            self._cancel_connect_flag = False
            self.connect_btn.setText('取消启动')
            self.status_label.setText('启动中...')
            self.status_label.setStyleSheet('color: orange;')

            def do_server_listen():
                try:
                    if port <= 0:
                        raise Exception('请输入有效的监听端口')
                    self._log(f'服务端正在启动，监听 0.0.0.0:{port}', 'blue')
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(('0.0.0.0', port))
                    s.listen(int(self.max_conn_combo.currentText()))
                    self.sock = s
                    self.connected = True

                    def on_ok():
                        if self._cancel_connect_flag:
                            self._disconnect()
                            return
                        self._log(f'服务端启动成功，正在监听 0.0.0.0:{port}', 'green')
                        self._start_accept_thread()
                        self.connect_btn.setText('停止')
                        self.connect_btn.setEnabled(True)
                        self.host_combo.setEnabled(False)
                        self.port_combo.setEnabled(False)
                        self.mode_client_rb.setEnabled(False)
                        self.mode_server_rb.setEnabled(False)
                        self.status_label.setText('运行中')
                        self.status_label.setStyleSheet('color: green;')
                        self._add_history(self.port_combo, str(port))
                        self.changed.emit()
                        self._connecting = False
                        self._connect_thread = None
                    QtCore.QTimer.singleShot(0, on_ok)

                except Exception as e:
                    def on_fail():
                        if self._cancel_connect_flag:
                            self._log('已取消启动', 'orange')
                        elif 'Address already in use' in str(e):
                            self._log(f'启动失败: 端口 {port} 已被占用', 'red')
                        else:
                            self._log(f'启动失败: {e}', 'red')
                        self.connect_btn.setText('启动')
                        self.connect_btn.setEnabled(True)
                        self.status_label.setText('未启动')
                        self.status_label.setStyleSheet('color: red;')
                        self._connecting = False
                        self._connect_thread = None
                        if self.sock:
                            try: self.sock.close()
                            except: pass
                        self.sock = None
                        self.connected = False
                    QtCore.QTimer.singleShot(0, on_fail)

            self._connect_thread = threading.Thread(target=do_server_listen)
            self._connect_thread.daemon = True
            self._connect_thread.start()



    def _disconnect(self):
        self.connected = False
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        self.sock = None
        self._log('连接已断开/服务已停止', 'blue')
        self.connect_btn.setText('连接')
        self.host_combo.setEnabled(True)
        self.port_combo.setEnabled(True)
        self.mode_client_rb.setEnabled(True)
        self.mode_server_rb.setEnabled(True)
        self.status_label.setText('未连接')
        self.status_label.setStyleSheet('color: red;')

    def _add_history(self, combo: QtWidgets.QComboBox, value: str):
        try:
            value = (value or '').strip()
            if not value:
                return
            existing = [combo.itemText(i) for i in range(combo.count())]
            if value not in existing:
                combo.insertItem(0, value)
            combo.setCurrentText(value)
            # 限制最多 20 条历史
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
                'host_history': [self.host_combo.itemText(i) for i in range(self.host_combo.count())],
                'port_history': [self.port_combo.itemText(i) for i in range(self.port_combo.count())],
                'last_host': self.host_combo.currentText(),
                'last_port': self.port_combo.currentText(),
                'max_clients': self.max_clients_edit.text()
            })
        except Exception:
            pass
        return cfg

    def load_config(self, cfg: dict):
        super().load_config(cfg)
        try:
            # 模式
            mode = cfg.get('mode', '客户端')
            if mode == '服务端':
                self.mode_server_rb.setChecked(True)
            else:
                self.mode_client_rb.setChecked(True)
            # 历史与最近值
            host_hist = cfg.get('host_history', [])
            port_hist = cfg.get('port_history', [])
            last_host = cfg.get('last_host', None)
            last_port = cfg.get('last_port', None)
            self.host_combo.clear()
            self.port_combo.clear()
            for h in host_hist:
                self.host_combo.addItem(h)
            for p in port_hist:
                self.port_combo.addItem(str(p))
            if last_host:
                self.host_combo.setCurrentText(str(last_host))
            if last_port:
                self.port_combo.setCurrentText(str(last_port))
        except Exception:
            pass

    def _start_recv_thread(self):
        def loop():
            while self.connected and self.sock:
                try:
                    data = self.sock.recv(4096)
                    if not data:
                        break
                    self._update_recv_stats(len(data))
                    self._log(self._format_recv(data), 'green')
                except Exception as e:
                    self._log(f'接收错误: {e}', 'red')
                    break
            self.connected = False
        self.recv_thread = threading.Thread(target=loop, daemon=True)
        self.recv_thread.start()

    def _accept_loop(self):
        try:
            while self.connected and self.sock:
                client, addr = self.sock.accept()
                self._log(f'客户端连接: {addr[0]}:{addr[1]}', 'blue')
                threading.Thread(target=self._client_loop, args=(client, addr), daemon=True).start()
        except Exception as e:
            self._log(f'服务端错误: {e}', 'red')

    def _client_loop(self, client: socket.socket, addr):
        try:
            while self.connected:
                data = client.recv(4096)
                if not data:
                    break
                self._update_recv_stats(len(data))
                self._log(f'来自 {addr[0]}:{addr[1]}: ' + self._format_recv(data), 'green')
        except Exception as e:
            self._log(f'客户端错误: {e}', 'red')
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _format_recv(self, data: bytes) -> str:
        if self.get_global_format() == 'HEX':
            return ' '.join(f'{b:02X}' for b in data)
        try:
            return data.decode('utf-8', errors='replace')
        except Exception:
            return repr(data)

    def _on_send_clicked(self, idx: int):
        row = self.send_rows[idx]
        data = self._parse_send_data(row['data_edit'].text())
        try:
            if not self.sock:
                self._log('未连接', 'red')
                return
            # 客户端或服务端：都向当前 socket 发送（服务端为广播可后续扩展）
            if self._current_mode() == '客户端':
                self.sock.sendall(data)
            else:
                # 简化：服务端下不直接发送，提示留作扩展
                self._log('服务端发送未实现（待扩展）', 'red')
                return
            self._log(((self._format_recv(data) if self.get_global_format() != 'HEX' else ' '.join(f'{b:02X}' for b in data))), 'blue')
        except Exception as e:
            self._log(f'发送失败: {e}', 'red')

    def shutdown(self):
        super().shutdown()
        self._disconnect()

    def _update_mode_ui(self):
        # 根据模式更新标签与控件可见性
        if self._current_mode() == '客户端':
            self.addr_label.setText('服务器地址:')
            self.max_clients_label.setVisible(False)
            self.max_clients_edit.setVisible(False)
        else:
            self.addr_label.setText('监听地址:')
            self.max_clients_label.setVisible(True)
            self.max_clients_edit.setVisible(True)


class UDPCommTabQtLegacy(BaseCommTab):
    def __init__(self, get_global_format, parent=None):
        super().__init__(get_global_format, parent)
        self.sock = None
        self.running = False
        # 顶部分组标题
        self.top_group.setTitle('UDP配置')

        # 第一行：工作模式 + 启动按钮 + 状态
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
        self.status_label.setStyleSheet('color: red;')
        row1_layout.addWidget(self.status_label)
        row1_layout.addStretch(1)
        self.top_vbox.addWidget(row1)

        # 第二行：本地和远程地址端口
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

        # 第三行：广播/组播
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

        # 事件连接
        self.toggle_btn.clicked.connect(self._toggle)
        self.mode_client_rb.toggled.connect(self._update_mode_ui)
        self.mode_server_rb.toggled.connect(self._update_mode_ui)
        self.multicast_cb.toggled.connect(self._on_multicast_change)
        self._update_mode_ui()
        # 自动保存：控件变更通知
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
                # 客户端也绑定本地便于接收
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
            self.status_label.setStyleSheet('color: green;')
            # 记住历史（客户端模式也记住远程）
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
        self.status_label.setStyleSheet('color: red;')

    def _recv_loop(self):
        while self.running and self.sock:
            try:
                data, addr = self.sock.recvfrom(4096)
                self._update_recv_stats(len(data))
                self._log(f'来自 {addr[0]}:{addr[1]}: ' + self._format_recv(data), 'green')
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
        data = self._parse_send_data(row['data_edit'].text())
        if not self.sock:
            self._log('未启动', 'red')
            return
        try:
            addr = (self.remote_host.currentText().strip(), int(self.remote_port.currentText().strip() or '0'))
            self.sock.sendto(data, addr)
            self._log(((self._format_recv(data) if self.get_global_format() != 'HEX' else ' '.join(f'{b:02X}' for b in data))), 'blue')
            # 发送后也记录远程历史
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
        # 服务端时隐藏远程目标地址配置
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
            # 历史
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
            # 广播/组播
            self.broadcast_cb.setChecked(bool(cfg.get('broadcast', False)))
            self.multicast_cb.setChecked(bool(cfg.get('multicast', False)))
            self.multicast_group.setText(cfg.get('multicast_group', self.multicast_group.text()))
            self._on_multicast_change(self.multicast_cb.isChecked())
            self._update_mode_ui()
        except Exception:
            pass


try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except Exception:
    SERIAL_AVAILABLE = False


class SerialDebugTabQtLegacy(BaseCommTab):
    def __init__(self, get_global_format, parent=None):
        super().__init__(get_global_format, parent)
        self.ser = None
        self.running = False
        # 顶部分组标题
        self.top_group.setTitle('串口配置')

        # 第一行：串口、刷新、波特率、数据位
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

        # 第二行：校验位、停止位、打开按钮、状态
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

        # 事件连接与初始化
        self.refresh_btn.clicked.connect(self._refresh_ports)
        self.toggle_btn.clicked.connect(self._toggle)
        self._refresh_ports()
        # 自动保存：控件变更通知
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
            ports = [p.device for p in serial.tools.list_ports.comports()]
            self.port_combo.clear()
            self.port_combo.addItems(ports)
        except Exception as e:
            self._log(f'刷新失败: {e}', 'red')

    def _open(self):
        if not SERIAL_AVAILABLE:
            self._log('串口库不可用', 'red')
            return
        try:
            port = self.port_combo.currentText()
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
        data = self._parse_send_data(row['data_edit'].text())
        if not self.ser:
            self._log('未打开串口', 'red')
            return
        try:
            self.ser.write(data)
            self._log(((self._format_recv(data) if self.get_global_format() != 'HEX' else ' '.join(f'{b:02X}' for b in data))), 'blue')
        except Exception as e:
            self._log(f'发送失败: {e}', 'red')

    def shutdown(self):
        super().shutdown()
        self._close()

    def get_config(self) -> dict:
        cfg = super().get_config()
        try:
            cfg.update({
                'port': self.port_combo.currentText(),
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
                items = [self.port_combo.itemText(i) for i in range(self.port_combo.count())]
                if last_port not in items:
                    self.port_combo.insertItem(0, last_port)
                self.port_combo.setCurrentText(last_port)
            self.baud_combo.setCurrentText(str(cfg.get('baud', self.baud_combo.currentText())))
            self.databits_combo.setCurrentText(str(cfg.get('databits', self.databits_combo.currentText())))
            self.parity_combo.setCurrentText(str(cfg.get('parity', self.parity_combo.currentText())))
            self.stopbits_combo.setCurrentText(str(cfg.get('stopbits', self.stopbits_combo.currentText())))
        except Exception:
            pass


class RS485TestTabQtLegacy(BaseCommTab):
    def __init__(self, get_global_format, parent=None):
        super().__init__(get_global_format, parent)
        self.ser = None
        self.running = False
        # 顶部分组标题
        self.top_group.setTitle('RS485配置')

        # 第一行：串口、刷新、波特率
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

        # 第二行：打开/关闭、状态、CRC
        row2 = QtWidgets.QWidget()
        row2_layout = QtWidgets.QHBoxLayout(row2)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(6)
        self.toggle_btn = QtWidgets.QPushButton('打开串口')
        row2_layout.addWidget(self.toggle_btn)
        self.status_label = QtWidgets.QLabel('未连接')
        self.status_label.setStyleSheet('color: red;')
        row2_layout.addWidget(self.status_label)
        self.auto_crc_cb = QtWidgets.QCheckBox('附加CRC-16(Modbus)')
        row2_layout.addWidget(self.auto_crc_cb)
        row2_layout.addStretch(1)
        self.top_vbox.addWidget(row2)

        # 事件连接与初始化
        self.refresh_btn.clicked.connect(self._refresh_ports)
        self.toggle_btn.clicked.connect(self._toggle)
        self._refresh_ports()
        # 自动保存：控件变更通知
        try:
            self.port_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.baud_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.auto_crc_cb.toggled.connect(lambda _c: self.changed.emit())
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
            ports = [p.device for p in serial.tools.list_ports.comports()]
            self.port_combo.clear()
            self.port_combo.addItems(ports)
        except Exception as e:
            self._log(f'刷新失败: {e}', 'red')

    def _open(self):
        if not SERIAL_AVAILABLE:
            self._log('串口库不可用', 'red')
            return
        try:
            port = self.port_combo.currentText()
            baud = int(self.baud_combo.currentText())
            self.ser = serial.Serial(port=port, baudrate=baud, timeout=0.2)
            self.running = True
            threading.Thread(target=self._recv_loop, daemon=True).start()
            self._log(f'RS485 串口已打开: {port}@{baud}', 'blue')
            self.toggle_btn.setText('关闭串口')
            self.port_combo.setEnabled(False)
            self.baud_combo.setEnabled(False)
            self.refresh_btn.setEnabled(False)
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
        self._log('RS485 串口已关闭', 'blue')
        self.toggle_btn.setText('打开串口')
        self.port_combo.setEnabled(True)
        self.baud_combo.setEnabled(True)
        self.refresh_btn.setEnabled(True)
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
        data = self._parse_send_data(row['data_edit'].text())
        if self.auto_crc_cb.isChecked():
            val = crc16_modbus(data)
            data = data + bytes([val & 0xFF, (val >> 8) & 0xFF])
        if not self.ser:
            self._log('未打开串口', 'red')
            return
        try:
            self.ser.write(data)
            self._log(((self._format_recv(data) if self.get_global_format() != 'HEX' else ' '.join(f'{b:02X}' for b in data))), 'blue')
        except Exception as e:
            self._log(f'发送失败: {e}', 'red')

    def shutdown(self):
        super().shutdown()
        self._close()

    def get_config(self) -> dict:
        cfg = super().get_config()
        try:
            cfg.update({
                'port': self.port_combo.currentText(),
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
                items = [self.port_combo.itemText(i) for i in range(self.port_combo.count())]
                if last_port not in items:
                    self.port_combo.insertItem(0, last_port)
                self.port_combo.setCurrentText(last_port)
            self.baud_combo.setCurrentText(str(cfg.get('baud', self.baud_combo.currentText())))
            self.auto_crc_cb.setChecked(bool(cfg.get('auto_crc', self.auto_crc_cb.isChecked())))
        except Exception:
            pass


# ESP32LogTab 已迁移到 app.esp32_log_tab


# 文件末尾调用入口
if __name__ == '__main__':
    main() 