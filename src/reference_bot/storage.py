from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import re
import sqlite3

from reference_bot.episodes import (
    BookMention,
    ConceptCluster,
    ConceptMention,
    ConceptRelationship,
    Episode,
    EpisodeSummary,
    IndexedTranscript,
    TranscribedEpisode,
    TranscriptSearchResult,
)
from reference_bot.normalization import expanded_query_terms, query_terms


SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    guid TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    published_at TEXT,
    episode_url TEXT,
    audio_url TEXT,
    audio_local_path TEXT,
    audio_downloaded_at TEXT,
    audio_download_error TEXT,
    audio_deleted_at TEXT,
    audio_delete_error TEXT,
    transcript_local_path TEXT,
    transcribed_at TEXT,
    transcription_error TEXT,
    obsidian_transcript_path TEXT,
    obsidian_transcript_status TEXT,
    obsidian_transcript_exported_at TEXT,
    obsidian_transcript_export_error TEXT,
    description TEXT,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


TRANSCRIPT_CHUNKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcript_chunks (
    episode_guid TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    transcript_local_path TEXT NOT NULL,
    obsidian_transcript_path TEXT,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (episode_guid, chunk_index),
    FOREIGN KEY (episode_guid) REFERENCES episodes(guid) ON DELETE CASCADE
);
"""


EPISODE_SUMMARIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS episode_summaries (
    episode_guid TEXT PRIMARY KEY,
    one_sentence_summary TEXT NOT NULL,
    key_points_text TEXT NOT NULL,
    topics_text TEXT NOT NULL,
    summary_note_path TEXT,
    generated_by TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_guid) REFERENCES episodes(guid) ON DELETE CASCADE
);
"""


BOOK_MENTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS book_mentions (
    episode_guid TEXT NOT NULL,
    name TEXT NOT NULL,
    mention_level TEXT NOT NULL,
    evidence TEXT NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (episode_guid, name),
    FOREIGN KEY (episode_guid) REFERENCES episodes(guid) ON DELETE CASCADE
);
"""


CONCEPT_MENTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS concept_mentions (
    episode_guid TEXT NOT NULL,
    name TEXT NOT NULL,
    mention_level TEXT NOT NULL,
    evidence TEXT NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (episode_guid, name),
    FOREIGN KEY (episode_guid) REFERENCES episodes(guid) ON DELETE CASCADE
);
"""


CONCEPT_CLUSTERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS concept_clusters (
    episode_guid TEXT NOT NULL,
    cluster_name TEXT NOT NULL,
    mention_name TEXT NOT NULL,
    mention_level TEXT NOT NULL,
    evidence TEXT NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (episode_guid, cluster_name, mention_name),
    FOREIGN KEY (episode_guid) REFERENCES episodes(guid) ON DELETE CASCADE
);
"""


CONCEPT_RELATIONSHIPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS concept_relationships (
    episode_guid TEXT NOT NULL,
    source_name TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    target_name TEXT NOT NULL,
    evidence TEXT NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (episode_guid, source_name, relation_type, target_name),
    FOREIGN KEY (episode_guid) REFERENCES episodes(guid) ON DELETE CASCADE
);
"""


AUDIO_DOWNLOAD_COLUMNS = {
    "audio_local_path": "TEXT",
    "audio_downloaded_at": "TEXT",
    "audio_download_error": "TEXT",
    "audio_deleted_at": "TEXT",
    "audio_delete_error": "TEXT",
}


TRANSCRIPTION_COLUMNS = {
    "transcript_local_path": "TEXT",
    "transcribed_at": "TEXT",
    "transcription_error": "TEXT",
}


OBSIDIAN_EXPORT_COLUMNS = {
    "obsidian_transcript_path": "TEXT",
    "obsidian_transcript_status": "TEXT",
    "obsidian_transcript_exported_at": "TEXT",
    "obsidian_transcript_export_error": "TEXT",
}


