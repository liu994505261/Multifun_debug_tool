#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试版本检查和下载功能
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from app.version_manager import VersionManager
from PySide6 import QtWidgets, QtCore


class VersionTestWidget(QtWidgets.QWidget):
    """版本测试界面"""
    
    def __init__(self):
        super().__init__()
        # 使用较低版本进行测试，或者自动获取当前版本
        self.vm = VersionManager("0.9.0")  # 可以传入None让它自动获取
        self.test_mode = False  # 测试模式标志
        self.setup_ui()
        self.connect_signals()
        
    def setup_ui(self):
        """设置界面"""
        self.setWindowTitle("版本检查和下载测试")
        self.setFixedSize(500, 400)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # 标题
        title = QtWidgets.QLabel("版本管理测试工具")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # 当前版本信息
        self.version_info = QtWidgets.QLabel(f"当前版本: {self.vm.current_version}")
        layout.addWidget(self.version_info)
        
        # 测试模式选择
        test_mode_layout = QtWidgets.QHBoxLayout()
        self.test_mode_cb = QtWidgets.QCheckBox("测试模式（模拟下载）")
        self.test_mode_cb.toggled.connect(self.toggle_test_mode)
        test_mode_layout.addWidget(self.test_mode_cb)
        test_mode_layout.addStretch()
        layout.addLayout(test_mode_layout)
        
        # 按钮区域
        button_layout = QtWidgets.QHBoxLayout()
        
        self.check_btn = QtWidgets.QPushButton("检查更新")
        self.check_btn.clicked.connect(self.check_updates)
        button_layout.addWidget(self.check_btn)
        
        self.download_btn = QtWidgets.QPushButton("下载最新版本")
        self.download_btn.clicked.connect(self.download_update)
        self.download_btn.setEnabled(False)
        button_layout.addWidget(self.download_btn)
        
        self.test_download_btn = QtWidgets.QPushButton("测试下载链接")
        self.test_download_btn.clicked.connect(self.test_download_links)
        button_layout.addWidget(self.test_download_btn)
        
        self.view_log_btn = QtWidgets.QPushButton("查看日志")
        self.view_log_btn.clicked.connect(self.view_logs)
        button_layout.addWidget(self.view_log_btn)
        
        layout.addLayout(button_layout)
        
        # 进度条
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 日志区域
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)
        
        # 退出按钮
        self.quit_btn = QtWidgets.QPushButton("退出")
        self.quit_btn.clicked.connect(self.close)
        layout.addWidget(self.quit_btn)
    
    def connect_signals(self):
        """连接信号"""
        self.vm.update_available.connect(self.on_update_available)
        self.vm.check_finished.connect(self.on_check_finished)
        self.vm.check_error.connect(self.on_check_error)
        self.vm.download_progress.connect(self.on_download_progress)
        self.vm.download_finished.connect(self.on_download_finished)
        self.vm.download_error.connect(self.on_download_error)
    
    def log(self, message):
        """添加日志"""
        self.log_text.append(f"[{QtCore.QTime.currentTime().toString()}] {message}")
    
    def check_updates(self):
        """检查更新"""
        self.check_btn.setEnabled(False)
        self.download_btn.setEnabled(False)
        self.log("开始检查更新...")
        self.vm.check_for_updates()
    
    def toggle_test_mode(self, checked):
        """切换测试模式"""
        self.test_mode = checked
        if checked:
            self.log("已启用测试模式 - 将模拟下载过程")
        else:
            self.log("已禁用测试模式 - 将执行真实下载")
    
    def download_update(self):
        """下载更新"""
        if self.test_mode:
            self.simulate_download()
        else:
            self.download_btn.setEnabled(False)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.log("开始下载最新版本...")
            self.vm.download_latest_release()
    
    def simulate_download(self):
        """模拟下载过程"""
        self.download_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.log("开始模拟下载...")
        
        # 创建定时器模拟下载进度
        self.download_timer = QtCore.QTimer()
        self.download_progress_value = 0
        
        def update_progress():
            self.download_progress_value += 5
            self.progress_bar.setValue(self.download_progress_value)
            self.log(f"模拟下载进度: {self.download_progress_value}%")
            
            if self.download_progress_value >= 100:
                self.download_timer.stop()
                self.progress_bar.setVisible(False)
                self.download_btn.setEnabled(True)
                
                # 创建一个模拟文件
                import tempfile
                temp_file = os.path.join(tempfile.gettempdir(), "test_download.exe")
                with open(temp_file, 'w') as f:
                    f.write("This is a test file for download simulation")
                
                self.log(f"模拟下载完成: {temp_file}")
                self.on_download_finished(temp_file)
        
        self.download_timer.timeout.connect(update_progress)
        self.download_timer.start(200)  # 每200ms更新一次
    
    def test_download_links(self):
        """测试下载链接可用性"""
        self.test_download_btn.setEnabled(False)
        self.log("开始测试下载链接...")
        
        def _test_links():
            import requests
            repo_name = "liu994505261/Multifun_debug_tool"
            
            # 测试API可用性
            try:
                api_url = f"https://api.github.com/repos/{repo_name}/releases/latest"
                response = requests.head(api_url, timeout=10)
                if response.status_code == 200:
                    self.log("✓ GitHub API 可访问")
                elif response.status_code == 403:
                    self.log("✗ GitHub API 速率限制")
                else:
                    self.log(f"✗ GitHub API 返回状态码: {response.status_code}")
            except Exception as e:
                self.log(f"✗ GitHub API 访问失败: {str(e)}")
            
            # 测试可能的下载链接
            possible_files = [
                "TcpTool.exe",
                "Multifun_debug_tool.exe", 
                "debug_tool.exe",
                "TcpTool.zip",
                "Multifun_debug_tool.zip"
            ]
            
            version_tags = ["latest", "v1.0.0", "1.0.0"]
            
            for tag in version_tags:
                self.log(f"测试版本标签: {tag}")
                for filename in possible_files:
                    try:
                        download_url = f"https://github.com/{repo_name}/releases/download/{tag}/{filename}"
                        response = requests.head(download_url, timeout=5)
                        if response.status_code == 200:
                            size = response.headers.get('content-length', 'Unknown')
                            self.log(f"  ✓ {filename} (大小: {size} bytes)")
                        else:
                            self.log(f"  ✗ {filename} (状态码: {response.status_code})")
                    except Exception as e:
                        self.log(f"  ✗ {filename} (错误: {str(e)})")
            
            # 重新启用按钮
            QtCore.QMetaObject.invokeMethod(
                self.test_download_btn, "setEnabled", 
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(bool, True)
            )
        
        # 在后台线程中测试
        import threading
        thread = threading.Thread(target=_test_links, daemon=True)
        thread.start()
    
    def on_update_available(self, current, latest):
        """发现新版本"""
        self.log(f"发现新版本: {current} -> {latest}")
        self.version_info.setText(f"当前版本: {current} | 最新版本: {latest}")
        self.download_btn.setEnabled(True)
    
    def on_check_finished(self, success):
        """检查完成"""
        self.check_btn.setEnabled(True)
        if success:
            self.log("版本检查完成")
        else:
            self.log("版本检查失败")
    
    def on_check_error(self, error_msg):
        """检查错误"""
        self.log(f"检查更新出错: {error_msg}")
        self.check_btn.setEnabled(True)
    
    def on_download_progress(self, progress):
        """下载进度"""
        self.progress_bar.setValue(progress)
        if progress % 10 == 0:  # 每10%记录一次
            self.log(f"下载进度: {progress}%")
    
    def on_download_finished(self, file_path):
        """下载完成"""
        self.progress_bar.setVisible(False)
        self.download_btn.setEnabled(True)
        self.log(f"下载完成: {file_path}")
        
        # 显示文件信息
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            self.log(f"文件大小: {file_size / 1024 / 1024:.2f} MB")
            
            # 询问是否打开文件夹
            reply = QtWidgets.QMessageBox.question(
                self, "下载完成", 
                f"文件已下载到:\n{file_path}\n\n是否打开文件夹？",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                import subprocess
                subprocess.run(['explorer', '/select,', file_path.replace('/', '\\')], shell=True)
    
    def on_download_error(self, error_msg):
        """下载错误"""
        self.progress_bar.setVisible(False)
        self.download_btn.setEnabled(True)
        self.log(f"下载失败: {error_msg}")
        
        QtWidgets.QMessageBox.critical(self, "下载失败", f"下载失败:\n{error_msg}")
    
    def view_logs(self):
        """查看日志"""
        try:
            log_content = self.vm.get_log_content(200)  # 获取最近200行日志
            log_file_path = self.vm.get_log_file_path()
            
            # 创建日志查看对话框
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle("版本管理器日志")
            dialog.setFixedSize(800, 600)
            
            layout = QtWidgets.QVBoxLayout(dialog)
            
            # 日志文件路径
            path_label = QtWidgets.QLabel(f"日志文件: {log_file_path}")
            path_label.setWordWrap(True)
            layout.addWidget(path_label)
            
            # 日志内容
            log_text = QtWidgets.QTextEdit()
            log_text.setReadOnly(True)
            log_text.setFont(QtWidgets.QApplication.font())
            log_text.setPlainText(log_content)
            
            # 滚动到底部
            cursor = log_text.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            log_text.setTextCursor(cursor)
            
            layout.addWidget(log_text)
            
            # 按钮
            button_layout = QtWidgets.QHBoxLayout()
            
            refresh_btn = QtWidgets.QPushButton("刷新")
            refresh_btn.clicked.connect(lambda: log_text.setPlainText(self.vm.get_log_content(200)))
            button_layout.addWidget(refresh_btn)
            
            open_file_btn = QtWidgets.QPushButton("打开日志文件")
            open_file_btn.clicked.connect(lambda: self.open_log_file(log_file_path))
            button_layout.addWidget(open_file_btn)
            
            close_btn = QtWidgets.QPushButton("关闭")
            close_btn.clicked.connect(dialog.close)
            button_layout.addWidget(close_btn)
            
            layout.addLayout(button_layout)
            
            dialog.exec()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "错误", f"查看日志失败:\n{str(e)}")
    
    def open_log_file(self, log_file_path):
        """打开日志文件"""
        try:
            import subprocess
            import os
            
            if os.path.exists(log_file_path):
                # Windows上用记事本打开
                subprocess.run(['notepad.exe', log_file_path], shell=True)
            else:
                QtWidgets.QMessageBox.warning(self, "警告", "日志文件不存在")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "错误", f"打开日志文件失败:\n{str(e)}")


