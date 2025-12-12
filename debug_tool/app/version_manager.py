#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本管理模块
自动检查GitHub Release页面的最新版本，下载并更新应用程序
"""

import json
import os
import sys
import tempfile
import threading
import time
import zipfile
import logging
from datetime import datetime
from typing import Optional, Callable
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None
    REQUESTS_AVAILABLE = False
from PySide6 import QtCore, QtWidgets


class VersionManagerLogger:
    """版本管理器日志记录器"""
    
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        self.log_file = os.path.join(log_dir, "version_manager.log")
        self.file_handler = None
        
        # 确保日志目录存在
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            print(f"创建日志目录失败: {e}")
            # 如果无法创建目录，使用临时目录
            import tempfile
            self.log_dir = tempfile.gettempdir()
            self.log_file = os.path.join(self.log_dir, "version_manager.log")
        
        # 配置日志记录器
        self.logger = logging.getLogger('VersionManager')
        self.logger.setLevel(logging.DEBUG)
        
        # 避免重复添加handler
        if not self.logger.handlers:
            # 尝试创建文件处理器
            try:
                self.file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
                self.file_handler.setLevel(logging.DEBUG)
                
                # 格式化器
                formatter = logging.Formatter(
                    '%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                
                self.file_handler.setFormatter(formatter)
                self.logger.addHandler(self.file_handler)
                
                # 测试写入权限
                self.logger.info("日志系统初始化成功")
                
            except Exception as e:
                print(f"创建文件日志处理器失败: {e}")
                self.file_handler = None
            
            # 控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
    
    def info(self, message: str):
        """记录信息日志"""
        self.logger.info(message)
    
    def warning(self, message: str):
        """记录警告日志"""
        self.logger.warning(message)
    
    def error(self, message: str, exception: Exception = None):
        """记录错误日志"""
        if exception:
            self.logger.error(f"{message}: {str(exception)}", exc_info=True)
        else:
            self.logger.error(message)
    
    def debug(self, message: str):
        """记录调试日志"""
        self.logger.debug(message)
    
    def log_operation_start(self, operation: str, **kwargs):
        """记录操作开始"""
        details = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        self.info(f"开始{operation} - {details}")
    
    def log_operation_success(self, operation: str, **kwargs):
        """记录操作成功"""
        details = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        self.info(f"{operation}成功 - {details}")
    
    def log_operation_failure(self, operation: str, error: str, **kwargs):
        """记录操作失败"""
        details = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        self.error(f"{operation}失败 - {error} - {details}")
    
    def get_log_content(self, lines: int = 100) -> str:
        """获取日志内容"""
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    all_lines = f.readlines()
                    return ''.join(all_lines[-lines:])
            return f"日志文件不存在: {self.log_file}"
        except Exception as e:
            return f"读取日志文件失败: {str(e)}\n日志文件路径: {self.log_file}"
    
    def clear_old_logs(self, days: int = 7):
        """清理旧日志（保留最近N天）"""
        try:
            if os.path.exists(self.log_file):
                # 获取文件修改时间
                file_time = os.path.getmtime(self.log_file)
                current_time = time.time()
                
                # 如果文件超过指定天数，清空内容
                if (current_time - file_time) > (days * 24 * 3600):
                    with open(self.log_file, 'w', encoding='utf-8') as f:
                        f.write(f"# 日志已于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 清理\n")
                    self.info("旧日志已清理")
        except Exception as e:
            self.error("清理旧日志失败", e)


class VersionManager(QtCore.QObject):
    """版本管理器"""
    
    # 信号定义
    update_available = QtCore.Signal(str, str)  # (current_version, latest_version)
    check_finished = QtCore.Signal(bool)  # 检查完成，参数为是否成功
    check_error = QtCore.Signal(str)  # 检查错误
    download_progress = QtCore.Signal(int)  # 下载进度 0-100
    download_finished = QtCore.Signal(str)  # 下载完成，参数为文件路径
    download_error = QtCore.Signal(str)  # 下载错误
    update_finished = QtCore.Signal()  # 更新完成
    update_error = QtCore.Signal(str)  # 更新错误
    
    def __init__(self, current_version: str = None, repo_url: str = "https://github.com/liu994505261/Multifun_debug_tool"):
        super().__init__()
        
        # 自动获取当前版本
        if current_version is None:
            current_version = self._get_current_version()
        
        self.current_version = current_version
        self.repo_url = repo_url.rstrip('.git')
        self.api_url = f"https://api.github.com/repos/liu994505261/Multifun_debug_tool/releases/latest"
        self.temp_dir = os.path.join(tempfile.gettempdir(), "multifun_debug_tool_update")
        self.download_thread = None
        self.update_thread = None
        
        # 缓存相关
        self.cache_file = os.path.join(self.temp_dir, "version_cache.json")
        self.cache_duration = 7200  # 2小时缓存，减少API调用频率
        
        # GitHub token (可选，用于提高API速率限制)
        self.github_token = self._get_github_token()
        
        # 日志记录器 - 使用exe当前目录
        log_dir = self._get_exe_directory()
        self.logger = VersionManagerLogger(log_dir)
        
        # 确保临时目录存在
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # 记录初始化信息
        self.logger.info(f"版本管理器初始化完成")
        self.logger.debug(f"当前版本: {self.current_version}")
        self.logger.debug(f"仓库URL: {self.repo_url}")
        self.logger.debug(f"API URL: {self.api_url}")
        self.logger.debug(f"临时目录: {self.temp_dir}")
        self.logger.debug(f"日志目录: {log_dir}")
        self.logger.debug(f"日志文件: {self.logger.log_file}")
        self.logger.debug(f"GitHub Token: {'已配置' if self.github_token else '未配置'}")
        
        # 清理旧日志
        self.logger.clear_old_logs()
    
    def _get_current_version(self) -> str:
        """从__version__模块获取当前应用版本"""
        try:
            from .__version__ import __version__
            return __version__
        except ImportError as e:
            # 如果__version__模块不存在，返回默认版本
            default_version = "1.0.0"
            # 注意：这里还没有初始化logger，所以使用print
            print(f"无法获取版本信息，使用默认版本 {default_version}: {e}")
            return default_version
    
    def _get_exe_directory(self) -> str:
        """获取exe文件所在目录"""
        try:
            if getattr(sys, 'frozen', False):
                # 如果是打包后的exe文件
                exe_dir = os.path.dirname(sys.executable)
            else:
                # 如果是开发环境，使用项目根目录
                exe_dir = os.path.dirname(os.path.dirname(__file__))  # 从app目录向上两级到debug_tool目录
            
            # 确保目录存在
            os.makedirs(exe_dir, exist_ok=True)
            return exe_dir
        except Exception as e:
            # 如果获取失败，回退到临时目录
            print(f"获取exe目录失败，使用临时目录: {e}")
            return self.temp_dir
    
    def _get_github_token(self) -> Optional[str]:
        """获取GitHub token，优先级：环境变量 > 配置文件"""
        # 首先尝试环境变量
        token = os.environ.get('GITHUB_TOKEN')
        if token:
            return token
        
        # 然后尝试配置文件
        try:
            config_path = os.path.join(os.path.dirname(__file__), '..', 'github_config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('github_token')
        except Exception as e:
            # 注意：这里还没有初始化logger，所以使用print
            print(f"读取GitHub配置文件失败: {e}")
        
        return None
    
    def _get_cached_release_data(self):
        """获取缓存的release数据"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    
                # 检查缓存是否过期
                cache_age = time.time() - cache_data.get('timestamp', 0)
                if cache_age < self.cache_duration:
                    self.logger.debug(f"使用缓存数据，缓存年龄: {cache_age:.0f}秒")
                    return cache_data.get('data')
                else:
                    self.logger.debug(f"缓存已过期，缓存年龄: {cache_age:.0f}秒")
        except Exception as e:
            self.logger.error("读取缓存数据失败", e)
        return None
    
    def _get_old_cache_data(self):
        """获取旧缓存数据（即使过期也返回）"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    cache_age = time.time() - cache_data.get('timestamp', 0)
                    self.logger.debug(f"获取旧缓存数据，缓存年龄: {cache_age:.0f}秒")
                    return cache_data.get('data')
        except Exception as e:
            self.logger.error("读取旧缓存数据失败", e)
        return None
    
    def _save_release_data_to_cache(self, data):
        """保存release数据到缓存"""
        try:
            cache_data = {
                'timestamp': time.time(),
                'data': data
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            self.logger.debug("release数据已保存到缓存")
        except Exception as e:
            self.logger.error("保存release数据到缓存失败", e)
    
    def check_for_updates(self) -> None:
        """检查更新（在后台线程中执行）"""
        def _check():
            if not REQUESTS_AVAILABLE:
                self.logger.warning("Requests library not found, skipping update check")
                self.check_error.emit("Requests library not found")
                self.check_finished.emit(False)
                return

            self.logger.log_operation_start("检查更新", current_version=self.current_version)
            
            try:
                # 首先尝试从缓存获取数据
                release_data = self._get_cached_release_data()
                
                if release_data is None:
                    self.logger.info("缓存不存在或已过期，从GitHub API获取数据")
                    
                    # 缓存不存在或已过期，从API获取
                    headers = {
                        'User-Agent': 'Multifun-Debug-Tool/1.0',
                        'Accept': 'application/vnd.github.v3+json'
                    }
                    
                    # 如果有GitHub token，添加到headers中
                    if self.github_token:
                        headers['Authorization'] = f'token {self.github_token}'
                        self.logger.debug("使用GitHub Token进行API调用")
                    else:
                        self.logger.warning("未配置GitHub Token，可能遇到API速率限制")
                    
                    self.logger.debug(f"请求URL: {self.api_url}")
                    response = requests.get(self.api_url, headers=headers, timeout=10)
                    self.logger.debug(f"API响应状态码: {response.status_code}")
                    
                    # 检查是否遇到速率限制
                    if response.status_code == 403:
                        try:
                            error_data = response.json()
                            if 'rate limit exceeded' in error_data.get('message', '').lower():
                                self.logger.warning("遇到GitHub API速率限制")
                                
                                # 尝试使用旧缓存数据
                                old_cache = self._get_old_cache_data()
                                if old_cache:
                                    self.logger.info("使用旧缓存数据继续检查")
                                    latest_version = old_cache.get('tag_name', '').lstrip('vV')
                                    
                                    if self._is_newer_version(latest_version, self.current_version):
                                        self.logger.log_operation_success("检查更新", 
                                                                        current_version=self.current_version,
                                                                        latest_version=latest_version,
                                                                        source="旧缓存")
                                        self.update_available.emit(self.current_version, latest_version)
                                    else:
                                        self.logger.info(f"当前版本 {self.current_version} 已是最新版本（基于旧缓存）")
                                    
                                    self.check_finished.emit(True)
                                    return
                                else:
                                    error_msg = "GitHub API速率限制已达到，且无可用缓存数据"
                                    self.logger.log_operation_failure("检查更新", error_msg)
                                    self.check_error.emit("GitHub API速率限制已达到，请稍后再试或设置GITHUB_TOKEN环境变量")
                                    self.check_finished.emit(False)
                                    return
                        except Exception as parse_error:
                            self.logger.error("解析API错误响应失败", parse_error)
                    
                    response.raise_for_status()
                    release_data = response.json()
                    self.logger.debug(f"获取到release数据: {release_data.get('tag_name', 'Unknown')}")
                    
                    # 保存到缓存
                    self._save_release_data_to_cache(release_data)
                else:
                    self.logger.info("使用缓存数据进行版本检查")
                
                latest_version = release_data.get('tag_name', '').lstrip('vV')
                self.logger.debug(f"最新版本: {latest_version}, 当前版本: {self.current_version}")
                
                if self._is_newer_version(latest_version, self.current_version):
                    # 发出更新可用信号
                    self.logger.log_operation_success("检查更新", 
                                                    current_version=self.current_version,
                                                    latest_version=latest_version,
                                                    source="API" if release_data else "缓存")
                    self.update_available.emit(self.current_version, latest_version)
                else:
                    self.logger.info(f"当前版本 {self.current_version} 已是最新版本")
                
                self.check_finished.emit(True)
                    
            except requests.exceptions.RequestException as e:
                if "rate limit" in str(e).lower():
                    error_msg = "GitHub API速率限制已达到，请稍后再试"
                    self.logger.log_operation_failure("检查更新", error_msg)
                    self.check_error.emit(error_msg)
                else:
                    error_msg = f"网络请求失败: {str(e)}"
                    self.logger.log_operation_failure("检查更新", error_msg)
                    self.check_error.emit(f"检查更新失败: {e}")
                self.check_finished.emit(False)
            except Exception as e:
                error_msg = f"检查更新时发生未知错误: {str(e)}"
                self.logger.log_operation_failure("检查更新", error_msg)
                self.check_error.emit(f"检查更新失败: {e}")
                self.check_finished.emit(False)
        
        # 在后台线程中执行检查
        thread = threading.Thread(target=_check, daemon=True)
        thread.start()
    
    def _is_newer_version(self, latest: str, current: str) -> bool:
        """比较版本号，判断是否有新版本"""
        try:
            def version_tuple(v):
                return tuple(map(int, v.split('.')))
            return version_tuple(latest) > version_tuple(current)
        except:
            return latest != current
    
    def download_latest_release(self) -> None:
        """下载最新版本"""
        if self.download_thread and self.download_thread.is_alive():
            self.logger.warning("下载线程已在运行，忽略重复请求")
            return
            
        def _download():
            if not REQUESTS_AVAILABLE:
                self.logger.warning("Requests library not found, skipping download")
                self.download_error.emit("Requests library not found")
                return
            self.logger.log_operation_start("下载最新版本")
            
            try:
                # 首先尝试从缓存获取release信息
                release_data = self._get_cached_release_data()
                
                if release_data is None:
                    self.logger.info("缓存不存在，从API获取release信息")
                    
                    # 缓存不存在，尝试从API获取
                    headers = {
                        'User-Agent': 'Multifun-Debug-Tool/1.0',
                        'Accept': 'application/vnd.github.v3+json'
                    }
                    
                    # 如果有GitHub token，添加到headers中
                    if self.github_token:
                        headers['Authorization'] = f'token {self.github_token}'
                        self.logger.debug("使用GitHub Token获取release信息")
                    
                    response = requests.get(self.api_url, headers=headers, timeout=10)
                    self.logger.debug(f"API响应状态码: {response.status_code}")
                    
                    # 检查是否遇到速率限制
                    if response.status_code == 403:
                        try:
                            error_data = response.json()
                            if 'rate limit exceeded' in error_data.get('message', '').lower():
                                self.logger.warning("遇到API速率限制，使用备用下载方案")
                                # 尝试使用备用方案：直接构造下载链接
                                self._download_with_fallback()
                                return
                        except Exception as parse_error:
                            self.logger.error("解析API错误响应失败", parse_error)
                    
                    response.raise_for_status()
                    release_data = response.json()
                    
                    # 保存到缓存
                    self._save_release_data_to_cache(release_data)
                else:
                    self.logger.info("使用缓存的release信息")
                
                # 查找Windows可执行文件
                assets = release_data.get('assets', [])
                self.logger.debug(f"找到 {len(assets)} 个资源文件")
                
                download_url = None
                filename = None
                
                for asset in assets:
                    name = asset.get('name', '').lower()
                    self.logger.debug(f"检查资源文件: {name}")
                    if name.endswith('.exe') or name.endswith('.zip'):
                        download_url = asset.get('browser_download_url')
                        filename = asset.get('name')
                        self.logger.info(f"找到可下载文件: {filename}")
                        break
                
                if not download_url:
                    self.logger.warning("未在release中找到可执行文件，使用备用下载方案")
                    # 如果没有找到资源，尝试备用方案
                    self._download_with_fallback()
                    return
                
                # 下载文件
                self.logger.info(f"开始下载文件: {filename}")
                self._download_file(download_url, filename)
                
            except Exception as e:
                self.logger.error("主下载方案失败，尝试备用方案", e)
                # 如果API方式失败，尝试备用方案
                try:
                    self._download_with_fallback()
                except Exception as fallback_error:
                    error_msg = f"下载失败: {str(e)}\n备用方案也失败: {str(fallback_error)}"
                    self.logger.log_operation_failure("下载最新版本", error_msg)
                    self.download_error.emit(error_msg)
        
        self.download_thread = threading.Thread(target=_download, daemon=True)
        self.download_thread.start()
    
    def _download_with_fallback(self):
        """备用下载方案：直接构造GitHub Release下载链接"""
        if not REQUESTS_AVAILABLE:
            raise Exception("Requests library not found")
        self.logger.log_operation_start("备用下载方案")
        
        try:
            # 构造可能的下载链接
            repo_name = "liu994505261/Multifun_debug_tool"
            
            # 尝试几种常见的文件名模式
            possible_files = [
                "TcpTool.exe",
                "Multifun_debug_tool.exe", 
                "debug_tool.exe",
                "TcpTool.zip",
                "Multifun_debug_tool.zip"
            ]
            
            # 尝试最新版本标签
            version_tags = ["latest", "v1.0.0", "1.0.0"]
            
            download_success = False
            
            for tag in version_tags:
                self.logger.debug(f"尝试版本标签: {tag}")
                for filename in possible_files:
                    try:
                        download_url = f"https://github.com/{repo_name}/releases/download/{tag}/{filename}"
                        self.logger.debug(f"检查下载链接: {download_url}")
                        
                        # 先检查文件是否存在
                        head_response = requests.head(download_url, timeout=10)
                        if head_response.status_code == 200:
                            file_size = head_response.headers.get('content-length', 'Unknown')
                            self.logger.info(f"找到可用文件: {filename} (大小: {file_size} bytes)")
                            
                            # 文件存在，开始下载
                            self._download_file(download_url, filename)
                            download_success = True
                            break
                        else:
                            self.logger.debug(f"文件不存在: {filename} (状态码: {head_response.status_code})")
                    except Exception as check_error:
                        self.logger.debug(f"检查文件失败: {filename} - {str(check_error)}")
                        continue
                
                if download_success:
                    break
            
            if not download_success:
                # 如果所有尝试都失败，提供手动下载链接
                manual_url = f"https://github.com/{repo_name}/releases/latest"
                error_msg = f"自动下载失败，可能是GitHub API速率限制。请手动访问以下链接下载最新版本：\n{manual_url}"
                self.logger.log_operation_failure("备用下载方案", "所有下载链接都不可用")
                self.download_error.emit(error_msg)
            else:
                self.logger.log_operation_success("备用下载方案", filename=filename)
                
        except Exception as e:
            error_msg = f"备用下载方案失败: {str(e)}"
            self.logger.log_operation_failure("备用下载方案", error_msg)
            raise Exception(error_msg)
    
    def _download_file(self, download_url: str, filename: str):
        """下载文件的通用方法"""
        if not REQUESTS_AVAILABLE:
            raise Exception("Requests library not found")
        file_path = os.path.join(self.temp_dir, filename)
        self.logger.log_operation_start("下载文件", url=download_url, filename=filename, path=file_path)
        
        # 添加重试机制
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.logger.debug(f"开始下载尝试 {attempt + 1}/{max_retries}")
                
                response = requests.get(download_url, stream=True, timeout=30)
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                self.logger.info(f"文件总大小: {total_size} bytes ({total_size / 1024 / 1024:.2f} MB)")
                
                downloaded = 0
                start_time = time.time()
                
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                progress = int((downloaded / total_size) * 100)
                                self.download_progress.emit(progress)
                                
                                # 每10%记录一次进度
                                if progress % 10 == 0 and progress > 0:
                                    elapsed = time.time() - start_time
                                    speed = downloaded / elapsed / 1024  # KB/s
                                    self.logger.debug(f"下载进度: {progress}%, 速度: {speed:.1f} KB/s")
                
                download_time = time.time() - start_time
                avg_speed = downloaded / download_time / 1024  # KB/s
                
                # 验证下载的文件
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    actual_size = os.path.getsize(file_path)
                    self.logger.log_operation_success("下载文件", 
                                                    filename=filename,
                                                    size=f"{actual_size} bytes",
                                                    time=f"{download_time:.1f}s",
                                                    speed=f"{avg_speed:.1f} KB/s")
                    self.download_finished.emit(file_path)
                    return
                else:
                    raise Exception("下载的文件为空或不存在")
                    
            except Exception as e:
                self.logger.warning(f"下载尝试 {attempt + 1} 失败: {str(e)}")
                if attempt == max_retries - 1:  # 最后一次尝试
                    self.logger.log_operation_failure("下载文件", f"所有重试都失败: {str(e)}")
                    self.download_error.emit(f"下载失败: {str(e)}")
                    raise e
                else:
                    self.logger.info(f"等待2秒后重试...")
                    time.sleep(2)  # 等待2秒后重试
    
    def install_update(self, file_path: str) -> None:
        """安装更新"""
        if self.update_thread and self.update_thread.is_alive():
            self.logger.warning("更新线程已在运行，忽略重复请求")
            return
            
        def _install():
            self.logger.log_operation_start("安装更新", file_path=file_path)
            
            try:
                current_exe = sys.executable if getattr(sys, 'frozen', False) else None
                
                if not current_exe:
                    error_msg = "无法确定当前可执行文件路径"
                    self.logger.log_operation_failure("安装更新", error_msg)
                    self.update_error.emit(error_msg)
                    return
                
                current_dir = os.path.dirname(current_exe)
                self.logger.debug(f"当前可执行文件: {current_exe}")
                self.logger.debug(f"当前目录: {current_dir}")
                
                if file_path.endswith('.zip'):
                    self.logger.info("处理ZIP文件")
                    # 解压ZIP文件
                    extract_dir = os.path.join(self.temp_dir, "extracted")
                    os.makedirs(extract_dir, exist_ok=True)
                    
                    with zipfile.ZipFile(file_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_dir)
                        self.logger.debug(f"ZIP文件已解压到: {extract_dir}")
                    
                    # 查找解压后的exe文件
                    new_exe = None
                    for root, dirs, files in os.walk(extract_dir):
                        for file in files:
                            if file.endswith('.exe'):
                                new_exe = os.path.join(root, file)
                                self.logger.debug(f"找到可执行文件: {new_exe}")
                                break
                        if new_exe:
                            break
                    
                    if not new_exe:
                        error_msg = "解压后未找到可执行文件"
                        self.logger.log_operation_failure("安装更新", error_msg)
                        self.update_error.emit(error_msg)
                        return
                        
                elif file_path.endswith('.exe'):
                    self.logger.info("处理EXE文件")
                    new_exe = file_path
                else:
                    error_msg = f"不支持的文件格式: {file_path}"
                    self.logger.log_operation_failure("安装更新", error_msg)
                    self.update_error.emit("不支持的文件格式")
                    return
                
                # 验证新文件
                if not os.path.exists(new_exe):
                    error_msg = f"新可执行文件不存在: {new_exe}"
                    self.logger.log_operation_failure("安装更新", error_msg)
                    self.update_error.emit("新可执行文件不存在")
                    return
                
                new_file_size = os.path.getsize(new_exe)
                self.logger.info(f"新文件大小: {new_file_size} bytes ({new_file_size / 1024 / 1024:.2f} MB)")
                
                # 备份当前文件
                backup_path = current_exe + '.backup'
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                    self.logger.debug("删除旧备份文件")
                
                self.logger.info("创建当前文件备份")
                os.rename(current_exe, backup_path)
                
                # 复制新文件
                self.logger.info("复制新文件到当前位置")
                import shutil
                shutil.copy2(new_exe, current_exe)
                
                # 验证安装
                if os.path.exists(current_exe):
                    installed_size = os.path.getsize(current_exe)
                    self.logger.log_operation_success("安装更新", 
                                                    new_file=current_exe,
                                                    size=f"{installed_size} bytes",
                                                    backup=backup_path)
                    self.update_finished.emit()
                else:
                    error_msg = "安装后文件不存在"
                    self.logger.log_operation_failure("安装更新", error_msg)
                    self.update_error.emit(error_msg)
                
            except Exception as e:
                error_msg = f"安装更新失败: {str(e)}"
                self.logger.log_operation_failure("安装更新", error_msg)
                self.update_error.emit(error_msg)
        
        self.update_thread = threading.Thread(target=_install, daemon=True)
        self.update_thread.start()
    
    def get_log_content(self, lines: int = 100) -> str:
        """获取日志内容"""
        return self.logger.get_log_content(lines)
    
    def get_log_file_path(self) -> str:
        """获取日志文件路径"""
        return self.logger.log_file


class UpdateDialog(QtWidgets.QDialog):
    """更新对话框"""
    
    def __init__(self, current_version: str, latest_version: str, parent=None):
        super().__init__(parent)
        self.current_version = current_version
        self.latest_version = latest_version
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("发现新版本")
        self.setFixedSize(400, 200)
        self.setModal(True)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # 版本信息
        info_label = QtWidgets.QLabel(
            f"发现新版本！\n\n"
            f"当前版本: {self.current_version}\n"
            f"最新版本: {self.latest_version}\n\n"
            f"是否现在下载并更新？"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 按钮
        button_layout = QtWidgets.QHBoxLayout()
        
        self.yes_btn = QtWidgets.QPushButton("是")
        self.no_btn = QtWidgets.QPushButton("否")
        self.later_btn = QtWidgets.QPushButton("稍后提醒")
        
        self.yes_btn.clicked.connect(self.accept)
        self.no_btn.clicked.connect(self.reject)
        self.later_btn.clicked.connect(self.ignore)
        
        button_layout.addWidget(self.yes_btn)
        button_layout.addWidget(self.no_btn)
        button_layout.addWidget(self.later_btn)
        
        layout.addLayout(button_layout)
    
    def ignore(self):
        self.done(2)  # 返回2表示稍后提醒


class DownloadProgressDialog(QtWidgets.QDialog):
    """下载进度对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("下载更新")
        self.setFixedSize(350, 120)
        self.setModal(True)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        self.status_label = QtWidgets.QLabel("正在下载更新...")
        layout.addWidget(self.status_label)
        
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        
        self.cancel_btn = QtWidgets.QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        layout.addWidget(self.cancel_btn)
    
    def update_progress(self, value: int):
        self.progress_bar.setValue(value)
        self.status_label.setText(f"正在下载更新... {value}%")
    
    def set_status(self, status: str):
        self.status_label.setText(status)