import os
from pathlib import Path
from typing import List

from langchain_core.tools import BaseTool

from apps.git import GitRepository
from apps.settings import Logger
from apps.tools.common import Observation
from apps.utils import normalize_path


class ListFilesObservation(Observation):
    files: List[str] = []
    total_files: int = 0

    def render(self) -> str:
        if not self.files:
            return f"No files found."

        lines = []
        lines.extend(self.files)
        more_files = self.total_files - len(self.files)

        if more_files > 0:
            lines.append(f"... and {more_files} more files")
        return "\n".join(lines)


def list_files(repo: GitRepository, dir_path: str) -> ListFilesObservation:
    result = ListFilesObservation()

    limit = 100

    path = Path(repo.repo_path) / normalize_path(dir_path)

    file_paths = []
    more_files = 0
    for root, _, files in os.walk(path):
        for file in files:
            if len(file_paths) > limit:
                more_files += 1
            file_path = Path(root) / file
            rel_path = os.path.relpath(file_path, repo.repo_path)
            if rel_path.startswith(".git/"):
                continue
            result.files.append(rel_path)

    result.total_files = len(result.files) + more_files
    return result


class ListFilesTool(BaseTool):
    name: str = "list_files"
    description: str = """
    List all files in the directory of the repository.
    You can use this tool to get an overview of the files in a specific directory.
    The tool will return a list of file paths in the specified directory.
    """
    repo: GitRepository

    def _run(self, dir_path: str) -> str:
        try:
            result = list_files(self.repo, dir_path)
            return result.render()
        except Exception as e:
            Logger.error(
                f"Error listing files in {dir_path}: {str(e)}", exc_info=True
            )
            return f"Error occurred while listing files."
