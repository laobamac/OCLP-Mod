# OCLP-Mod changelog

## 2.4.6

## 2.4.5
- 修补根修补期间的metallib_install_handle句柄。

## 2.4.4
- 更新至 OpenCore 1.0.3
- 添加对AR9485/AR8111/AR9285的支持
- 修复SN的生成
- 启用Github Action，以后可在Actions获取最新编译版本（开发测试！生产环境不要使用！）
- 将Lilu更新到1.7.0，WEG更新到1.6.9，修复OpenCore的更新程序，以便它可以在1.0.3+上使用

## 2.4.3
- 支持直接运行应用程序（.app）！不再需要pkg安装了！🎉
- 修复AMD_GCN 7000上的补丁，这些GPU现在可以在Seqouia 15.2+上使用！
- 重复使用OpenCore 1.0.2，修复SLC文件夹，解决 #3

## 2.4.2
- 修复了payload.dmg挂载失败导致无法生成OpenCore的问题

## 2.4.1
- 修复手动下载KDK，Metallib版本不对应的问题
- 允许复制下载加速链接自行使用其他工具下载