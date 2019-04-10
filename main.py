import glob
import json
import os
import shutil
import sys
import traceback

import paramiko

# import pp
#
# print = pp.cout

"""
FTP同步工具
"""
# 默认的配置文件名称
config_filename = "ftp.json"
default_config_file = "default_ftp.json"


# windows平台已经支持/路径了，所以此处可以统一一下，防止linux上出错
def join(*path_list):
    return os.path.join(*path_list).replace("\\", "/")


def dirname(path):
    return os.path.dirname(path).replace("\\", "/")


def relpath(path, base):
    return os.path.relpath(path, base).replace("\\", "/")


class Ftp:
    def __init__(self, host, port, username, password):
        """
        初始化FTP
        :param host: 主机
        :param port: 端口号
        :param username: 用户名
        :param password: 密码，可为""，若为空字符串，则默认启用~/.ssh中的公钥登录
        """
        self.transport = paramiko.Transport((host, port))
        if password:
            self.transport.connect(username=username, password=password)
        else:  # 没有提供密码，使用家目录下的SSH进行登录
            userHome = os.path.expanduser("~")
            id_rsa_path = join(userHome, '.ssh/id_rsa')
            print("no password ,will use SSH to login. id_rsa_path", id_rsa_path)
            private_key = paramiko.RSAKey.from_private_key_file(id_rsa_path)
            try:
                self.transport.connect(username=username, pkey=private_key)
            except:
                traceback.print_stack()
                print("connect failed")
        # sftp和ssh可以共用transport
        self.sftp = paramiko.SFTPClient.from_transport(self.transport)
        self.ssh = paramiko.SSHClient()
        self.ssh._transport = self.transport

    def prepareRemote(self, path):
        """
        准备好目录，在linux上无法直接放置文件，必须要把之前的目录准备好
        :param path:需要准备好的目录
        :return:
        """
        if self.isDir(path):
            return
        self.prepareRemote(dirname(path))
        self.sftp.mkdir(path)

    def prepareLocal(self, path):
        if os.path.isdir(path):
            return
        self.prepareLocal(dirname(path))
        os.mkdir(path)

    def upload(self, localFile, remoteFile, lazy=True):
        """
        上传文件
        :param localFile: 本地文件路径，必须是文件
        :param remoteFile: 远程文件路径，必须是文件
        :param lazy: 如果lazy=true，如果远程文件存在且较新，则不上传本地文件
        :return:
        """
        print("uploading", localFile, remoteFile)
        if lazy:
            try:  # 捕捉远程文件不存在的异常
                remoteInfo = self.sftp.stat(remoteFile)
                localInfo = os.stat(localFile)
                # 不需要更新
                if localInfo.st_mtime < remoteInfo.st_mtime:
                    print("no upload for no change", localFile)
                    return
            except FileNotFoundError as e:
                pass
        self.prepareRemote(dirname(remoteFile))
        self.sftp.put(localFile, remoteFile)  # 上传文件
        print("uploaded", localFile)

    def download(self, localFile, remoteFile, lazy=True):
        """
        下载远程文件
        :param localFile: 本地文件
        :param remoteFile: 远程文件
        :param lazy: 如果lazy=True，如果本地文件存在且较新，则更新本地文件
        :return:
        """
        print("downloading", localFile, remoteFile)
        if lazy:
            try:
                remoteInfo = self.sftp.stat(remoteFile)
                localInfo = os.stat(localFile)
                if localInfo.st_mtime > remoteInfo.st_mtime:
                    print("no download for no change", localFile)
                    return
            except FileNotFoundError as e:
                pass
        self.prepareLocal(dirname(localFile))
        self.sftp.get(remoteFile, localFile)
        print("downloaded", localFile)

    def close(self):
        """
        释放资源
        :return:
        """
        self.transport.close()

    def isFile(self, remotePath):
        try:
            stat = self.sftp.stat(remotePath)
            if not str(stat).startswith("d"):
                return True
            else:
                return False
        except Exception as ex:
            return False

    def isDir(self, remotePath):
        try:
            stat = self.sftp.stat(remotePath)
            if str(stat).startswith("d"):
                return True
            else:
                return False
        except Exception as ex:
            return False

    def exec(self, command):
        # 执行命令
        stdin, stdout, stderr = self.ssh.exec_command(command)
        # 获取命令结果
        result = stdout.read()
        return str(result, encoding='utf8')

    def glob(self, path):
        """
        使用ls命令获取远程的glob文件
        :param path: glob路径
        :return: 一个路径列表
        """
        assert path.startswith("/"), "path 应该使用绝对路径"
        command = "ls %s -d -1" % path
        out = self.exec(command)
        a = out.split("\n")
        a = [i.strip() for i in a if i.strip()]
        return a

    def listdir(self, path):
        files = self.sftp.listdir(path)
        return files


def isFileInNoNeed(noNeed, file):
    """
    判断file是否在noNeed这个数组中
    :param noNeed: 文件路径数组
    :param file: 文件（可为文件夹）
    :return:
    """
    for i in noNeed:
        p = os.path.relpath(file, i)
        if p == ".": return True
        if not p.startswith(".."):
            return True
    return False


