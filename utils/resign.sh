#!/bin/bash

# 检查是否提供了文件夹路径
if [ -z "$1" ]; then
    echo "Usage: $0 /path/to/directory"
    exit 1
fi

target_dir="$1"
signing_identity="Apple Development: wxcznb@qq.com (636H9J6N4H)"

# 检查目录是否存在
if [ ! -d "$target_dir" ]; then
    echo "Error: Directory $target_dir does not exist"
    exit 1
fi

# 查找并删除所有 _CodeSignature 文件夹
echo "Searching for _CodeSignature folders in $target_dir..."
find "$target_dir" -type d -name "_CodeSignature" -print -exec rm -rf {} +

echo "Process completed."