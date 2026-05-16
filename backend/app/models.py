from datetime import datetime, timezone

from sqlalchemy import Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (UniqueConstraint("word", name="uq_entries_word"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(Text, nullable=False)
    color_idx: Mapped[int | None] = mapped_column(Integer, nullable=True)
    definition_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    definition_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extras_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    guess_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=utc_now_iso,
        onupdate=utc_now_iso,
    )


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    rows_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)
