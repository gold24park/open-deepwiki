from pathlib import Path
from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from apps.git import GitRepository
from apps.settings import Logger
from apps.tools.common import Observation, read_file_content
from apps.utils import normalize_path


class ViewFileContentObservation(Observation):
    page: int = 0
    has_more: bool = False
    content: str = ""

    def render(self) -> str:
        lines = []
        lines.append(f">> Page: {self.page}")
        lines.append(
            f">> Next Page: {self.page + 1 if self.has_more else '[END]'}"
        )
        if not self.content:
            lines.append("[EMPTY_FILE]")
        else:
            lines.append(self.content)
        return "\n".join(lines)


def view_file_content(
    repo: GitRepository,
    file_path: str,
    page: int = 0,
) -> ViewFileContentObservation:
    """
    Read and retrieve file content with pagination support.

    Args:
        repo (GitRepository): Repository object containing the file
        file_path (str): Path to the file relative to the repository root
        page (int, optional): Page number to view (zero-indexed). Defaults to 0.

    Returns:
        ViewFileContentObservation: Object containing the file content and pagination info
    """
    # Number of lines to display per page
    lines_per_page = 100

    # Get the absolute path of the file
    file_path = normalize_path(file_path)
    path = Path(repo.repo_path) / file_path

    content = read_file_content(path)

    page_start = page * lines_per_page
    page_end = (page + 1) * lines_per_page
    lines = content.splitlines()

    codes = []
    for line_num, line in enumerate(
        lines[page_start:page_end], start=page_start + 1
    ):
        # Format line number as 4 digits and separate with | character
        codes.append(f"{line_num:4d} | {line.rstrip()}")

    return ViewFileContentObservation(
        page=page,
        has_more=len(lines) > page_end,
        content="\n".join(codes),
    )


class ViewFileContentInput(BaseModel):
    file_path: str = Field(
        description="The path to the file in the repository."
    )
    page: int = Field(
        default=0, description="The page number to view. Default is 0."
    )


class ViewFileContentTool(BaseTool):
    name: str = "view_file_content"
    description: str = """
    Use this tool to read the content of a file in the repository.
    """

    repo: GitRepository

    args_schema: Type[BaseModel] = ViewFileContentInput  # type: ignore

    def _run(self, file_path: str, page: int = 0) -> str:
        try:
            result = view_file_content(
                self.repo,
                file_path=file_path,
                page=page,
            )
            return result.render()
        except FileNotFoundError:
            Logger.info(f"File {file_path} not found.")
            return f"File {file_path} not found."
        except Exception as e:
            Logger.error(
                f"Error reading file {file_path}: {str(e)}", exc_info=True
            )
            return f"Error occurred while reading the file."
