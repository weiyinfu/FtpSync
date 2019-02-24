# 特点
* 支持glob语法设置上传下载文件
* 可以配置忽略上传、下载的文件
* 可以避免重复上传未更新的文件

# 原理
使用SFTP远程登录服务器

# 配置说明
* host:主机
* port：端口号
* username：用户名
* password：密码，如果密码为空字符串，则使用~/.ssh下的公钥进行登录
* upload:需要上传的文件，使用glob语法
* noUpload：需要忽略上传的文件，使用glob语法
* download：需要下载的文件，使用glob语法
* noDownload：不需要下载的文件，使用glob语法
* lazy：是否启用lazy模式。lazy模式下，上传时只上传发生更改的文件（通过比对本地文件和远程文件的更改时间得出）；下载时只下载远程发生更改的文件（通过比对本地文件和远程文件的更改时间得出）
* localBase：本地基本路径
* remoteBase：远程基本路径

# 命令行
只有三个命令：
* init：初始化，创建ftp.json
* upload：上传
* download：下载

# TODO
* 添加文件改变监控功能
* 添加彩色打印上传信息 