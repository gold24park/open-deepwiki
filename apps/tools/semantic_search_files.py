import os
from pathlib import Path
from typing import List, Tuple

from langchain_core.tools import BaseTool

from apps.git import GitRepository
from apps.retriever import get_retriever
from apps.settings import Logger
from apps.tools.common import Observation, TextSplitCriteria, read_file_content
from apps.utils import make_sync


class SemanticSearchFileObservation(Observation):
    files: List[Tuple[str, str]] = []

    def render(self) -> str:
        lines = [f"Found {len(self.files)} related files:\n\n"]
        for file_path, content in self.files:
            lines.append(f"[{file_path}]")
            lines.append(f"Preview: {content}\n")
        return "\n".join(lines)


async def semantic_search_files(
    query: str,
    repo: GitRepository,
) -> SemanticSearchFileObservation:
    """
    Asynchronously search for relevant files using semantic search with the given query.

    Args:
        query (str): The natural language query to search with
        repo (GitRepository): Repository to search in

    Returns:
        SemanticSearchFileObservation: Search results with file paths and content previews
    """
    result = SemanticSearchFileObservation()

    preview_length = 160
    retriever = await get_retriever(repo)
    documents = await retriever.ainvoke(query)

    if not documents:
        return result

    file_paths = [doc.metadata["file_path"] for doc in documents]

    for file_path in file_paths:
        path = Path(repo.repo_path) / file_path

        content = read_file_content(
            path,
            ignore_errors=True,
            split_criteria=TextSplitCriteria.LENGTH,
            split_size=preview_length,
        )

        if not content:
            continue

        # If file was read successfully, add it to the result list
        rel_path = os.path.relpath(path, repo.repo_path)
        result.files.append((rel_path, content))

    return result


class SemanticSearchFilesTool(BaseTool):
    name: str = "semantic_search_files"
    description: str = """
    Use this tool to retrieve relevant files from the repository by searching with natural language queries.
    For specific file symbols (class names, or method names), Use `code_index_search` tool instead.
    """

    repo: GitRepository

    def _run(self, query: str) -> str:
        return make_sync(self._arun)(query)

    async def _arun(self, query: str) -> str:
        try:
            result = await semantic_search_files(query, self.repo)
            return result.render()
        except Exception as e:
            Logger.error(
                f"Error during semantic search: {str(e)}", exc_info=True
            )
            return f"Error occurred during semantic search."
