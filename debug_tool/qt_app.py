#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PySide6 前端主入口（精简版）
保留主窗口与模块化标签页导入，移除内置 Legacy 实现。
"""

import json
import os
import sys

from PySide6 import QtWidgets, QtCore, QtGui

"""
Ensure local package imports work even if the script is launched
from a different working directory. Insert project root to sys.path
before importing from the local 'app' package.
"""
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.tcp_tab import TCPClientTabQt
from app.udp_tab import UDPCommTabQt
from app.serial_tab import SerialDebugTabQt
from app.modbus_tab import ModbusTab
from app.plotter_tab import PlotterTab
from app.analyzer_tab import ProtocolAnalyzerTab
from app.esp32_log_tab import ESP32LogTab
from app.esp32_flash_tab import ESP32FlashTab
from app.theme import ModernTheme


# 配置文件路径：开发环境用源码目录，打包后用可执行文件所在目录
CONFIG_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('通信测试上位机 (PySide6)')
        self.resize(1200, 800)

        # 配置与状态
        self.config = self._load_config()
        self.global_format = self.config.get('format', 'ASCII')
        self.serial_blacklist = list(self.config.get('serial_blacklist', []))
        self.ui_theme = (self.config.get('ui', {}) or {}).get('theme', 'light')

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
        self.send_font = self._get_ui_font('send_font', default_family='Consolas', default_size=12)
        self.recv_font = self._get_ui_font('recv_font', default_family='Consolas', default_size=12)

        # 中心区域：标签页
        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)

        # 标签页：TCP / UDP / 串口 / RS485 / CRC / ESP32 Log / ESP32烧录
        self.tcp_tab = TCPClientTabQt(self.get_global_format)
        self.udp_tab = UDPCommTabQt(self.get_global_format)
        self.serial_tab = SerialDebugTabQt(self.get_global_format, self.get_serial_blacklist)
        self.modbus_tab = ModbusTab(self.get_global_format, self.get_serial_blacklist)
        self.plotter_tab = PlotterTab(self.get_global_format)
        self.analyzer_tab = ProtocolAnalyzerTab(self.get_global_format)
        self.esp32_log_tab = ESP32LogTab(self.get_global_format, self.get_serial_blacklist)
        self.esp32_flash_tab = ESP32FlashTab(self.get_global_format, self.get_serial_blacklist)

        # 加载配置与应用字体
        self.tcp_tab.load_config(self.config.get('tcp', {}))
        self.udp_tab.load_config(self.config.get('udp', {}))
        self.serial_tab.load_config(self.config.get('serial', {}))
        self.modbus_tab.load_config(self.config.get('modbus', {}))
        self.plotter_tab.load_config(self.config.get('plotter', {}))
        self.analyzer_tab.load_config(self.config.get('analyzer', {}))
        self.esp32_log_tab.load_config(self.config.get('esp32_log', {}))
        self.esp32_flash_tab.load_config(self.config.get('esp32_flash', {}))

        self.tcp_tab.apply_fonts(self.send_font, self.recv_font)
        self.udp_tab.apply_fonts(self.send_font, self.recv_font)
        self.serial_tab.apply_fonts(self.send_font, self.recv_font)
        self.modbus_tab.apply_fonts(self.send_font, self.recv_font)
        self.plotter_tab.apply_fonts(self.send_font, self.recv_font)
        self.analyzer_tab.apply_fonts(self.send_font, self.recv_font)
        self.esp32_log_tab.apply_fonts(self.send_font, self.recv_font)
        self.esp32_flash_tab.apply_fonts(self.send_font, self.recv_font)

        self.tabs.addTab(self.tcp_tab, 'TCP客户端')
        self.tabs.addTab(self.udp_tab, 'UDP通信')
        self.tabs.addTab(self.serial_tab, '串口调试')
        self.tabs.addTab(self.modbus_tab, 'Modbus')
        self.tabs.addTab(self.plotter_tab, '数据波形')
        self.tabs.addTab(self.analyzer_tab, '协议分析')
        self.tabs.addTab(self.esp32_log_tab, 'ESP32 Log')
        self.tabs.addTab(self.esp32_flash_tab, 'ESP32烧录')

        # 录制文件句柄
        self.record_file = None

        # 数据路由
        self.tcp_tab.data_received.connect(lambda d: self._route_data(d, 'TCP客户端'))
        self.udp_tab.data_received.connect(lambda d: self._route_data(d, 'UDP通信'))
        self.serial_tab.data_received.connect(lambda d: self._route_data(d, '串口调试'))
        self.modbus_tab.data_received.connect(lambda d: self._route_data(d, 'Modbus'))

        # 恢复上次打开的tab页面
        last_tab = self.config.get('last_active_tab', 0)
        if 0 <= last_tab < self.tabs.count():
            self.tabs.setCurrentIndex(last_tab)

        # 监听tab切换事件，自动保存
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # 状态栏：格式选择 + 时间
        status = self.statusBar()
        status.showMessage('就绪')
        # 修复背景色：让QStatusBar背景透明，继承主窗口颜色
        status.setStyleSheet("QStatusBar { background: transparent; } QStatusBar::item { border: none; }")
        
        # # 录制功能
        # self.record_btn = QtWidgets.QPushButton("开始录制")
        # self.record_btn.setCheckable(True)
        # self.record_btn.setStyleSheet("QPushButton:checked { background-color: #ff4d4d; color: white; border-radius: 4px; }")
        # self.record_btn.clicked.connect(self._toggle_recording)
        # status.addPermanentWidget(self.record_btn)

        fmt_label = QtWidgets.QLabel('格式:')
        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItems(['ASCII', 'HEX'])
        self.format_combo.setCurrentText(self.global_format)
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
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
            for tab in [self.tcp_tab, self.udp_tab, self.serial_tab, self.modbus_tab, self.plotter_tab, self.analyzer_tab, self.esp32_log_tab, self.esp32_flash_tab]:
                tab.changed.connect(lambda: self._schedule_save())
                tab._install_autosave_hooks()
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
        # settings_menu.addAction('字体与大小...', self._show_font_settings) # 移除
        settings_menu.addAction('串口黑名单...', self._show_serial_blacklist_settings)
        self.dark_theme_action = QtGui.QAction('深色主题', self)
        self.dark_theme_action.setCheckable(True)
        self.dark_theme_action.setChecked(self.ui_theme == 'dark')
        self.dark_theme_action.toggled.connect(self._on_dark_theme_toggled)
        settings_menu.addAction(self.dark_theme_action)

        help_menu = menu.addMenu('帮助')
        help_menu.addAction('关于', self._show_about)

        self._apply_theme(self.ui_theme)

    # 数据路由
    def _route_data(self, data, source):
        self.plotter_tab.process_incoming_data(data, source)
        self.analyzer_tab.process_incoming_data(data, source)
        
        # 录制
        if self.record_file:
            try:
                ts = QtCore.QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm:ss.zzz')
                # 尝试转文本
                content = ""
                try:
                    content = data.decode('utf-8', errors='replace')
                except:
                    content = repr(data)
                
                line = f"[{ts}] [{source}] {content}\n"
                self.record_file.write(line)
                self.record_file.flush()
            except Exception:
                pass

    # # 录制开关
    # def _toggle_recording(self):
    #     if self.record_btn.isChecked():
    #         # 开始录制
    #         filename = f"record_{QtCore.QDateTime.currentDateTime().toString('yyyyMMdd_hhmmss')}.log"
    #         path = os.path.join(os.getcwd(), filename)
    #         try:
    #             self.record_file = open(path, 'w', encoding='utf-8')
    #             self.record_btn.setText(f"录制中: {filename}")
    #             self.statusBar().showMessage(f"开始录制到 {path}", 3000)
    #         except Exception as e:
    #             self.record_btn.setChecked(False)
    #             QtWidgets.QMessageBox.warning(self, "录制失败", f"无法创建文件: {e}")
    #     else:
    #         # 停止录制
    #         if self.record_file:
    #             try:
    #                 self.record_file.close()
    #             except:
    #                 pass
    #             self.record_file = None
    #         self.record_btn.setText("开始录制")
    #         self.statusBar().showMessage("录制已停止", 3000)

    # 全局格式接口（给标签页调用）
    def get_global_format(self) -> str:
        return self.global_format

    def _on_format_changed(self, text: str):
        self.global_format = text
        self._schedule_save()

    def _on_tab_changed(self, index: int):
        """tab页面切换时保存当前索引"""
        self._schedule_save()
        
    def _apply_theme(self, theme: str):
        app = QtWidgets.QApplication.instance()
        if app:
            app.setStyleSheet(ModernTheme.get_qss(theme))

    def _on_dark_theme_toggled(self, checked: bool):
        self.ui_theme = 'dark' if checked else 'light'
        self._apply_theme(self.ui_theme)
        self._schedule_save()
    
    def get_serial_blacklist(self) -> list:
        return list(self.serial_blacklist or [])

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

    # 缩放功能
    def _zoom_in(self):
        self._adjust_font_size(1)

    def _zoom_out(self):
        self._adjust_font_size(-1)

    def _adjust_font_size(self, delta):
        s = self.send_font.pointSize() + delta
        if s < 6: s = 6
        if s > 72: s = 72
        self.send_font.setPointSize(s)
        
        r = self.recv_font.pointSize() + delta
        if r < 6: r = 6
        if r > 72: r = 72
        self.recv_font.setPointSize(r)
        
        # Update tabs
        for tab in [self.tcp_tab, self.udp_tab, self.serial_tab, self.modbus_tab, self.plotter_tab, self.analyzer_tab, self.esp32_log_tab, self.esp32_flash_tab]:
            tab.apply_fonts(self.send_font, self.recv_font)
        self._schedule_save()

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
        cfg['serial_blacklist'] = list(self.serial_blacklist or [])
        # 保存当前打开的tab页面索引
        cfg['last_active_tab'] = self.tabs.currentIndex()
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
        cfg['ui']['theme'] = self.ui_theme
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
        cfg['modbus'] = self.modbus_tab.get_config()
        cfg['plotter'] = self.plotter_tab.get_config()
        cfg['analyzer'] = self.analyzer_tab.get_config()
        cfg['esp32_log'] = self.esp32_log_tab.get_config()
        cfg['esp32_flash'] = self.esp32_flash_tab.get_config()
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self.statusBar().showMessage('配置已保存', 3000)
        except Exception as e:
            self.statusBar().showMessage(f'保存失败: {e}', 5000)

    def _reload_config(self):
        self.config = self._load_config()
        self.global_format = self.config.get('format', 'ASCII')
        self.serial_blacklist = list(self.config.get('serial_blacklist', []))
        self.ui_theme = (self.config.get('ui', {}) or {}).get('theme', 'light')
        self.format_combo.setCurrentText(self.global_format)
        # 字体应用
        self.send_font = self._get_ui_font('send_font', default_family='Consolas', default_size=12)
        self.recv_font = self._get_ui_font('recv_font', default_family='Consolas', default_size=12)
        # 应用到所有标签页
        for tab in [self.tcp_tab, self.udp_tab, self.serial_tab, self.modbus_tab, self.plotter_tab, self.analyzer_tab, self.esp32_log_tab, self.esp32_flash_tab]:
            tab.apply_fonts(self.send_font, self.recv_font)
        # 加载各自配置
        self.tcp_tab.load_config(self.config.get('tcp', {}))
        self.udp_tab.load_config(self.config.get('udp', {}))
        self.serial_tab.load_config(self.config.get('serial', {}))
        self.modbus_tab.load_config(self.config.get('modbus', {}))
        self.plotter_tab.load_config(self.config.get('plotter', {}))
        self.analyzer_tab.load_config(self.config.get('analyzer', {}))
        self.esp32_log_tab.load_config(self.config.get('esp32_log', {}))
        self.esp32_flash_tab.load_config(self.config.get('esp32_flash', {}))
        self._apply_theme(self.ui_theme)
        self.statusBar().showMessage('配置已加载', 3000)

    def _show_serial_blacklist_settings(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle('串口黑名单')
        layout = QtWidgets.QVBoxLayout(dlg)
        info = QtWidgets.QLabel('屏蔽这些串口号，不在下拉列表显示')
        layout.addWidget(info)
        lst = QtWidgets.QListWidget()
        for p in self.serial_blacklist:
            lst.addItem(str(p))
        layout.addWidget(lst)
        btns = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton('添加')
        del_btn = QtWidgets.QPushButton('删除选中')
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        btns.addStretch(1)
        apply_btn = QtWidgets.QPushButton('应用')
        cancel_btn = QtWidgets.QPushButton('取消')
        btns.addWidget(apply_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)
        def do_add():
            text, ok = QtWidgets.QInputDialog.getText(self, '添加黑名单', '串口号:')
            if not ok:
                return
            t = (text or '').strip()
            if not t:
                return
            if not lst.findItems(t, QtCore.Qt.MatchFlag.MatchExactly):
                lst.addItem(t)
        def do_del():
            for it in lst.selectedItems():
                lst.takeItem(lst.row(it))
        def do_apply():
            self.serial_blacklist = [lst.item(i).text() for i in range(lst.count())]
            self._schedule_save()
            try:
                self.serial_tab._refresh_ports()
            except Exception:
                pass
            try:
                self.modbus_tab._refresh_ports()
            except Exception:
                pass
            try:
                self.esp32_log_tab._refresh_ports()
            except Exception:
                pass
            try:
                self.esp32_flash_tab._refresh_ports()
            except Exception:
                pass
            dlg.accept()
        add_btn.clicked.connect(do_add)
        del_btn.clicked.connect(do_del)
        apply_btn.clicked.connect(do_apply)
        cancel_btn.clicked.connect(dlg.reject)
        dlg.exec()

    # 字体设置
    def _show_font_settings(self):
        # 移除
        pass

    def _show_about(self):
        QtWidgets.QMessageBox.information(self, '关于', '通信测试上位机\nPySide6 精简版：模块化标签页与配置保存。')

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        try:
            # 关闭各标签页连接/线程
            for tab in [self.tcp_tab, self.udp_tab, self.serial_tab, self.modbus_tab, self.plotter_tab, self.analyzer_tab, self.esp32_flash_tab]:
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


if __name__ == '__main__':
    main()