import os  # 用来改变目录
import requests  # 用来进行网络请求
import csv  # 用来处理 CSV 文件
import re  # 用来正则匹配
import time  # 用来处理时间延迟
import subprocess  # 用来执行 Powershell 命令并获取输出
from concurrent.futures import ThreadPoolExecutor  # 用来处理多线程任务

# GitHub access token 用于访问私有仓库
access_token = ''

# 本地存放所有仓库的目录
base_path1 = 'G:\\Repo'

# 输入的 CSV 文件路径
input_csv = "E:\\task\\fw\\1.csv"

# 输出的 CSV 文件路径
output_csv = "E:\\task\\fw\\a.csv"

# 定义正则表达式模式
# 匹配以 // 开头的单行注释
single_line_comment_pattern = re.compile(r'^[+-]?\s*//')

# 匹配以 /* 开头的多行注释块
multi_line_comment_start_pattern = re.compile(r'^[+-]?\s*/\*')

# 匹配多行注释的内容行（以 * 开头）
multi_line_comment_cont_pattern = re.compile(r'^[+-]?\s*\*')

# 正则表达式用于匹配仅包含空白字符、制表符或填充空格的行
empty_or_whitespace_pattern = re.compile(r'^\s*$')

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

    # 使用 cmd 查询指定 commit 中是否有 test 文件
    git_ls_tree = f'git ls-tree -r {commit_hash}'
    result = subprocess.run(['cmd', '/c', git_ls_tree], capture_output=True, text=True)
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
        pointer = -1 # 指针，用于记录行索引
        hunk = 0  # Hunk 的数量，考虑到第一个 Hunk 之前存在 @@ 标记，所以初始化为 0
        is_in_hunk = 0 # 标志位，用于判断当前行是否在 Hunk 中
        is_comment = 0
        is_test_case = 0

        for index, line in enumerate(self.lines, start=1):

            if line.startswith('@@'):
                # 遇到 Hunk 标记行，重置指针和注释标志位
                # 如果指示器为 1，说明上一个 Hunk 应该结束
                if is_in_hunk == 1:
                    pointer = index # 更新指针到当前行
                    is_in_hunk = 0
                is_comment = 0 # 重置注释标志位
                continue
            
            if line.find('*/') != -1 and is_comment == 1:
                is_comment = 0 # 注释结束
                if is_in_hunk == 1: # 且如果当前行在 Hunk 中，指针到当前行，Hunk 不结束
                    pointer = index
                continue

            if is_comment == 1: # 上一段是注释段
                if is_in_hunk == 1: # 且如果当前行在 Hunk 中，指针到当前行，Hunk 不结束
                    pointer = index
                continue

            if line.startswith("diff"):
                is_test_case = 0 # 重置测试用例标志位
                is_java_file = 0 # 重置 Java 文件标志位
                test_pattern = "^diff --git.*[Tt][Ee][Ss][Tt].*$"
                test_ans = re.search(test_pattern, line)
                if test_ans:
                    is_test_case = 1
                java_pattern = r"^diff --git.*\.java$"
                java_ans = re.search(java_pattern, line)
                if java_ans:
                    is_java_file = 1
            if is_test_case == 1:
                continue
            if is_java_file == 0:
                continue

            # 处理修改行（+/-开头的行）
            if line.find("import") == -1: # 排除 import 语句
                if line[0] == '-' or line[0] == "+":
                    if any(line.startswith(ignore) for ignore in ["+++", "---"]):  # 排除 diff 头部信息
                        continue

                    if bool(empty_or_whitespace_pattern.match(line[1:])):
                        # 如果行只包含空白字符、制表符或填充空格，跳过
                        if is_in_hunk == 1:
                            pointer = index
                        continue

                    is_in_hunk = 1
                    
                    if single_line_comment_pattern.match(line):  # 排除单行注释
                        if pointer == -1: # 如果指针未初始化，则直接跳过
                            continue
                        if is_in_hunk == 1:
                            pointer = index
                        continue

                    if multi_line_comment_start_pattern.match(line):  # 排除多行注释块
                        if pointer == -1: # 如果指针未初始化，则直接跳过
                            is_comment = 1
                            continue
                        is_comment = 1
                        if is_in_hunk == 1:
                            pointer = index
                        continue


                    if pointer == -1: # 第一次遇到代码的修改行，初始化指针
                        pointer = index
                        hunk += 1
                        print("hunk:", hunk)
                        print("line:", line)

                    else: # 非第一次遇到修改行，判断是否属于同一个hunk
                        if index == (pointer + 1): # 如果当前行是上一行的下一行，说明在同一个 hunk 中
                            if is_in_hunk == 1:
                                pointer = index

                        else: # 如果当前行不是hunk当前结尾的下一行，说明进入了新的 hunk，重置指针和 hunk 计数
                            if is_in_hunk == 1:
                                pointer = index
                            hunk += 1
                            print("hunk:", hunk)
                            print("line:", line)
                else:
                    is_in_hunk = 0

            # # 处理注释
            # if line.find("/**") != -1 or line.find("/*") != -1:
            #     is_comment = 1
            #     continue
            # if line.find('//') != -1:
            #     continue



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
                pattern = "^diff --git.*[Tt][Ee][Ss][Tt].*$"
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
    path_str = os.path.join(base_path1, repo_path)
    command = ["git", "-C", path_str, "show", "--format=%s", "-s", commit_hash]
    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode == 0:
        return result.stdout.strip()
    else:
        print("Failed to get commit subject")
        print("Error:", result.stderr)  # 添加 stderr 输出调试信息
        return None


