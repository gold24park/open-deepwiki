import asyncio
import os
import shutil

import pytest

from apps.retriever import get_retriever
from apps.settings import INDEX_DIR


@pytest.fixture
def clean_index(repo):
    """
    테스트 전에 인덱스 디렉토리를 정리하는 fixture
    """
    # 인덱스 디렉토리 정리
    folder_path = os.path.join(INDEX_DIR, repo.owner, repo.repo)
    shutil.rmtree(folder_path, ignore_errors=True)

    yield

    # 테스트 후 정리
    shutil.rmtree(folder_path, ignore_errors=True)


@pytest.mark.asyncio
async def test_concurrent_retriever_access_no_race_condition(repo, clean_index):
    """
    여러 코루틴이 동시에 retriever에 접근할 때 인덱스가 한 번만 생성되는지 테스트
    """
    # 인덱스가 없는 상태에서 여러 코루틴이 동시에 retriever에 접근
    tasks = [
        asyncio.create_task(get_retriever(git_repo=repo)) for _ in range(5)
    ]
    retrievers = await asyncio.gather(*tasks)

    # 모든 retriever가 동일한 인스턴스인지 확인
    first_retriever_id = id(retrievers[0])
    for i, retriever in enumerate(retrievers[1:], 1):
        assert id(retriever) == first_retriever_id, (
            f"retriever #{i}가 첫 번째 retriever와 다른 인스턴스입니다."
        )

    print("모든 retriever가 같은 인스턴스를 참조하고 있습니다.")
