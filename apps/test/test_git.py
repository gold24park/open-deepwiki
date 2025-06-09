import os
import subprocess
from datetime import datetime

from apps.git import GitRepository, WikiRepository


def test_clone(repo: GitRepository):
    assert os.path.exists(repo.repo_path)
    assert os.path.exists(os.path.join(repo.repo_path, ".git"))


def test_checkout(repo: GitRepository):
    branch = "apne2-cb-slack"
    repo.checkout(branch=branch)

    assert repo.branch == branch

    try:
        repo.checkout(branch="branch-not-exist")
    except subprocess.CalledProcessError as e:
        assert True
    except Exception as e:
        assert False, f"Unexpected exception: {e}"


def test_download(repo: GitRepository):
    repo.download()
    assert os.path.exists(repo.repo_path)
    assert os.path.exists(os.path.join(repo.repo_path, ".git"))


def test_most_updated_files(repo: GitRepository):
    r1 = repo.get_most_updated_files(
        top_n=10,
    )
    assert len(r1) == 10

    r2 = repo.get_most_updated_files(
        top_n=10,
        filter_exists=True,
    )
    assert len(r2) == 10
    assert r1 != r2


def test_list_diff_files(repo: GitRepository):
    diffs = []
    for diff in repo.list_diff_files("170554"):
        diffs.append(diff)
    assert len(diffs) > 0


def test_last_commit_time(wiki_repo: WikiRepository):
    wiki_repo.download()
    last_commit_time = wiki_repo.get_last_commit_time()
    assert last_commit_time is not None
    assert isinstance(last_commit_time, datetime)