def initialize_database(database_path: str) -> None:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as connection:
        connection.execute(SCHEMA)
        connection.execute(TRANSCRIPT_CHUNKS_SCHEMA)
        connection.execute(EPISODE_SUMMARIES_SCHEMA)
        connection.execute(BOOK_MENTIONS_SCHEMA)
        connection.execute(CONCEPT_MENTIONS_SCHEMA)
        connection.execute(CONCEPT_CLUSTERS_SCHEMA)
        connection.execute(CONCEPT_RELATIONSHIPS_SCHEMA)
        _ensure_columns(connection, "episodes", AUDIO_DOWNLOAD_COLUMNS)
        _ensure_columns(connection, "episodes", TRANSCRIPTION_COLUMNS)
        _ensure_columns(connection, "episodes", OBSIDIAN_EXPORT_COLUMNS)


def _ensure_columns(
    connection: sqlite3.Connection,
    table_name: str,
    columns: dict[str, str],
) -> None:
    existing_columns = {
        row[1] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }

    for column_name, column_type in columns.items():
        if column_name not in existing_columns:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def upsert_episodes(database_path: str, episodes: Iterable[Episode]) -> int:
    initialize_database(database_path)
    rows = list(episodes)

    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            """
            INSERT INTO episodes (
                guid,
                title,
                published_at,
                episode_url,
                audio_url,
                description
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guid) DO UPDATE SET
                title = excluded.title,
                published_at = excluded.published_at,
                episode_url = excluded.episode_url,
                audio_url = excluded.audio_url,
                description = excluded.description,
                updated_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    episode.guid,
                    episode.title,
                    episode.published_at,
                    episode.episode_url,
                    episode.audio_url,
                    episode.description,
                )
                for episode in rows
            ],
        )

    return len(rows)


def count_episodes(database_path: str) -> int:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute("SELECT COUNT(*) FROM episodes")
        return int(cursor.fetchone()[0])


def list_episodes(database_path: str, limit: int = 10) -> list[Episode]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                guid,
                title,
                published_at,
                episode_url,
                audio_url,
                description
            FROM episodes
            ORDER BY first_seen_at DESC
            """,
        ).fetchall()

    episodes = [
        Episode(
            guid=row[0],
            title=row[1],
            published_at=row[2],
            episode_url=row[3],
            audio_url=row[4],
            description=row[5],
        )
        for row in rows
    ]
    return sorted(episodes, key=_episode_sort_key, reverse=True)[:limit]


def list_pending_downloads(database_path: str, limit: int = 10) -> list[Episode]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                guid,
                title,
                published_at,
                episode_url,
                audio_url,
                description
            FROM episodes
            WHERE audio_url IS NOT NULL
                AND TRIM(audio_url) != ''
                AND audio_local_path IS NULL
                AND audio_deleted_at IS NULL
            ORDER BY first_seen_at DESC
            """,
        ).fetchall()

    episodes = [
        Episode(
            guid=row[0],
            title=row[1],
            published_at=row[2],
            episode_url=row[3],
            audio_url=row[4],
            description=row[5],
        )
        for row in rows
    ]
    return sorted(episodes, key=_episode_sort_key, reverse=True)[:limit]


def mark_audio_downloaded(database_path: str, guid: str, audio_local_path: str) -> None:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE episodes
            SET
                audio_local_path = ?,
                audio_downloaded_at = CURRENT_TIMESTAMP,
                audio_download_error = NULL,
                audio_deleted_at = NULL,
                audio_delete_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE guid = ?
            """,
            (audio_local_path, guid),
        )


def mark_audio_download_failed(database_path: str, guid: str, error: str) -> None:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE episodes
            SET
                audio_download_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE guid = ?
            """,
            (error, guid),
        )


def get_audio_local_path(database_path: str, guid: str) -> str | None:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT audio_local_path FROM episodes WHERE guid = ?",
            (guid,),
        ).fetchone()

    if row is None:
        return None
    return row[0]


def mark_audio_deleted(database_path: str, guid: str) -> None:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE episodes
            SET
                audio_deleted_at = CURRENT_TIMESTAMP,
                audio_delete_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE guid = ?
            """,
            (guid,),
        )


