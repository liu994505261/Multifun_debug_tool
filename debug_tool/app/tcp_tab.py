from PySide6 import QtWidgets, QtCore, QtGui
import socket
import threading
import traceback
import queue

from app.base_comm import BaseCommTab


class TCPClientTabQt(BaseCommTab):
    server_started = QtCore.Signal()
    server_error = QtCore.Signal(str)
    client_connected = QtCore.Signal()
    client_connect_error = QtCore.Signal(str)
    connection_lost = QtCore.Signal()

    def __init__(self, get_global_format, parent=None):
        super().__init__(get_global_format, parent)
        self.sock = None
        self.connected = False
        self.recv_thread = None
        self.clients = []  # List to track connected clients
        self.clients_lock = threading.Lock() # Thread safety for clients list

        # 连接过程状态
        self._connecting = False
        self._connect_thread = None
        self._connecting_socket = None
        self._cancel_connect_flag = False
        # 连接超时管理（毫秒）
        self._connect_timeout_ms = 2000

        # Connect signals
        self.server_started.connect(self._on_server_started)
        self.server_error.connect(self._on_server_error)
        self.client_connected.connect(self._on_client_connected)
        self.client_connect_error.connect(self._on_client_connect_error)
        self.connection_lost.connect(self._on_connection_lost)

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
        self._set_label_status(self.status_label, 'error')
        row1_layout.addWidget(self.status_label)
        self.limit_display_cb = QtWidgets.QCheckBox('不显示接收')
        row1_layout.addWidget(self.limit_display_cb)

        # 醒目匹配
        row1_layout.addWidget(QtWidgets.QLabel('醒目:'))
        self.highlight_edit = QtWidgets.QLineEdit()
        self.highlight_edit.setPlaceholderText('匹配内容')
        self.highlight_edit.setMaximumWidth(100)
        row1_layout.addWidget(self.highlight_edit)
        
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
            self.limit_display_cb.toggled.connect(lambda _c: self._on_limit_toggled(_c))
            self.limit_display_cb.toggled.connect(lambda _c: self.changed.emit())
            self.highlight_edit.textChanged.connect(self._on_highlight_pattern_changed)
            self.highlight_edit.textChanged.connect(lambda _t: self.changed.emit())
        except Exception:
            pass

        self._display_limit_enabled = False
        self._display_limit_max = 10 * 1024
        self._displayed_bytes = 0

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
            self._set_label_status(self.status_label, 'error')
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

            # 异步连接
            if not host or port <= 0:
                self._log('请输入有效的服务器地址与端口', 'red')
                return

            self.status_label.setText('连接中...')
            self._set_label_status(self.status_label, 'warning')
            self.connect_btn.setText('取消') # 连接中允许取消
            self.connect_btn.setEnabled(True)
            self._connecting = True
            self._cancel_connect_flag = False

            self._log(f'正在连接到 {host}:{port} ...', 'blue')

            def do_connect():
                s = None
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self._connecting_socket = s
                    s.settimeout(2.0) # 使用2秒超时
                    s.connect((host, port))
                    s.settimeout(None)
                    
                    if self._cancel_connect_flag:
                        try: s.close() 
                        except: pass
                        return

                    self.sock = s
                    self.connected = True
                    self.client_connected.emit()

                except Exception as e:
                    if self._cancel_connect_flag:
                        return
                    msg = str(e)
                    is_timeout = isinstance(e, TimeoutError) or ('timed out' in msg.lower())
                    if is_timeout:
                        self.client_connect_error.emit(f'连接超时：请检查网络并确认 {host}:{port} ')
                    else:
                        self.client_connect_error.emit(f'连接失败: {msg}')
                    if s:
                        try: s.close()
                        except: pass
            
            self._connect_thread = threading.Thread(target=do_connect, daemon=True)
            self._connect_thread.start()

        elif mode == '服务端':
            self._log('服务端模式启动中...', 'blue')
            # 服务端逻辑保持异步
            self._connecting = True
            self._cancel_connect_flag = False
            self.connect_btn.setText('取消启动')
            self.status_label.setText('启动中...')
            self.status_label.setStyleSheet('color: orange;')

            # 获取最大连接数 (主线程操作)
            try:
                max_clients_val = int(self.max_clients_edit.text().strip() or '5')
            except Exception:
                max_clients_val = 5

            def do_server_listen():
                try:
                    if port <= 0:
                        raise Exception('请输入有效的监听端口')
                    self._log(f'服务端正在启动，监听 {host}:{port}', 'blue')
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind((host, port))
                    # 修正：使用预获取的数值，避免在线程中访问 UI
                    s.listen(max_clients_val)
                    self.sock = s
                    self.connected = True
                    
                    # Emit signal to update UI in main thread
                    self.server_started.emit()

                except Exception as e:
                    msg = str(e)
                    if 'Address already in use' in msg:
                         msg = f'端口 {port} 已被占用'
                    self.server_error.emit(msg)

            self._connect_thread = threading.Thread(target=do_server_listen)
            self._connect_thread.daemon = True
            self._connect_thread.start()

    def _on_client_connected(self):
        if self._cancel_connect_flag:
            self._disconnect()
            return
            
        host = self.host_combo.currentText().strip()
        port = self.port_combo.currentText().strip()

        self._log('已连接到服务器', 'blue')
        self._start_recv_thread()
        try:
            self._send_queue = queue.Queue(maxsize=1000)
        except Exception:
            self._send_queue = None
        self._start_send_thread()
        self.connect_btn.setText('断开')
        self.host_combo.setEnabled(False)
        self.port_combo.setEnabled(False)
        self.mode_client_rb.setEnabled(False)
        self.mode_server_rb.setEnabled(False)
        self.status_label.setText('已连接')
        self._set_label_status(self.status_label, 'success')
        self._displayed_bytes = 0
        self._add_history(self.host_combo, host)
        self._add_history(self.port_combo, str(port))
        self.changed.emit()
        self._connecting = False
        self._connect_thread = None

    def _on_client_connect_error(self, error_msg):
        if self._cancel_connect_flag:
            self._log('正在取消连接...', 'orange')
        else:
            self._log(error_msg, 'red')
        
        self.status_label.setText('未连接')
        self._set_label_status(self.status_label, 'error')
        self.connect_btn.setText('连接')
        self.connect_btn.setEnabled(True)
        if self.sock:
            try: self.sock.close()
            except: pass
        self.sock = None
        self.connected = False
        self._connecting = False
        self._connect_thread = None

    def _on_connection_lost(self):
        self._log('连接异常断开', 'red')
        self._disconnect()

    def _on_server_started(self):
        if self._cancel_connect_flag:
            self._disconnect()
            return
        
        # Need to retrieve host/port for logging/display. 
        # Since they are UI elements, we can access them here safely (main thread).
        host = self.host_combo.currentText().strip()
        port = self.port_combo.currentText().strip()
        
        self._log(f'服务端启动成功，正在监听 {host}:{port}', 'green')
        
        # Start accept thread
        threading.Thread(target=self._accept_loop, daemon=True).start()
        
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

    def _on_server_error(self, error_msg):
        if self._cancel_connect_flag:
            self._log('已取消启动', 'orange')
        else:
            self._log(f'启动失败: {error_msg}', 'red')
        
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

    def _disconnect(self):
        self.connected = False
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        self.sock = None
        
        # Close all connected clients
        with self.clients_lock:
            for client in self.clients:
                try:
                    client.close()
                except:
                    pass
            self.clients.clear()

        try:
            self._send_queue = None
        except Exception:
            pass
        self._log('连接已断开/服务已停止', 'blue')
        self.connect_btn.setText('连接')
        self.host_combo.setEnabled(True)
        self.port_combo.setEnabled(True)
        self.mode_client_rb.setEnabled(True)
        self.mode_server_rb.setEnabled(True)
        self.status_label.setText('未连接')
        self.status_label.setStyleSheet('color: red;')
        self._displayed_bytes = 0

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
                    if not self._display_limit_enabled:
                        self._update_recv_stats(len(data))
                        self._log(self._format_recv(data), 'green')
                    self.data_received.emit(data)
                except Exception as e:
                    if self.connected:
                        self._log(f'接收错误: {e}', 'red')
                        self.connection_lost.emit()
                    break
            self.connected = False
        self.recv_thread = threading.Thread(target=loop, daemon=True)
        self.recv_thread.start()

    def _accept_loop(self):
        try:
            while self.connected and self.sock:
                try:
                    client, addr = self.sock.accept()
                    self._log(f'客户端连接: {addr[0]}:{addr[1]}', 'blue')
                    with self.clients_lock:
                        self.clients.append(client)
                    threading.Thread(target=self._handle_client, args=(client, addr), daemon=True).start()
                except OSError:
                    # Socket closed
                    break
                except Exception as e:
                    if self.connected:
                        self._log(f'服务端Accept错误: {e}', 'red')
        except Exception as e:
            if self.connected:
                self._log(f'服务端错误: {e}', 'red')

    def _handle_client(self, client: socket.socket, addr):
        try:
            while self.connected:
                try:
                    data = client.recv(4096)
                except OSError:
                    break
                
                if not data:
                    break
                if not self._display_limit_enabled:
                    self._update_recv_stats(len(data))
                    self._log(f'来自 {addr[0]}:{addr[1]}: ' + self._format_recv(data), 'green')
                self.data_received.emit(data)
        except Exception as e:
            self._log(f'客户端 {addr[0]}:{addr[1]} 错误: {e}', 'red')
        finally:
            self._log(f'客户端断开: {addr[0]}:{addr[1]}', 'orange')
            with self.clients_lock:
                if client in self.clients:
                    self.clients.remove(client)
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
        fmt = row['fmt_combo'].currentText()
        data = self._parse_send_data(row['data_edit'].text(), fmt)
        try:
            if not self.sock:
                self._log('未连接', 'red')
                return
            # 客户端或服务端：都向当前 socket 发送（服务端为广播可后续扩展）
            if self._current_mode() == '客户端':
                q = getattr(self, '_send_queue', None)
                if q:
                    try:
                        q.put_nowait((fmt, data))
                    except Exception:
                        pass
                else:
                    # 兜底：无队列时直接发送
                    self.sock.sendall(data)
                    if not self._display_limit_enabled:
                        self._log(self._format_by(data, fmt), 'blue')
            else:
                # 服务端广播发送
                if not self.clients:
                    self._log('无客户端连接，无法发送', 'orange')
                    return
                
                success_count = 0
                with self.clients_lock:
                    # Copy list to avoid issues if modifications happen during iteration (though lock prevents it)
                    current_clients = list(self.clients)
                
                for client in current_clients:
                    try:
                        client.sendall(data)
                        success_count += 1
                    except Exception as e:
                        # Wait for _handle_client to remove it, or we could remove it here?
                        # Better let the receive loop handle disconnection to avoid race conditions
                        pass
                
                if not self._display_limit_enabled:
                    self._log(f'广播发送给 {success_count} 个客户端: ' + self._format_by(data, fmt), 'blue')

        except Exception as e:
            self._log(f'发送失败: {e}', 'red')

    def shutdown(self):
        super().shutdown()
        self._disconnect()

    def _start_send_thread(self):
        def loop():
            q = getattr(self, '_send_queue', None)
            while self.connected and self.sock:
                try:
                    item = q.get(timeout=0.2) if q else None
                except Exception:
                    item = None
                if not item:
                    continue
                fmt, data = item
                try:
                    self.sock.sendall(data)
                    if not self._display_limit_enabled:
                        def log_sent():
                            self._log(self._format_by(data, fmt), 'blue')
                        QtCore.QTimer.singleShot(0, log_sent)
                except Exception as e:
                    def on_err():
                        self._log(f'发送失败: {e}', 'red')
                    QtCore.QTimer.singleShot(0, on_err)
                    break
        try:
            self.send_thread = threading.Thread(target=loop, daemon=True)
            self.send_thread.start()
        except Exception:
            pass

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

    def _on_limit_toggled(self, checked: bool):
        try:
            self._display_limit_enabled = bool(checked)
            if self._display_limit_enabled:
                self._displayed_bytes = 0
        except Exception:
            pass

    def _on_highlight_pattern_changed(self, text):
        self.highlight_pattern = text
