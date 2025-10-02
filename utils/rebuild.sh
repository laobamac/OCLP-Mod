#!/bin/bash

# 设置颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}PFX/P12证书转换为Legacy格式脚本${NC}"
echo "========================================"

# 检查输入文件
if [ $# -eq 0 ]; then
    echo -e "${RED}错误: 请拖拽证书文件到终端，或提供证书路径作为参数${NC}"
    echo "用法: $0 <证书文件路径>"
    exit 1
fi

CERT_FILE="$1"

# 检查文件是否存在
if [ ! -f "$CERT_FILE" ]; then
    echo -e "${RED}错误: 文件 '$CERT_FILE' 不存在${NC}"
    exit 1
fi

# 检查文件扩展名
if [[ ! "$CERT_FILE" =~ \.(pfx|p12)$ ]]; then
    echo -e "${RED}错误: 文件必须是 .pfx 或 .p12 格式${NC}"
    exit 1
fi

# 获取文件信息
FILENAME=$(basename "$CERT_FILE")
DIRNAME=$(dirname "$CERT_FILE")
BASENAME="${FILENAME%.*}"
EXTENSION="${FILENAME##*.}"
LEGACY_CERT="$DIRNAME/Legacy_$FILENAME"

echo "输入文件: $CERT_FILE"
echo "输出文件: $LEGACY_CERT"

# 安全地读取密码
echo -e "${YELLOW}请输入证书密码（如果没有密码，请直接按回车）:${NC}"
read -s -r CERT_PASSWORD

echo "正在转换证书..."

# 创建临时文件
TEMP_CERT=$(mktemp)
TEMP_KEY=$(mktemp)

# 设置退出时清理临时文件
cleanup() {
    rm -f "$TEMP_CERT" "$TEMP_KEY"
}
trap cleanup EXIT

if [ -z "$CERT_PASSWORD" ]; then
    # 无密码情况 - 分步转换
    echo "步骤1: 提取证书和私钥..."
    openssl pkcs12 -in "$CERT_FILE" -nodes -legacy -out "$TEMP_CERT" -passin pass:
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}✗ 提取证书失败！${NC}"
        exit 1
    fi
    
    echo "步骤2: 重新打包为Legacy格式..."
    openssl pkcs12 -export -legacy -out "$LEGACY_CERT" -in "$TEMP_CERT" -passout pass:
else
    # 有密码情况 - 分步转换
    echo "步骤1: 提取证书和私钥..."
    openssl pkcs12 -in "$CERT_FILE" -nodes -legacy -out "$TEMP_CERT" -passin "pass:$CERT_PASSWORD"
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}✗ 提取证书失败！请检查密码是否正确。${NC}"
        exit 1
    fi
    
    echo "步骤2: 重新打包为Legacy格式..."
    openssl pkcs12 -export -legacy -out "$LEGACY_CERT" -in "$TEMP_CERT" -passout "pass:$CERT_PASSWORD"
fi

# 检查转换结果
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 证书转换成功！${NC}"
    echo "Legacy证书已保存到: $LEGACY_CERT"
    
    # 验证新证书
    echo -e "\n${YELLOW}验证新证书...${NC}"
    if [ -z "$CERT_PASSWORD" ]; then
        openssl pkcs12 -in "$LEGACY_CERT" -info -nodes -legacy -passin pass: 2>/dev/null | grep -E "(subject=|issuer=|Not Before|Not After)" | head -10
    else
        openssl pkcs12 -in "$LEGACY_CERT" -info -nodes -legacy -passin "pass:$CERT_PASSWORD" 2>/dev/null | grep -E "(subject=|issuer=|Not Before|Not After)" | head -10
    fi
else
    echo -e "${RED}✗ 证书转换失败！${NC}"
    echo "可能的原因："
    echo "  - 密码错误"
    echo "  - 证书文件损坏"
    echo "  - 没有足够的权限"
    exit 1
fi

# 清理临时文件
cleanup

echo -e "\n${GREEN}现在您可以在GitHub Action中使用这个Legacy证书了！${NC}"