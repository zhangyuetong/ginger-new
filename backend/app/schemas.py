from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GuessPatchBody(BaseModel):
    guessZh: str




class SpanDto(BaseModel):
    kind: str
    value: str
    lemma: str | None = None
    guessZh: str | None = None


class SenseDto(BaseModel):
    n: int | None = None
    text: str
    renderedSpans: list[SpanDto]


class PosBlockDto(BaseModel):
    pos: str | None = None
    posGuessZh: str | None = None
    senses: list[SenseDto]


class RenderedDto(BaseModel):
    posBlocks: list[PosBlockDto]


class EntryListRow(BaseModel):
    id: int
    word: str
    colorIdx: int | None = Field(default=None)
    guessZh: str | None = None
    preview: str | None = None
    extras: dict[str, Any] | None = None


class EntryDetail(BaseModel):
    id: int
    word: str
    colorIdx: int | None = None
    definitionRaw: str | None = None
    definition: dict[str, Any]
    extras: dict[str, Any]
    rendered: RenderedDto
    guessZh: str | None = None
    updatedAt: str


class EntriesPage(BaseModel):
    items: list[EntryListRow]
    nextCursor: int | None = None


class HealthDto(BaseModel):
    ok: bool = True