def mark_audio_delete_failed(database_path: str, guid: str, error: str) -> None:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE episodes
            SET
                audio_delete_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE guid = ?
            """,
            (error, guid),
        )


def list_pending_transcriptions(database_path: str, limit: int = 10) -> list[Episode]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                guid,
                title,
                published_at,
                episode_url,
                audio_url,
                description
            FROM episodes
            WHERE audio_local_path IS NOT NULL
                AND TRIM(audio_local_path) != ''
                AND transcript_local_path IS NULL
            ORDER BY audio_downloaded_at DESC, first_seen_at DESC
            """,
        ).fetchall()

    episodes = [
        Episode(
            guid=row[0],
            title=row[1],
            published_at=row[2],
            episode_url=row[3],
            audio_url=row[4],
            description=row[5],
        )
        for row in rows
    ]
    return sorted(episodes, key=_episode_sort_key, reverse=True)[:limit]


def mark_transcript_imported(database_path: str, guid: str, transcript_local_path: str) -> bool:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE episodes
            SET
                transcript_local_path = ?,
                transcribed_at = CURRENT_TIMESTAMP,
                transcription_error = NULL,
                obsidian_transcript_path = NULL,
                obsidian_transcript_status = NULL,
                obsidian_transcript_exported_at = NULL,
                obsidian_transcript_export_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE guid = ?
            """,
            (transcript_local_path, guid),
        )
        return cursor.rowcount > 0


def mark_transcription_failed(database_path: str, guid: str, error: str) -> None:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE episodes
            SET
                transcription_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE guid = ?
            """,
            (error, guid),
        )


def list_pending_transcript_exports(
    database_path: str,
    limit: int = 10,
) -> list[TranscribedEpisode]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                guid,
                title,
                published_at,
                episode_url,
                audio_url,
                description,
                transcript_local_path
            FROM episodes
            WHERE transcript_local_path IS NOT NULL
                AND TRIM(transcript_local_path) != ''
                AND obsidian_transcript_path IS NULL
            ORDER BY transcribed_at DESC, first_seen_at DESC
            """,
        ).fetchall()

    transcribed_episodes = [
        TranscribedEpisode(
            episode=Episode(
                guid=row[0],
                title=row[1],
                published_at=row[2],
                episode_url=row[3],
                audio_url=row[4],
                description=row[5],
            ),
            transcript_local_path=row[6],
        )
        for row in rows
    ]
    return sorted(
        transcribed_episodes,
        key=lambda item: _episode_sort_key(item.episode),
        reverse=True,
    )[:limit]


def mark_transcript_note_exported(
    database_path: str,
    guid: str,
    obsidian_transcript_path: str,
) -> None:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE episodes
            SET
                obsidian_transcript_path = ?,
                obsidian_transcript_status = 'indexed',
                obsidian_transcript_exported_at = CURRENT_TIMESTAMP,
                obsidian_transcript_export_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE guid = ?
            """,
            (obsidian_transcript_path, guid),
        )


def mark_transcript_note_export_failed(database_path: str, guid: str, error: str) -> None:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE episodes
            SET
                obsidian_transcript_export_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE guid = ?
            """,
            (error, guid),
        )


def list_indexed_transcripts(database_path: str, limit: int = 10) -> list[IndexedTranscript]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                guid,
                title,
                published_at,
                episode_url,
                audio_url,
                description,
                transcript_local_path,
                obsidian_transcript_path
            FROM episodes
            WHERE obsidian_transcript_status = 'indexed'
                AND transcript_local_path IS NOT NULL
                AND TRIM(transcript_local_path) != ''
                AND guid NOT IN (
                    SELECT DISTINCT episode_guid
                    FROM transcript_chunks
                )
            ORDER BY obsidian_transcript_exported_at DESC, first_seen_at DESC
            """,
        ).fetchall()

    transcripts = [
        IndexedTranscript(
            episode=Episode(
                guid=row[0],
                title=row[1],
                published_at=row[2],
                episode_url=row[3],
                audio_url=row[4],
                description=row[5],
            ),
            transcript_local_path=row[6],
            obsidian_transcript_path=row[7],
        )
        for row in rows
    ]
    return sorted(transcripts, key=lambda item: _episode_sort_key(item.episode), reverse=True)[
        :limit
    ]


