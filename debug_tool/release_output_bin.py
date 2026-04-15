#!/usr/bin/env python3
import os
import argparse
from subprocess import run

# 默认烧录地址（ESP32S3通用配置）
DEFAULT_OFFSETS = {
    "bootloader.bin": 0x0000,
    "partitions.bin": 0x8000,
    "firmware.bin": 0x10000,
    "generated_assets.bin": 0x800000,
}


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
    with open(output_file, "wb") as f:
        f.write(merged_firmware)
    print(f"合并完成，合并后的固件已保存到 {output_file}")


if __name__ == "__main__":
    # firmware_files = ["bootloader.bin",  "partitions.bin",  "firmware.bin"]
    firmware_files = [
        "build/bootloader/bootloader.bin",
        "build/partition_table/partition-table.bin",
        "build/minimax.bin",
        "build/generated_assets.bin",
    ]
    offsets = [0x0000, 0x8000, 0x200000, 0xA00000]
    output_file = "scripts/merged_firmware.bin"
    # 设置当前目录为项目根目录
    # 通过多次dirname回溯到项目根目录
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root_dir)
    current_dir = os.getcwd()
    print("当前目录：", current_dir)

    # 判断boot 文件是否存在
    if os.path.exists(firmware_files[0]):
        print("bootloader.bin 存在")
        # merge_esp32_firmwares(firmware_files, offsets, output_file)
    merge_esp32_firmwares(firmware_files, offsets, output_file)
