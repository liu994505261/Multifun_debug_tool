#!/usr/bin/env python3
import os
import re
import json
import argparse
from datetime import datetime
from subprocess import run

# 脚本版本号
SCRIPT_VERSION = "1.1.0"


def read_project_version(root_dir):
    """从根目录的 CMakeLists.txt 中读取 PROJECT_VER 版本号，若不存在则返回 None"""
    cmake_path = os.path.join(root_dir, "CMakeLists.txt")
    version = None
    try:
        with open(cmake_path, "r") as f:
            content = f.read()
            # 匹配 set(PROJECT_VER "x.y.z") 或 set(PROJECT_VER x.y.z)
            match = re.search(r'set\s*\(\s*PROJECT_VER\s+["\']?([^"\')\s]+)["\']?\s*\)', content)
            if match:
                version = match.group(1)
    except Exception as e:
        print(f"读取版本号失败: {e}")
    if version is None:
        print("提示: CMakeLists.txt 中未定义 PROJECT_VER，输出文件名将不包含版本号")
    return version


def get_datetime_hour_str():
    """返回当前日期+小时字符串，格式 YYYYMMDD_HH (24小时制)"""
    return datetime.now().strftime("%Y%m%d_%H")


def read_firmware_from_flasher_args(build_dir):
    """
    从 build/flasher_args.json 读取固件文件列表和对应的烧录偏移地址
    :param build_dir: build 目录的绝对路径
    :return: (firmware_files, offsets) 元组，失败返回 (None, None)
    """
    flasher_json = os.path.join(build_dir, "flasher_args.json")
    if not os.path.exists(flasher_json):
        print(f"错误: 找不到 {flasher_json}，请先执行 idf.py build")
        return None, None

    with open(flasher_json, "r") as f:
        data = json.load(f)

    flash_files = data.get("flash_files", {})
    if not flash_files:
        print("错误: flasher_args.json 中没有 flash_files 信息")
        return None, None

    # 解析条目并按偏移地址排序
    entries = []
    for offset_str, file_path in flash_files.items():
        offset = int(offset_str, 16)
        # flasher_args.json 中的路径相对于 build 目录
        full_path = os.path.join("build", file_path)
        entries.append((offset, full_path))

    entries.sort(key=lambda x: x[0])

    offsets = [e[0] for e in entries]
    firmware_files = [e[1] for e in entries]

    print(f"从 flasher_args.json 读取到 {len(firmware_files)} 个固件文件:")
    for path, offset in zip(firmware_files, offsets):
        print(f"  0x{offset:05X}  {path}")

    return firmware_files, offsets


def merge_esp32_firmwares(firmware_files, offsets, output_file):
    """
    合并ESP32固件文件
    :param firmware_files: 要合并的固件文件列表
    :param offsets: 每个固件文件的偏移地址列表
    :param output_file: 合并后的输出文件路径
    """
    # 确定合并后固件的最大长度
    max_length = 0
    for i in range(len(firmware_files)):
        with open(firmware_files[i], "rb") as f:
            firmware_data = f.read()
            end_address = offsets[i] + len(firmware_data)
            if end_address > max_length:
                max_length = end_address

    # 创建一个空白的合并后固件数据缓冲区
    merged_firmware = bytearray(max_length)

    # 依次读取每个固件文件并合并到缓冲区
    for i in range(len(firmware_files)):
        with open(firmware_files[i], "rb") as f:
            firmware_data = f.read()
            # 将固件数据写入缓冲区的指定偏移位置
            merged_firmware[offsets[i] : offsets[i] + len(firmware_data)] = (
                firmware_data
            )

    # 将合并后的固件数据写入输出文件
    # 确保输出目录存在
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(output_file, "wb") as f:
        f.write(merged_firmware)
    print(f"合并完成，合并后的固件已保存到 {output_file}")


if __name__ == "__main__":
    print("  /\\___/\\")
    print(" (  o   o  )")
    print(" (  =^_^=  )   ESP32 Release Output Tool  v" + SCRIPT_VERSION)
    print("  (______)")
    print("=" * 56)

    # 设置当前目录为项目根目录
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root_dir)
    print(f"  工作目录: {os.getcwd()}")

    # 读取版本号（可能为 None）
    version = read_project_version(root_dir)
    datetime_hour = get_datetime_hour_str()

    # 项目名称（可根据需要修改或从 CMakeLists.txt 解析 project()）
    project_name = "stamp_dev"

    # 构造输出文件名
    if version:
        output_filename = f"merged_firmware-{project_name}-V{version}-{datetime_hour}.bin"
    else:
        output_filename = f"merged_firmware-{project_name}-{datetime_hour}.bin"

    output_file = os.path.join("scripts", output_filename)

    # 从 flasher_args.json 读取固件文件列表和偏移地址
    firmware_files, offsets = read_firmware_from_flasher_args(os.path.join(root_dir, "build"))
    if firmware_files is None:
        exit(1)

    # 检查所有固件文件是否存在
    for fw in firmware_files:
        if not os.path.exists(fw):
            print(f"错误: 找不到 {fw}")
            exit(1)

    # 执行合并
    merge_esp32_firmwares(firmware_files, offsets, output_file)