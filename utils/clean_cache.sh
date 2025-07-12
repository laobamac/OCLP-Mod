#!/bin/bash

# 检查是否提供了文件夹路径
if [ -z "$1" ]; then
    echo "Usage: $0 /path/to/directory"
    exit 1
fi

# 检查文件夹是否存在
if [ ! -d "$1" ]; then
    echo "Error: Directory $1 does not exist"
    exit 1
fi

# 查找并删除所有 __pycache__ 文件夹
echo "正在删除 $1 及其子目录中的所有 __pycache__ 文件夹..."
find "$1" -type d -name "__pycache__" -exec rm -rf {} +

echo "清理完成"