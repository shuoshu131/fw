import os  # 用来改变目录
import requests  # 用来进行网络请求
import csv  # 用来处理 CSV 文件
import re  # 用来正则匹配
import time  # 用来处理时间延迟
import subprocess  # 用来执行 Powershell 命令并获取输出
from concurrent.futures import ThreadPoolExecutor  # 用来处理多线程任务

# GitHub access token 用于访问私有仓库
access_token = 'input your token'

# 本地存放所有仓库的目录
base_path1 = 'G:\\REPO'

# 输入的 CSV 文件路径
input_csv = "E:\\task\\fw\\java_repos.csv"

# 输出的 CSV 文件路径
output_csv = "D:\\大创\\fw\\a.csv"


def clone_repository(url, output_dir):
    """
    克隆指定仓库到本地目录

    参数:
    - url: 仓库的 GitHub URL，包含提交的 commit 信息
    - output_dir: 本地目录，存放克隆的仓库

    返回:
    无直接返回，成功则打印克隆信息，失败则打印错误信息
    """
    try:
        # 从 URL 中提取仓库名
        repository_name = re.search(r'/([^/]+/[^/]+)/commit/', url).group(1)
        repo = re.search(r'[^/]+$', repository_name).group()

        # 构造包含 token 的仓库地址
        repository_url = f"https://{access_token}@github.com/{repository_name}"
        print(repo)

        # 检查仓库是否已存在，避免重复克隆
        if os.path.exists(os.path.join(output_dir, repo)):
            print(f"Repository {repo} already exists, skipping...")
            return

        # 执行 git clone 命令
        subprocess.run(["git", "clone", repository_url])
        print(f"Successfully cloned {url}")

        # 延迟一段时间，避免频繁请求 GitHub
        time.sleep(2)

    except Exception as e:
        print(f"Error cloning {url}: {e}")


def extract_commit_hash(url):
    """
    从 URL 中提取提交的 commit hash 值

    参数:
    - url: 包含 commit hash 的 GitHub URL

    返回:
    - commit_hash: 提取的 commit hash 值，如果找不到返回 None
    """
    match = re.search(r'/commit/([^/#]+)', url)
    if match:
        commit_hash = match.group(1)
        return commit_hash
    else:
        return None


def test_finder(url):
    """
    在仓库的指定 commit 中查找是否包含 test 相关的文件

    参数:
    - url: 包含 commit 信息的 GitHub URL

    返回:
    - bool: 如果找到测试文件返回 True，否则返回 False
    """
    repository_name = re.search(r'/([^/]+/[^/]+)/commit/', url).group(1)
    repo = re.search(r'[^/]+$', repository_name).group()

    # 切换到仓库所在的目录
    os.chdir(os.path.join(base_path1, repo))
    commit_hash = extract_commit_hash(url)

    # 使用 Powershell 查询指定 commit 中是否有 test 文件
    git_ls_tree = f'git ls-tree -r {commit_hash} | Select-String "(?i)test"'
    result = subprocess.run(['powershell', '-Command', git_ls_tree], capture_output=True, text=True)
    output = result.stdout

    return bool(output)