def list_indexed_episodes(database_path: str, limit: int = 10) -> list[Episode]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                guid,
                title,
                published_at,
                episode_url,
                audio_url,
                description
            FROM episodes
            WHERE obsidian_transcript_status = 'indexed'
            ORDER BY obsidian_transcript_exported_at DESC, first_seen_at DESC
            """,
        ).fetchall()

    episodes = [
        Episode(
            guid=row[0],
            title=row[1],
            published_at=row[2],
            episode_url=row[3],
            audio_url=row[4],
            description=row[5],
        )
        for row in rows
    ]
    return sorted(episodes, key=_episode_sort_key, reverse=True)[:limit]


def replace_transcript_chunks(
    database_path: str,
    transcript: IndexedTranscript,
    chunks: list[str],
) -> int:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "DELETE FROM transcript_chunks WHERE episode_guid = ?",
            (transcript.episode.guid,),
        )
        connection.executemany(
            """
            INSERT INTO transcript_chunks (
                episode_guid,
                chunk_index,
                chunk_text,
                transcript_local_path,
                obsidian_transcript_path
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    transcript.episode.guid,
                    index,
                    chunk,
                    transcript.transcript_local_path,
                    transcript.obsidian_transcript_path,
                )
                for index, chunk in enumerate(chunks)
            ],
        )

    return len(chunks)


def search_transcript_chunks(
    database_path: str,
    query: str,
    limit: int = 10,
) -> list[TranscriptSearchResult]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query cannot be empty.")

    initialize_database(database_path)
    like_terms = [f"%{_escape_like(term)}%" for term in expanded_query_terms(normalized_query)]
    if not like_terms:
        return []

    where_clauses = []
    score_clauses = []
    score_params: list[str] = []
    where_params: list[str] = []
    for like_term in like_terms:
        score_clauses.append("CASE WHEN c.chunk_text LIKE ? ESCAPE '\\' THEN 1 ELSE 0 END")
        score_params.append(like_term)
        where_clauses.append("c.chunk_text LIKE ? ESCAPE '\\'")
        where_params.append(like_term)
    params: list[str | int] = [*score_params, *where_params, limit]
    score_expression = " + ".join(f"({clause})" for clause in score_clauses)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                e.guid,
                e.title,
                e.published_at,
                e.episode_url,
                e.audio_url,
                e.description,
                c.chunk_index,
                c.chunk_text,
                c.transcript_local_path,
                c.obsidian_transcript_path,
                ({score_expression}) AS match_score
            FROM transcript_chunks c
            JOIN episodes e ON e.guid = c.episode_guid
            WHERE {" OR ".join(where_clauses)}
            ORDER BY match_score DESC, e.published_at DESC, c.chunk_index ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return [
        TranscriptSearchResult(
            episode=Episode(
                guid=row[0],
                title=row[1],
                published_at=row[2],
                episode_url=row[3],
                audio_url=row[4],
                description=row[5],
            ),
            chunk_index=row[6],
            chunk_text=row[7],
            transcript_local_path=row[8],
            obsidian_transcript_path=row[9],
        )
        for row in rows
    ]


def list_indexed_episodes_without_summary(
    database_path: str,
    limit: int = 10,
) -> list[IndexedTranscript]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                e.guid,
                e.title,
                e.published_at,
                e.episode_url,
                e.audio_url,
                e.description,
                e.transcript_local_path,
                e.obsidian_transcript_path
            FROM episodes e
            WHERE e.obsidian_transcript_status = 'indexed'
                AND e.transcript_local_path IS NOT NULL
                AND TRIM(e.transcript_local_path) != ''
                AND e.guid NOT IN (
                    SELECT episode_guid
                    FROM episode_summaries
                )
            ORDER BY e.published_at DESC, e.first_seen_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        IndexedTranscript(
            episode=Episode(
                guid=row[0],
                title=row[1],
                published_at=row[2],
                episode_url=row[3],
                audio_url=row[4],
                description=row[5],
            ),
            transcript_local_path=row[6],
            obsidian_transcript_path=row[7],
        )
        for row in rows
    ]


