from typing import List

import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from apps.git import GitRepository
from apps.settings import Logger
from apps.tools.common import Observation
from apps.utils import make_sync

INDEX_SEARCH_ENDPOINT = "https://api.github.com/search/code"


class GHSearchResult(BaseModel):
    file_path: str
    score: float
    fragments: List[str]


class SearchSymbolObservation(Observation):
    results: List[GHSearchResult]

    def render(self) -> str:
        self.results.sort(key=lambda x: x.score, reverse=True)

        lines = []
        lines.append(f"Found {len(self.results)} results:")
        for result in self.results:
            lines.append(f">> File: {result.file_path}")
            lines.append(f">> Score: {result.score}")
            lines.append(">> Fragments:")
            for fragment in result.fragments:
                lines.append(f"---\n{fragment}")
            lines.append("")
        return "\n".join(lines)


async def code_index_search(
    repo: GitRepository, symbol: str
) -> SearchSymbolObservation:
    query = "{symbol}+in:file+repo:{owner}/{repo}".format(
        symbol=symbol, owner=repo.owner, repo=repo.repo
    )
    headers = {
        "Accept": "application/vnd.github.text-match+json",
        "Authorization": "Bearer {token}".format(token=repo.pat),
        "X-Github-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{INDEX_SEARCH_ENDPOINT}?q={query}", headers=headers
        )

    res.raise_for_status()
    result = res.json()

    results = []
    for item in result["items"]:
        result = GHSearchResult(
            file_path=item["path"],  # relative path
            score=item["score"],
            fragments=[m["fragment"] for m in item["text_matches"]],
        )
        results.append(result)

    return SearchSymbolObservation(results=results)


class CodeIndexSearchTool(BaseTool):
    name: str = "code_index_search"
    description: str = """
    Searches for a specific symbol (e.g., class name, function name, constant) within the default branch of a GitHub repository using GitHub's code search API.
    This tool queries files where the symbol appears and returns a list of matches, including file paths and surrounding code fragments. The results are sorted in descending order of relevance (score). 
    Useful for locating the definition or usage context of a symbol in the codebase.
    """

    repo: GitRepository

    def _run(self, symbol: str) -> str:
        return make_sync(self._arun)(symbol)

    async def _arun(self, symbol: str) -> str:
        try:
            result = await code_index_search(self.repo, symbol)
            return result.render()
        except Exception as e:
            Logger.error(
                f"Error searching for symbol {symbol}: {str(e)}", exc_info=True
            )
            return f"Error occurred while searching for symbol {symbol}."
