import os

import pytest

from apps.context import Context
from apps.model import WikiConfiguration
from apps.settings import PROJECT_DIR
from apps.wiki_page import GeneratePages
from apps.wiki_structure import GenerateStructure, WikiStructure


@pytest.fixture
def structure() -> WikiStructure:
    file = os.path.join(PROJECT_DIR, "test", "cached_structure.json")
    return WikiStructure.model_validate_json(open(file).read())


@pytest.fixture
def config() -> WikiConfiguration:
    return WikiConfiguration(
        model="google/gemini-2.0-flash",
        ignore_patterns=["**/*.json"],
        reference=["Agent Tools"],
    )


@pytest.fixture
def context(repo, config) -> Context:
    return Context(git_repo=repo, config=config)


@pytest.mark.asyncio
async def test_page(context: Context, structure: WikiStructure):
    result = await GeneratePages.invoke(context, input=structure)
    print(result.error)
    assert result.status == "success"


@pytest.mark.asyncio
async def test_structure(context: Context):
    result = await GenerateStructure.invoke(context)
    assert result.status == "success"

    structure = result.value
    assert isinstance(structure, WikiStructure)
    assert len(structure.pages) > 0
