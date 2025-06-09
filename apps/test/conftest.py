import os
import shutil

import pytest

from apps.git import GitRepository, WikiRepository
from apps.model import WikiConfiguration
from apps.settings import GITHUB_ACCESS_TOKEN, PROJECT_DIR

test_pat = GITHUB_ACCESS_TOKEN
test_repository = "gold24park/open-deepwiki"


@pytest.fixture(scope="session")
def _repo() -> GitRepository:
    return GitRepository(
        pat=test_pat,
        repo_dir=os.path.join(PROJECT_DIR, "test", "repos"),
        repository=test_repository,
    )


@pytest.fixture(scope="session")
def repo(_repo: GitRepository):
    repo_dir = os.path.join(PROJECT_DIR, "test", "repos")
    shutil.rmtree(repo_dir, ignore_errors=True)
    os.makedirs(repo_dir, exist_ok=True)

    _repo.clone()
    yield _repo

    # repository 정리
    shutil.rmtree(repo_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def wiki_repo(repo: GitRepository) -> WikiRepository:
    return WikiRepository(repo, config=WikiConfiguration())