def test_version_check():
    """测试版本检查功能（命令行模式）"""
    app = QtWidgets.QApplication(sys.argv)
    
    # 创建版本管理器
    vm = VersionManager("0.9.0")  # 使用较低版本进行测试
    
    def on_update_available(current, latest):
        print(f"发现新版本: {current} -> {latest}")
        app.quit()
    
    def on_check_finished(success):
        if success:
            print("版本检查完成")
        else:
            print("版本检查失败")
        app.quit()
    
    def on_check_error(error_msg):
        print(f"检查更新出错: {error_msg}")
    
    vm.update_available.connect(on_update_available)
    vm.check_finished.connect(on_check_finished)
    vm.check_error.connect(on_check_error)
    
    # 延迟检查更新
    QtCore.QTimer.singleShot(1000, vm.check_for_updates)
    
    # 10秒后自动退出（增加超时时间）
    QtCore.QTimer.singleShot(10000, app.quit)
    
    print("开始检查更新...")
    app.exec()


def test_with_gui():
    """使用GUI界面测试"""
    app = QtWidgets.QApplication(sys.argv)
    
    widget = VersionTestWidget()
    widget.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    # 检查命令行参数
    if len(sys.argv) > 1 and sys.argv[1] == '--cli':
        test_version_check()
    else:
        test_with_gui()