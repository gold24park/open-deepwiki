import os
import shutil
import subprocess
from collections import Counter
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Self

from directory_tree import DisplayTree
from github import Auth, Github

from apps.model import WikiConfiguration
from apps.settings import IS_TEST, REPO_DIR, Logger
from apps.utils import normalize_path


class ChangeMode(Enum):
    ADDED = "A"
    MODIFIED = "M"
    DELETED = "D"


def is_git_repo(path: str | Path) -> bool:
    repo_path = Path(path) if isinstance(path, str) else path
    return repo_path.exists() and (repo_path / ".git").exists()


class GitRepository:
    def __init__(
        self,
        repository: str,
        pat: str | None,
        repo_dir: str = REPO_DIR,
    ):
        self.pat = pat
        self.repo_dir = repo_dir
        self.repository = repository

        auth = Auth.Token(pat) if pat else None
        self._gh = Github(auth=auth)
        p = self._gh.get_user()
        self._repo = self._gh.get_repo(self.repository)

    @property
    def repo(self) -> str:
        """
        Returns the name of the repository.
        """
        return self._repo.name

    @property
    def owner(self) -> str:
        """
        Returns the owner of the repository.
        """
        return self._repo.owner.login

    @property
    def branch(self) -> str:
        """
        Returns the current branch of the repository.
        """
        result = self.exec(
            ["rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def exec(self, args: list[str], **kwargs) -> subprocess.CompletedProcess:
        base_args = ["git", "-C", self.repo_path]
        result = subprocess.run(
            base_args + args,
            **kwargs,
        )
        if result.returncode != 0:
            Logger.error(
                f"Git command failed {result.args}: {result.stderr or result.stdout}"
            )
            raise subprocess.CalledProcessError(
                returncode=result.returncode,
                cmd=result.args,
                output=result.stdout,
                stderr=result.stderr,
            )
        return result

    @property
    def repo_path(self) -> Path:
        """
        Returns the path to the local repository.
        """
        return Path(self.repo_dir) / self._repo.owner.login / self._repo.name

    @property
    def commit_hash(self) -> str:
        result = self.exec(
            ["rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def clone(self) -> Self:
        """
        Repository가 존재하지 않으면 Repository를 clone 합니다.

        Raises:
            subprocess.CalledProcessError: git clone이 실패한 경우
        """
        # 이미 git repository가 존재하는 경우
        if is_git_repo(self.repo_path):
            return self

        # repository가 없으므로 clone한다.
        url = self._repo.clone_url
        if self.pat:
            url = url.replace("https://", f"https://{self.pat}@")

        subprocess.run(
            [
                "git",
                "clone",
                url,
                self.repo_path,
            ],
            check=True,
        )

        return self

    def checkout(self, branch: str | None = None) -> Self:
        """
        Repository의 branch를 checkout 합니다.

        Raises:
            subprocess.CalledProcessError: git checkout이 실패한 경우
        """
        branch = branch or self._repo.default_branch
        self.exec(["fetch", "--all"])
        self.exec(["checkout", branch])
        return self

    def pull(self) -> Self:
        """
        Repository의 branch를 pull 합니다.

        Raises:
            subprocess.CalledProcessError: git pull이 실패한 경우
        """
        self.exec(["restore", "."])  # 변경된 사항을 복원한다.
        self.exec(["pull", "--rebase=true"])
        return self

    def get_most_updated_files(
        self,
        since: str | None = None,
        top_n: int = 10,
        filter_exists: bool = False,
    ) -> list[tuple[str, int]]:
        """
        Repository에서 가장 많이 수정된 파일을 가져옵니다.

        Args:
            since (str): 최근 몇개월 전부터의 commit을 가져올지 설정합니다. e.g "3 months ago"
            top_n (int): 가장 많이 수정된 파일의 개수를 설정합니다.
            filter_exists (bool): True일 경우, 현재 Clone된 Repository에 존재하는 파일만 가져옵니다.

        Returns:
            list[tuple[str, int]]: 가장 많이 수정된 파일, 수정횟수 목록
        """
        args = ["log", "--name-only", "--pretty=format:"]
        if since:
            args += ["--since", since]
        result = self.exec(
            args,
            capture_output=True,
            text=True,
        )
        files = [
            file
            for file in result.stdout.splitlines()
            if file
            and (not filter_exists or (Path(self.repo_path) / file).exists())
        ]
        file_count = Counter(files)
        return file_count.most_common(top_n)

    def download(
        self, branch: str | None = None, ignore_patterns: list[str] = []
    ):
        """
        Repository를 다운로드합니다.

        Args:
            branch (str | None): checkout할 branch를 설정합니다. 설정하지 않을 경우 기본 branch로 checkout합니다.
            ignore_patterns (list[str]): 무시할 파일 패턴을 설정합니다. glob 패턴을 사용합니다. 다운로드 후 삭제됩니다.
        """
        self.clone().checkout(branch=branch).pull()

        # 무시할 파일 패턴을 삭제합니다.
        for pattern in ignore_patterns:
            for path in Path(self.repo_path).rglob(pattern):
                if any(part == ".git" for part in path.parts):
                    continue  # .git 관련 경로는 스킵
                elif path.is_file():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)

    def get_file_tree(self) -> str:
        """
        Repository의 파일 트리를 가져옵니다.

        Returns:
            str: Repository의 파일 트리
        """
        tree = (
            DisplayTree(
                dirPath=self.repo_path,
                maxDepth=6,
                stringRep=True,
            )
            or "."
        )
        tree = tree.replace(f"{self.repo}/", "/")
        return tree

    def list_diff_files(self, commit_hash: str):
        """
        Repository의 commit hash에 대한 diff 파일 목록을 가져옵니다.

        Args:
            commit_hash (str): commit hash

        Yields:
            tuple[ChangeMode, str]: 변경된 파일의 mode와 경로
        """
        curr_hash = self.commit_hash
        result = self.exec(
            ["diff", "--name-status", "--no-renames", commit_hash, curr_hash],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if not line:
                continue
            mode, file_path = line.split("\t")
            yield ChangeMode(mode), file_path


class WikiRepository(GitRepository):
    def __init__(self, base: GitRepository, config: WikiConfiguration):
        repository = config.wiki.repository or base.repository
        owner, repo = repository.split("/")
        super().__init__(
            repository=repository,
            pat=base.pat,
        )
        self._base_repo = base
        self.wiki_path = base.repo_path / normalize_path(
            config.wiki.directory or "/"
        )

    def upload(self):
        """
        생성된 Wiki 문서를 Wiki Repository에 업로드합니다.
        """
        message = f"Update wiki for {self._base_repo.branch} ({self._base_repo.commit_hash})"

        # 테스트 모드일 경우, commit message에 TEST를 붙여 구분합니다.
        if IS_TEST:
            message = f"TEST: {message}"

        self.exec(["add", "."])
        self.exec(["commit", "-m", message])
        self.exec(["push", "origin", self._repo.default_branch])

    def get_last_commit_time(self) -> datetime | None:
        """
        Wiki Repository의 마지막 commit 시간을 가져옵니다.

        Returns:
            datetime: 마지막 commit 시간
        """
        try:
            # git --no-pager log -1 --format="%ci" apps/
            path = (
                os.path.relpath(self.wiki_path, self.repo_path)
                if str(self.wiki_path) == self.repo_path
                else "."
            )
            result = self.exec(
                ["--no-pager", "log", "-1", "--format=%cd", path],
                capture_output=True,
                text=True,
            )
            commit_time = datetime.strptime(
                result.stdout.strip(), "%a %b %d %H:%M:%S %Y %z"
            )
            return commit_time.replace(tzinfo=None)
        except Exception as e:
            Logger.error(f"Failed to get last commit time: {e}")
            return None

    def cleanup(self):
        """
        Wiki Repository를 정리합니다.
        """
        shutil.rmtree(self.repo_path, ignore_errors=True)
        shutil.rmtree(self.wiki_path, ignore_errors=True)
