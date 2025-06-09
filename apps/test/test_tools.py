import pytest

from apps.git import GitRepository
from apps.tools.list_files import list_files
from apps.tools.semantic_search_files import semantic_search_files
from apps.tools.view_file_content import view_file_content

# python -m pytest apps/test/test_tools.py -v


def test_list_files(repo: GitRepository):
    result = list_files(repo, "/")
    rendered = result.render()
    print(rendered)
    assert ".git/" not in rendered
    assert len(result.files) > 0
    assert result.total_files > 0


@pytest.mark.asyncio
async def test_semantic_search_files(repo: GitRepository):
    result = await semantic_search_files("pyproject.toml", repo)
    assert len(result.files) > 0


def test_view_file_content(repo: GitRepository):
    result = view_file_content(repo, "apps/app.py", page=2)
    print(result.render())
    assert len(result.content) > 0