def list_indexed_transcripts_for_summary(
    database_path: str,
    limit: int = 10,
    replace_existing: bool = False,
) -> list[IndexedTranscript]:
    if not replace_existing:
        return list_indexed_episodes_without_summary(database_path, limit=limit)

    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                guid,
                title,
                published_at,
                episode_url,
                audio_url,
                description,
                transcript_local_path,
                obsidian_transcript_path
            FROM episodes
            WHERE obsidian_transcript_status = 'indexed'
                AND transcript_local_path IS NOT NULL
                AND TRIM(transcript_local_path) != ''
            ORDER BY published_at DESC, first_seen_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        IndexedTranscript(
            episode=Episode(
                guid=row[0],
                title=row[1],
                published_at=row[2],
                episode_url=row[3],
                audio_url=row[4],
                description=row[5],
            ),
            transcript_local_path=row[6],
            obsidian_transcript_path=row[7],
        )
        for row in rows
    ]


def upsert_episode_summary(database_path: str, summary: EpisodeSummary) -> None:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO episode_summaries (
                episode_guid,
                one_sentence_summary,
                key_points_text,
                topics_text,
                summary_note_path,
                generated_by
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(episode_guid) DO UPDATE SET
                one_sentence_summary = excluded.one_sentence_summary,
                key_points_text = excluded.key_points_text,
                topics_text = excluded.topics_text,
                summary_note_path = excluded.summary_note_path,
                generated_by = excluded.generated_by,
                generated_at = CURRENT_TIMESTAMP
            """,
            (
                summary.episode.guid,
                summary.one_sentence_summary,
                "\n".join(summary.key_points),
                "\n".join(summary.topics),
                summary.summary_note_path,
                summary.generated_by,
            ),
        )


def get_episode_summary_by_number(
    database_path: str,
    episode_number: int,
) -> EpisodeSummary | None:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                e.guid,
                e.title,
                e.published_at,
                e.episode_url,
                e.audio_url,
                e.description,
                s.one_sentence_summary,
                s.key_points_text,
                s.topics_text,
                s.summary_note_path,
                s.generated_by
            FROM episode_summaries s
            JOIN episodes e ON e.guid = s.episode_guid
            WHERE e.title LIKE ?
            ORDER BY e.published_at DESC
            LIMIT 1
            """,
            (f"%EP.{episode_number}%",),
        ).fetchone()

    if row is None:
        return None

    return EpisodeSummary(
        episode=Episode(
            guid=row[0],
            title=row[1],
            published_at=row[2],
            episode_url=row[3],
            audio_url=row[4],
            description=row[5],
        ),
        one_sentence_summary=row[6],
        key_points=[line for line in row[7].splitlines() if line.strip()],
        topics=[line for line in row[8].splitlines() if line.strip()],
        summary_note_path=row[9],
        generated_by=row[10],
    )


def search_episode_summaries(
    database_path: str,
    query: str,
    limit: int = 5,
) -> list[EpisodeSummary]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query cannot be empty.")

    initialize_database(database_path)
    like_terms = [f"%{_escape_like(term)}%" for term in expanded_query_terms(normalized_query)]
    if not like_terms:
        return []

    where_clauses = []
    score_clauses = []
    score_params: list[str] = []
    where_params: list[str] = []
    for like_term in like_terms:
        score_clauses.append(
            """
            CASE WHEN e.title LIKE ? ESCAPE '\\' THEN 8 ELSE 0 END
            + CASE WHEN s.topics_text LIKE ? ESCAPE '\\' THEN 5 ELSE 0 END
            + CASE WHEN s.one_sentence_summary LIKE ? ESCAPE '\\' THEN 3 ELSE 0 END
            + CASE WHEN s.key_points_text LIKE ? ESCAPE '\\' THEN 1 ELSE 0 END
            """
        )
        score_params.extend([like_term, like_term, like_term, like_term])
        where_clauses.append(
            """
            (
                e.title LIKE ? ESCAPE '\\'
                OR s.one_sentence_summary LIKE ? ESCAPE '\\'
                OR s.key_points_text LIKE ? ESCAPE '\\'
                OR s.topics_text LIKE ? ESCAPE '\\'
            )
            """
        )
        where_params.extend([like_term, like_term, like_term, like_term])
    params: list[str | int] = [*score_params, *where_params, limit]
    score_expression = " + ".join(f"({clause})" for clause in score_clauses)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                e.guid,
                e.title,
                e.published_at,
                e.episode_url,
                e.audio_url,
                e.description,
                s.one_sentence_summary,
                s.key_points_text,
                s.topics_text,
                s.summary_note_path,
                s.generated_by,
                ({score_expression}) AS match_score
            FROM episode_summaries s
            JOIN episodes e ON e.guid = s.episode_guid
            WHERE {" OR ".join(where_clauses)}
            ORDER BY match_score DESC, e.published_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return [
        EpisodeSummary(
            episode=Episode(
                guid=row[0],
                title=row[1],
                published_at=row[2],
                episode_url=row[3],
                audio_url=row[4],
                description=row[5],
            ),
            one_sentence_summary=row[6],
            key_points=[line for line in row[7].splitlines() if line.strip()],
            topics=[line for line in row[8].splitlines() if line.strip()],
            summary_note_path=row[9],
            generated_by=row[10],
        )
        for row in rows
    ]


