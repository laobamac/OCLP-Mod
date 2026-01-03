#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>
#include <libgen.h>
#include <limits.h>

#ifdef __APPLE__
#include <mach-o/dyld.h>  // 用于获取可执行文件路径
#endif

void remove_directory(const char *path) {
    char command[PATH_MAX * 2];
    snprintf(command, sizeof(command), "rm -rf \"%s\"", path);
    system(command);
}

void remove_file(const char *path) {
    if (remove(path) == 0) {
        printf("已删除: %s\n", path);
    }
}

void process_directory(const char *base_path, const char *target_name, int is_dir) {
    DIR *dir;
    struct dirent *entry;
    struct stat statbuf;
    char path[PATH_MAX];
    
    if ((dir = opendir(base_path)) == NULL) {
        return;
    }
    
    while ((entry = readdir(dir)) != NULL) {
        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0) {
            continue;
        }
        
        snprintf(path, sizeof(path), "%s/%s", base_path, entry->d_name);
        
        if (lstat(path, &statbuf) == -1) {
            continue;
        }
        
        if (S_ISDIR(statbuf.st_mode)) {
            if (is_dir && strcmp(entry->d_name, target_name) == 0) {
                printf("正在删除目录: %s\n", path);
                remove_directory(path);
            } else {
                process_directory(path, target_name, is_dir);
            }
        } else if (!is_dir && S_ISREG(statbuf.st_mode)) {
            if (strcmp(entry->d_name, target_name) == 0) {
                printf("正在删除文件: %s\n", path);
                remove_file(path);
            }
        }
    }
    
    closedir(dir);
}

// 获取程序所在目录的路径
int get_program_dir(char *buffer, size_t size) {
#ifdef __APPLE__
    // macOS 专用方法
    uint32_t bufsize = (uint32_t)size;
    if (_NSGetExecutablePath(buffer, &bufsize) == 0) {
        // 获取可执行文件的绝对路径
        char real_path[PATH_MAX];
        if (realpath(buffer, real_path) != NULL) {
            strncpy(buffer, real_path, size);
        }
        // 获取目录部分
        char *dir = dirname(buffer);
        strncpy(buffer, dir, size);
        return 0;
    }
    return -1;
#else
    // Linux/Unix 通用方法
    ssize_t len = readlink("/proc/self/exe", buffer, size - 1);
    if (len != -1) {
        buffer[len] = '\0';
        char *dir = dirname(buffer);
        strncpy(buffer, dir, size);
        return 0;
    }
    return -1;
#endif
}

// 获取程序所在目录的上一级目录
int get_parent_of_program_dir(char *buffer, size_t size) {
    char prog_dir[PATH_MAX];
    
    if (get_program_dir(prog_dir, sizeof(prog_dir)) != 0) {
        return -1;
    }
    
    // 使用 dirname 获取上一级目录
    // 注意：dirname 可能会修改输入字符串，所以先复制
    char temp[PATH_MAX];
    strncpy(temp, prog_dir, sizeof(temp));
    char *parent = dirname(temp);
    
    // 如果已经在根目录，则无法获取上一级
    if (strcmp(parent, "/") == 0 || strcmp(parent, ".") == 0) {
        return -1;
    }
    
    strncpy(buffer, parent, size);
    return 0;
}

int main(int argc, char *argv[]) {
    char target_path[PATH_MAX];
    
    // 确定目标路径
    if (argc > 1) {
        // 如果提供了命令行参数，使用它
        strncpy(target_path, argv[1], sizeof(target_path) - 1);
        target_path[sizeof(target_path) - 1] = '\0';
    } else {
        // 如果没有参数，使用程序所在目录的上一级目录
        if (get_parent_of_program_dir(target_path, sizeof(target_path)) != 0) {
            // 如果无法获取程序目录的上一级，使用当前目录的上一级作为备选
            if (getcwd(target_path, sizeof(target_path)) == NULL) {
                perror("获取当前目录失败");
                return 1;
            }
            
            char *parent_dir = dirname(target_path);
            if (parent_dir == NULL || strcmp(parent_dir, ".") == 0) {
                fprintf(stderr, "无法确定目标目录\n");
                return 1;
            }
            
            strncpy(target_path, parent_dir, sizeof(target_path) - 1);
            target_path[sizeof(target_path) - 1] = '\0';
            
            printf("警告：使用当前目录的上一级作为目标：%s\n", target_path);
        } else {
            printf("自动选择程序所在目录的上一级作为目标：%s\n", target_path);
        }
    }
    
    // 检查目录是否存在
    struct stat statbuf;
    if (stat(target_path, &statbuf) == -1 || !S_ISDIR(statbuf.st_mode)) {
        fprintf(stderr, "错误: 目录 %s 不存在\n", target_path);
        return 1;
    }
    
    printf("正在清理目录: %s\n", target_path);
    printf("================================\n");
    
    // 删除所有 __pycache__ 文件夹
    printf("正在删除所有 __pycache__ 文件夹...\n");
    process_directory(target_path, "__pycache__", 1);

    // 删除所有 Build-Folder 文件夹
    printf("正在删除所有 Build-Folder 文件夹...\n");
    process_directory(target_path, "Build-Folder", 1);   
   
    // 删除所有 .DS_Store 文件
    printf("\n正在删除所有 .DS_Store 文件...\n");
    process_directory(target_path, ".DS_Store", 0);
    
    // 删除特定文件和目录
    printf("\n正在删除特定文件和目录...\n");
    
    char universal_path[PATH_MAX];
    char oclp_path[PATH_MAX];
    
    snprintf(universal_path, sizeof(universal_path), "%s/payloads/Universal-Binaries_overlay", target_path);
    snprintf(oclp_path, sizeof(oclp_path), "%s/payloads/oclp-mod.plist", target_path);
    
    struct stat st;
    if (stat(universal_path, &st) == 0) {
        if (S_ISDIR(st.st_mode)) {
            printf("正在删除: %s\n", universal_path);
            remove_directory(universal_path);
        } else {
            printf("正在删除文件: %s\n", universal_path);
            remove_file(universal_path);
        }
    }
    
    if (stat(oclp_path, &st) == 0) {
        printf("正在删除: %s\n", oclp_path);
        remove_file(oclp_path);
    }
    
    printf("\n================================\n");
    printf("清理完成!\n");
    
    return 0;
}
