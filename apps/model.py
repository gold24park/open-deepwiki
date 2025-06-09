from datetime import timedelta

from msgspec import Struct, field
from pydantic import BaseModel, Field


class WikiMetadata(BaseModel):
    owner: str
    repo: str


class WikiPage(BaseModel):
    path: str = Field(
        description="Path of the wiki page. e.g. /getting-started.md"
    )
    title: str = Field(description="Title of the wiki page.")
    description: str = Field(
        description="Brief description of what this page will cover."
    )
    relevant_files: list[str] = Field(
        default_factory=list,
        description="List of relevant files for this wiki page.",
    )
    relevant_page_paths: list[str] = Field(
        default_factory=list,
        description="List of relevant wiki page paths.",
    )


class WikiStructure(BaseModel):
    title: str = Field(description="Title of the wiki.")
    pages: list[WikiPage] = Field(
        default_factory=list, description="List of wiki pages."
    )


class Wiki(Struct, frozen=True):
    """위키 페이지를 생성하기 위한 저장소 정보를 정의합니다."""

    repository: str | None = None
    """위키 페이지를 생성할 저장소의 이름입니다. 설정하지 않으면 동일한 저장소가 사용됩니다."""

    branch: str | None = None
    """위키 페이지를 생성할 브랜치입니다. 설정하지 않으면 기본 브랜치가 사용됩니다."""

    directory: str = field(default="/wikis")
    """위키 페이지를 생성할 디렉토리입니다. (기본값: "/wikis")"""


class WikiConfiguration(Struct, frozen=True):
    """위키 페이지를 생성하기 위한 설정을 정의합니다."""

    wiki: Wiki = field(default_factory=Wiki)
    """위키 페이지를 생성하기 위한 저장소 정보입니다."""

    skip: timedelta = field(default=timedelta(days=7))
    """"Wiki 페이지 생성을 건너뛰는 주기입니다. (기본값: 7일)"""

    language: str = field(default="English")
    """Wiki 페이지의 언어입니다. (기본값: English)"""

    model: str | None = None
    """Wiki 페이지 생성을 위한 모델입니다. (기본값: None)"""

    ignore_patterns: list[str] = field(default_factory=list)
    """코드 인덱싱에서 무시할 파일 패턴을 정의합니다. (glob 패턴 사용)"""

    tutorial: list[str] = field(default_factory=list)
    """초보자가 쉽게 시작할 수 있는 튜토리얼이나 사전 준비 문서입니다."""

    how_to: list[str] = field(default_factory=list)
    """배경지식이 있는 상태에서 기술이나 도구를 사용하다 생기는 특정한 문제를 해결하고 싶을때 사용합니다."""

    reference: list[str] = field(default_factory=list)
    """이미 기본적인 작동 방법을 알고 있는 상태에서 특정 기능이나 API 사용법을 확인해서 적용하고 싶을 때 사용합니다."""

    explanation: list[str] = field(default_factory=list)
    """개념, 원리, 배경 지식을 깊이 이해하고 싶을 때 사용합니다."""
