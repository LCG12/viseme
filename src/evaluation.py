from __future__ import annotations

from pathlib import Path

from .io_utils import write_csv


HUMAN_RATING_FIELDS = [
    "paragraph_id",
    "rater_id",
    "lip_sync_score",
    "viseme_clarity_score",
    "naturalness_score",
    "overall_score",
    "comment",
]

ISSUE_LOG_FIELDS = [
    "paragraph_id",
    "time_ms",
    "syllable",
    "issue_type",
    "description",
    "suggested_fix_stage",
]


def ensure_evaluation_templates(sample_dir: str | Path, paragraph_id: str):
    sample_dir = Path(sample_dir)
    rating_path = sample_dir / "human_rating.csv"
    issue_path = sample_dir / "issue_log.csv"

    if not rating_path.is_file():
        write_csv(
            rating_path,
            [
                {
                    "paragraph_id": paragraph_id,
                    "rater_id": "",
                    "lip_sync_score": "",
                    "viseme_clarity_score": "",
                    "naturalness_score": "",
                    "overall_score": "",
                    "comment": "",
                }
            ],
            HUMAN_RATING_FIELDS,
        )

    if not issue_path.is_file():
        write_csv(
            issue_path,
            [
                {
                    "paragraph_id": paragraph_id,
                    "time_ms": "",
                    "syllable": "",
                    "issue_type": "",
                    "description": "",
                    "suggested_fix_stage": "",
                }
            ],
            ISSUE_LOG_FIELDS,
        )