def list_episode_summaries(database_path: str, limit: int = 100) -> list[EpisodeSummary]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                e.guid,
                e.title,
                e.published_at,
                e.episode_url,
                e.audio_url,
                e.description,
                s.one_sentence_summary,
                s.key_points_text,
                s.topics_text,
                s.summary_note_path,
                s.generated_by
            FROM episode_summaries s
            JOIN episodes e ON e.guid = s.episode_guid
            ORDER BY e.published_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        EpisodeSummary(
            episode=Episode(
                guid=row[0],
                title=row[1],
                published_at=row[2],
                episode_url=row[3],
                audio_url=row[4],
                description=row[5],
            ),
            one_sentence_summary=row[6],
            key_points=[line for line in row[7].splitlines() if line.strip()],
            topics=[line for line in row[8].splitlines() if line.strip()],
            summary_note_path=row[9],
            generated_by=row[10],
        )
        for row in rows
    ]


def replace_book_mentions(database_path: str, episode_guid: str, mentions: list[BookMention]) -> int:
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("DELETE FROM book_mentions WHERE episode_guid = ?", (episode_guid,))
        connection.executemany(
            """
            INSERT INTO book_mentions (episode_guid, name, mention_level, evidence)
            VALUES (?, ?, ?, ?)
            """,
            [
                (episode_guid, mention.name, mention.mention_level, mention.evidence)
                for mention in mentions
            ],
        )
    return len(mentions)


def replace_concept_mentions(
    database_path: str,
    episode_guid: str,
    mentions: list[ConceptMention],
) -> int:
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("DELETE FROM concept_mentions WHERE episode_guid = ?", (episode_guid,))
        connection.executemany(
            """
            INSERT INTO concept_mentions (episode_guid, name, mention_level, evidence)
            VALUES (?, ?, ?, ?)
            """,
            [
                (episode_guid, mention.name, mention.mention_level, mention.evidence)
                for mention in mentions
            ],
        )
    return len(mentions)


def replace_concept_clusters(
    database_path: str,
    episode_guid: str,
    clusters: list[ConceptCluster],
) -> int:
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("DELETE FROM concept_clusters WHERE episode_guid = ?", (episode_guid,))
        connection.executemany(
            """
            INSERT INTO concept_clusters (episode_guid, cluster_name, mention_name, mention_level, evidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    episode_guid,
                    cluster.cluster_name,
                    cluster.mention_name,
                    cluster.mention_level,
                    cluster.evidence,
                )
                for cluster in clusters
            ],
        )
    return len(clusters)


def replace_concept_relationships(
    database_path: str,
    episode_guid: str,
    relationships: list[ConceptRelationship],
) -> int:
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("DELETE FROM concept_relationships WHERE episode_guid = ?", (episode_guid,))
        connection.executemany(
            """
            INSERT INTO concept_relationships (episode_guid, source_name, relation_type, target_name, evidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    episode_guid,
                    relationship.source_name,
                    relationship.relation_type,
                    relationship.target_name,
                    relationship.evidence,
                )
                for relationship in relationships
            ],
        )
    return len(relationships)