class DiffParser:
    """
    解析 git diff 输出的类

    方法:
    - parse_hunk: 解析并统计 Hunk 的数量
    - parse_file: 解析文件数量和 java 文件的数量
    - extract_functions: 提取文件中的函数定义
    """

    def __init__(self, diff_output):
        """
        构造函数，初始化类

        参数:
        - diff_output: git diff 命令的输出结果
        """
        self.lines = diff_output.splitlines(keepends=False)
        self.diff_output = diff_output

    def parse_hunk(self):
        """
        解析并统计 Hunk 的数量

        返回:
        - hunk: Hunk 的数量
        """
        pointer = -1
        hunk = 0  # 计算 Hunk 的数量
        is_comment = 0
        is_test_case = 0

        for index, line in enumerate(self.lines, start=1):

            if line.startswith('@@'):
                # 遇到 Hunk 标记行，重置指针和注释标志位
                # 如果指针不为 -1，说明上一个 Hunk 已经结束，Hunk 数量 +1
                if pointer != -1:
                    hunk += 1
                    pointer = -1
                is_comment = 0
                continue

            if line.startswith("diff"):
                is_test_case = 0
                pattern = "^diff --git.*[Tt][Ee][Ss][Tt].*$"
                ans = re.search(pattern, line)
                if ans:
                    is_test_case = 1
            if is_test_case == 1:
                continue

            # 处理注释
            if line.find('*/') != -1 and is_comment == 1:
                is_comment = 0
                continue
            if line.find("/**") != -1 or line.find("/*") != -1:
                is_comment = 1
                continue
            if is_comment == 1:
                continue

            # 处理修改行（+/-开头的行）
            if len(line) >= 1:
                if line.find("import") == -1:
                    if line[0] == '-' or line[0] == "+":
                        if any(line.startswith(ignore) for ignore in ["+++", "---", "+ *", "+/*", "-/*", "- *"]):
                            continue

                        if pointer == -1:
                            pointer = index
                            hunk += 1
                        else:
                            if index == (pointer + 1):
                                pointer = index
                            else:
                                pointer = index
                                hunk += 1

        print(hunk)
        return hunk

    def parse_file(self):
        """
        解析文件的数量和 Java 文件的数量

        返回:
        - file: 文件的总数
        - java_file: Java 文件的数量
        - test_in_commit: 提交中是否有测试文件
        """
        file = 0
        java_file = 0
        is_test_case = 0
        test_in_commit = 0

        for line in self.lines:
            if line.startswith("diff"):
                is_test_case = 0
                pattern = "^diff --git.*[Tt][eE][Ss][Tt].*$"
                ans = re.search(pattern, line)
                if ans:
                    is_test_case = 1
            if is_test_case == 1:
                test_in_commit = 1
                continue

            if line.startswith("diff"):
                file += 1  # 遇到新文件，计数器 +1
                if line.endswith(".java"):
                    java_file += 1

        print("[java_file]:", java_file)
        print("[file]:", file)
        print("[test_in_commit]:", test_in_commit)
        return file, java_file, test_in_commit

    def extract_functions(self):
        """
        从 diff 输出中提取函数定义

        返回:
        - functions: 提取的函数定义列表
        """
        functions = []
        diff_blocks = self.diff_output.split('diff --git')

        for block in diff_blocks:
            if 'test' not in block.lower():
                function_matches = re.findall(r'(\b[a-zA-Z_][a-zA-Z0-9_]*\s*\([^)]*\)\s*(?:throws\s+\w+\s*)?\{[^}]*\})',
                                              block)
                functions.extend(function_matches)

        return functions


def get_commit_subject(commit_hash, repo_path):
    """
    获取给定 commit 的提交说明

    参数:
    - commit_hash: commit 的哈希值
    - repo_path: 本地仓库的路径

    返回:
    - 提交说明，如果获取失败则返回 None
    """
    path_str = f"E:\\REPO\\{repo_path}"
    command = ["git", "-C", path_str, "show", "--format=%s", "-s", commit_hash]
    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode == 0:
        return result.stdout.strip()
    else:
        print("Failed to get commit subject")
        return None


if __name__ == '__main__':
    max_workers = 5

    # 读取输入的 CSV 文件，获取所有的仓库 URL
    with open(input_csv) as csvfile:
        reader = csv.reader(csvfile)
        urls = [row[3] for row in reader]

    # 克隆所有仓库
    os.chdir(base_path1)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for url in urls:
            executor.submit(clone_repository, url, base_path1)

    # 输出 CSV 文件初始化
    with open(output_csv, 'w') as f:
        f.write("url,repo,file,java_file,func,hunk,test,note\n")

    # 分析每个仓库的提交记录
    for url in urls:
        commit_hash = extract_commit_hash(url)
        repository_name = re.search(r'/([^/]+/[^/]+)/commit/', url).group(1)
        repo = re.search(r'[^/]+$', repository_name).group()

        # 获取仓库的 diff 信息
        command = ['git', '-C', f'E:\\REPO\\{repo}', 'diff', f'{commit_hash}~1', commit_hash]
        result = subprocess.run(command, capture_output=True, text=True)
        diff_output = result.stdout

        # 解析 diff 信息
        diff_parser = DiffParser(diff_output)
        file, java_file, test_in_commit = diff_parser.parse_file()
        hunk = diff_parser.parse_hunk()
        functions = diff_parser.extract_functions()

        # 获取提交说明
        commit_subject = get_commit_subject(commit_hash, repo)

        # 测试检测
        test_result = test_finder(url)

        # 将结果写入输出文件
        with open(output_csv, 'a') as f:
            f.write(f"{url},{repo},{file},{java_file},{len(functions)},{hunk},{test_result},{commit_subject}\n")
