import re
import sys

def replace_logging_info(source_file_path, translated_file_path):
    # 读取源文件内容
    with open(source_file_path, 'r') as source_file:
        lines = source_file.readlines()

    # 读取翻译后的日志内容
    translated_logs = []
    with open(translated_file_path, 'r') as translated_file:
        for line in translated_file:
            parts = line.strip().split(' | ')
            if len(parts) == 2:
                origin, translated = parts
                translated_logs.append((origin.strip(), translated.strip()))

    # 替换源文件中的logging.info语句
    pattern = r'logging\.info\(([\s\S]*?)\)'
    for i, line in enumerate(lines):
        for origin, translated in translated_logs:
            if re.search(pattern, line) and origin == re.search(pattern, line).group(1).strip():
                lines[i] = f"logging.info({translated})"
                print(f"Replaced '{origin}' with '{translated}'")
                break

    # 将替换后的内容写回源文件
    with open(source_file_path, 'w') as source_file:
        source_file.writelines(lines)

    print(f"Logging info in '{source_file_path}' has been replaced with translated content.")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python replace_logging.py <source_file_path> <translated_file_path>")
    else:
        source_file_path = sys.argv[1]
        translated_file_path = sys.argv[2]
        replace_logging_info(source_file_path, translated_file_path)