def search_book_mentions(database_path: str, query: str, limit: int = 5) -> list[BookMention]:
    return _search_mentions(database_path, query, limit, table_name="book_mentions", result_type="book")


def search_concept_mentions(database_path: str, query: str, limit: int = 8) -> list[ConceptMention]:
    return _search_mentions(database_path, query, limit, table_name="concept_mentions", result_type="concept")


def list_concept_mentions(database_path: str, limit: int = 1000) -> list[ConceptMention]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                e.guid,
                e.title,
                e.published_at,
                e.episode_url,
                e.audio_url,
                e.description,
                m.name,
                m.mention_level,
                m.evidence
            FROM concept_mentions m
            JOIN episodes e ON e.guid = m.episode_guid
            ORDER BY e.published_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        ConceptMention(
            episode=Episode(
                guid=row[0],
                title=row[1],
                published_at=row[2],
                episode_url=row[3],
                audio_url=row[4],
                description=row[5],
            ),
            name=row[6],
            mention_level=row[7],
            evidence=row[8],
        )
        for row in rows
    ]


def search_concept_clusters(database_path: str, query: str, limit: int = 12) -> list[ConceptCluster]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query cannot be empty.")

    initialize_database(database_path)
    like_terms = [f"%{_escape_like(term)}%" for term in expanded_query_terms(normalized_query)]
    if not like_terms:
        return []

    where_clauses = []
    score_clauses = []
    score_params: list[str] = []
    where_params: list[str] = []
    for like_term in like_terms:
        score_clauses.append(
            """
            CASE WHEN c.cluster_name LIKE ? ESCAPE '\\' THEN 8 ELSE 0 END
            + CASE WHEN c.mention_name LIKE ? ESCAPE '\\' THEN 5 ELSE 0 END
            + CASE WHEN c.evidence LIKE ? ESCAPE '\\' THEN 1 ELSE 0 END
            """
        )
        score_params.extend([like_term, like_term, like_term])
        where_clauses.append(
            """
            (
                c.cluster_name LIKE ? ESCAPE '\\'
                OR c.mention_name LIKE ? ESCAPE '\\'
                OR c.evidence LIKE ? ESCAPE '\\'
            )
            """
        )
        where_params.extend([like_term, like_term, like_term])
    params: list[str | int] = [*score_params, *where_params, limit]
    score_expression = " + ".join(f"({clause})" for clause in score_clauses)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                e.guid,
                e.title,
                e.published_at,
                e.episode_url,
                e.audio_url,
                e.description,
                c.cluster_name,
                c.mention_name,
                c.mention_level,
                c.evidence,
                ({score_expression}) AS match_score
            FROM concept_clusters c
            JOIN episodes e ON e.guid = c.episode_guid
            WHERE {" OR ".join(where_clauses)}
            ORDER BY match_score DESC, e.published_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return [
        ConceptCluster(
            episode=Episode(
                guid=row[0],
                title=row[1],
                published_at=row[2],
                episode_url=row[3],
                audio_url=row[4],
                description=row[5],
            ),
            cluster_name=row[6],
            mention_name=row[7],
            mention_level=row[8],
            evidence=row[9],
        )
        for row in rows
    ]


