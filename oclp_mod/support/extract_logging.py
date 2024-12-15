import re
import sys

def extract_logging_info(source_file_path, output_file_path):
    # 读取文件内容
    with open(source_file_path, 'r') as file:
        content = file.read()

    # 使用正则表达式匹配所有的logging.info语句
    pattern = r'logging\.info\(([\s\S]*?)\)'
    
    # 将匹配到的日志语句和顺序号写入新文件
    with open(output_file_path, 'w') as output_file:
        matches = re.findall(pattern, content)
        for index, match in enumerate(matches):
            # 获取匹配的原始内容
            origin = match.strip()
            # 写入原始内容和翻译占位符
            output_file.write(f"{origin} | $ts\n")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python extract_logging.py <source_file_path> <output_file_path>")
    else:
        source_file_path = sys.argv[1]
        output_file_path = sys.argv[2]
        extract_logging_info(source_file_path, output_file_path)
        print(f"Logging info extracted to '{output_file_path}'")