def handleFile(filepath, noNeed, handler):
    """
    处理单个文件
    :param filepath:文件路径
    :param noNeed:不需要处理的文件路径
    :param handler:处理器
    :return:
    """
    if isFileInNoNeed(noNeed, filepath):
        return
    handler(filepath)


def handleDir(folder, fun):
    """
    处理文件夹
    :param folder: 文件夹路径
    :return:
    """
    if isFileInNoNeed(fun['noNeed'], folder):
        return
    for file in fun["listDir"](folder):
        filepath = join(folder, file)
        if fun["isFolder"](filepath):
            handleDir(filepath, fun)
        elif fun["isFile"](filepath):
            handleFile(filepath, fun['noNeed'], fun['handler'])
        else:
            print("unkown file stats", filepath)


def handle(fun):
    for it in fun["need"]:  # 处理每个需要处理的文件或者文件夹
        file_path = fun['rel2abs'](it)
        try:
            if fun["isFile"](file_path):
                # 注意handleFile应该使用相对路径
                handleFile(file_path, fun["noNeed"], fun['handler'])
            elif fun["isFolder"](file_path):
                handleDir(file_path, fun)
            else:
                print("ignore", file_path)
        except Exception as ex:
            traceback.print_exc()


def validConfig(conf):
    default_config = json.load(open(join(os.path.dirname(__file__), "default_ftp.json"), encoding='utf8'))
    lack = set(default_config.keys()) - set(conf.keys())
    if lack:
        return "lack keys : %s" % (','.join(lack))


class Work:
    def __init__(self):
        if not os.path.exists(config_filename):
            print(config_filename, "not exist")
            exit(-1)
        config = json.load(open(config_filename, encoding='utf8'))
        valid_info = validConfig(config)
        if valid_info:
            print(valid_info)
            exit(-1)
        self.lazy = config['lazy']
        self.localBase = config['localBase']
        self.remoteBase = config['remoteBase']
        # upload noUpload download noDownload
        self.ftp = Ftp(host=config['host'], port=config['port'], username=config['username'], password=config.get("password", ""))
        # 准备好基本目录
        self.ftp.prepareRemote(self.remoteBase)
        # 在解析下面代码过程中要用到sftp
        for glob_key in "upload noUpload".split():
            config[glob_key] = [relpath(p, self.localBase) for p in self.globList2FileList(config[glob_key])]
        for glob_key in "download noDownload".split():
            config[glob_key] = [relpath(p, self.remoteBase) for p in self.remoteGlob2FileList(config[glob_key])]
        self.upload = config['upload']
        self.noUpload = config['noUpload']
        self.download = config['download']
        self.noDownload = config['noDownload']
        # 不要上传准备下载的东西，不要下载准备上传的东西
        self.config = config

    def globList2FileList(self, glob_list):
        a = []
        for i in glob_list:
            a.extend(glob.glob(i))
        return a

    def remoteGlob2FileList(self, glob_list):
        a = []
        for i in glob_list:
            a.extend(self.ftp.glob(join(self.remoteBase, i)))
        return a

    def uploadOne(self, relpath):
        self.ftp.upload(join(self.localBase, relpath), join(self.remoteBase, relpath), self.lazy)

    def downloadOne(self, path):
        self.ftp.download(join(self.localBase, path), join(self.remoteBase, path), self.lazy)

    def doUpload(self):
        fun = {
            "rel2abs": lambda path: join(self.localBase, path),
            "isFile": lambda path: os.path.isfile(path),
            "isFolder": lambda path: os.path.isdir(path),
            "handler": lambda path: self.uploadOne(relpath(path, self.localBase)),
            "need": self.upload,
            "noNeed": self.noUpload,
            "listDir": os.listdir
        }
        handle(fun)
        self.ftp.close()

    def doDownload(self):
        fun = {
            "rel2abs": lambda path: join(self.remoteBase, path),
            "isFile": lambda path: self.ftp.isFile(path),
            "isFolder": lambda path: self.ftp.isDir(path),
            "handler": lambda path: self.downloadOne(relpath(path, self.remoteBase)),
            "need": self.download,
            "noNeed": self.noDownload,
            "listDir": self.ftp.listdir
        }
        handle(fun)
        self.ftp.close()


def help():
    print("""
    use 3 command :
    init upload download
    """)


if __name__ == '__main__':
    args = sys.argv
    if len(args) > 2:
        print("too much arguments")
        help()
        exit(-1)
    if len(args) < 2:
        print("too few arguments")
        help()
        exit(-1)
    if args[1] == "upload":
        w = Work()
        w.doUpload()
    elif args[1] == "download":
        w = Work()
        w.doDownload()
    elif args[1] == "init":
        shutil.copy(join(dirname(__file__), default_config_file), join(os.curdir, config_filename))
        print("初始化成功")
    else:
        print("unkown command")
        help()