def search_concept_relationships(
    database_path: str,
    query: str,
    limit: int = 12,
) -> list[ConceptRelationship]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query cannot be empty.")

    initialize_database(database_path)
    like_terms = [f"%{_escape_like(term)}%" for term in expanded_query_terms(normalized_query)]
    if not like_terms:
        return []

    where_clauses = []
    score_clauses = []
    score_params: list[str] = []
    where_params: list[str] = []
    for like_term in like_terms:
        score_clauses.append(
            """
            CASE WHEN r.source_name LIKE ? ESCAPE '\\' THEN 8 ELSE 0 END
            + CASE WHEN r.target_name LIKE ? ESCAPE '\\' THEN 5 ELSE 0 END
            + CASE WHEN r.evidence LIKE ? ESCAPE '\\' THEN 1 ELSE 0 END
            """
        )
        score_params.extend([like_term, like_term, like_term])
        where_clauses.append(
            """
            (
                r.source_name LIKE ? ESCAPE '\\'
                OR r.target_name LIKE ? ESCAPE '\\'
                OR r.evidence LIKE ? ESCAPE '\\'
            )
            """
        )
        where_params.extend([like_term, like_term, like_term])
    params: list[str | int] = [*score_params, *where_params, limit]
    score_expression = " + ".join(f"({clause})" for clause in score_clauses)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                e.guid,
                e.title,
                e.published_at,
                e.episode_url,
                e.audio_url,
                e.description,
                r.source_name,
                r.relation_type,
                r.target_name,
                r.evidence,
                ({score_expression}) AS match_score
            FROM concept_relationships r
            JOIN episodes e ON e.guid = r.episode_guid
            WHERE {" OR ".join(where_clauses)}
            ORDER BY match_score DESC, e.published_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return [
        ConceptRelationship(
            episode=Episode(
                guid=row[0],
                title=row[1],
                published_at=row[2],
                episode_url=row[3],
                audio_url=row[4],
                description=row[5],
            ),
            source_name=row[6],
            relation_type=row[7],
            target_name=row[8],
            evidence=row[9],
        )
        for row in rows
    ]


def _search_mentions(
    database_path: str,
    query: str,
    limit: int,
    *,
    table_name: str,
    result_type: str,
):
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query cannot be empty.")

    initialize_database(database_path)
    like_terms = [f"%{_escape_like(term)}%" for term in expanded_query_terms(normalized_query)]
    if not like_terms:
        return []

    where_clauses = []
    score_clauses = []
    score_params: list[str] = []
    where_params: list[str] = []
    for like_term in like_terms:
        score_clauses.append(
            """
            CASE WHEN m.name LIKE ? ESCAPE '\\' THEN 8 ELSE 0 END
            + CASE WHEN m.evidence LIKE ? ESCAPE '\\' THEN 1 ELSE 0 END
            """
        )
        score_params.extend([like_term, like_term])
        where_clauses.append("(m.name LIKE ? ESCAPE '\\' OR m.evidence LIKE ? ESCAPE '\\')")
        where_params.extend([like_term, like_term])
    params: list[str | int] = [*score_params, *where_params, limit]
    score_expression = " + ".join(f"({clause})" for clause in score_clauses)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                e.guid,
                e.title,
                e.published_at,
                e.episode_url,
                e.audio_url,
                e.description,
                m.name,
                m.mention_level,
                m.evidence,
                ({score_expression}) AS match_score
            FROM {table_name} m
            JOIN episodes e ON e.guid = m.episode_guid
            WHERE {" OR ".join(where_clauses)}
            ORDER BY match_score DESC, e.published_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    mention_class = BookMention if result_type == "book" else ConceptMention
    return [
        mention_class(
            episode=Episode(
                guid=row[0],
                title=row[1],
                published_at=row[2],
                episode_url=row[3],
                audio_url=row[4],
                description=row[5],
            ),
            name=row[6],
            mention_level=row[7],
            evidence=row[8],
        )
        for row in rows
    ]


def _query_terms(query: str) -> list[str]:
    return query_terms(query)


def _expanded_mention_terms(query: str) -> list[str]:
    return expanded_query_terms(query)


def _looks_like_cjk(value: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        deduped.append(term)
    return deduped


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _episode_sort_date(episode: Episode) -> datetime:
    if not episode.published_at:
        return datetime.min.replace(tzinfo=timezone.utc)

    try:
        parsed_date = parsedate_to_datetime(episode.published_at)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)

    if parsed_date.tzinfo is None:
        return parsed_date.replace(tzinfo=timezone.utc)

    return parsed_date.astimezone(timezone.utc)


def _episode_sort_key(episode: Episode) -> tuple[int, int, datetime]:
    episode_number = _episode_number(episode.title)
    if episode_number is not None:
        return (1, episode_number, _episode_sort_date(episode))
    return (0, 0, _episode_sort_date(episode))


def _episode_number(title: str) -> int | None:
    match = re.match(r"^\s*EP\.?\s*(\d+)", title, flags=re.IGNORECASE)
    if match is None:
        return None
    return int(match.group(1))