if __name__ == '__main__':
    max_workers = 5

    # 读取输入的 CSV 文件，获取所有的仓库 URL
    with open(input_csv) as csvfile:
        reader = csv.reader(csvfile)
        urls = [row[3] for row in reader]

    # 克隆所有仓库
    # os.chdir(base_path1)
    # with ThreadPoolExecutor(max_workers=max_workers) as executor:
    #     for url in urls:
    #         executor.submit(clone_repository, url, base_path1)

    # 输出 CSV 文件初始化
    with open(output_csv, 'w') as f:
        f.write("url,repo,file,java_file,func,hunk,test,note\n")

    # 分析每个仓库的提交记录
    for url in urls:
        try:
            commit_hash=extract_commit_hash(url)
            repo=repository_name = re.search(r'/([^/]+/[^/]+)/commit/', url).group(1)
            repo = re.search(r'[^/]+$', repository_name).group()
            note = get_commit_subject(commit_hash,repo)
            os.chdir(os.path.join(base_path1, repo))
            diff_command = f'git diff {commit_hash}^..{commit_hash}'  # 注意添加了空格
            diff_output = subprocess.run(['pwsh', '-Command', diff_command], capture_output=True, text=True, encoding='utf-8').stdout
            print (diff_command)
            if len(diff_output)<1:
                print("the repo local is bad")
                diff_url=url+'.diff'
                res=requests.get(diff_url).text
                if res!=None:
                    print("it is solved")
                    diff_output=res
            parser=DiffParser(diff_output)
            with open(output_csv, 'a') as f:
                file, java_file,test_in_commit = parser.parse_file()
                hunk = parser.parse_hunk()
                functions = len(parser.extract_functions())

                string = "URL: {}   Repo: {}   file: {}   java_file: {}   functions: {}   hunk: {}\n".format(url, repo, file, java_file, functions, hunk)
                test_in_repo = 0
                if(test_in_commit == 0):
                    if test_finder(url):
                        test_in_repo = 1

                string = "{},{},{},{},{},{},{},{}\n".format(url, repository_name, file, java_file, functions, hunk, test_in_commit|test_in_repo,note)
                f.write(string)
        except Exception as e:
            print(f"Error processing {url}: {e}")
            continue
