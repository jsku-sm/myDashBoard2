"""New additive tables; legacy records keep their existing schema."""
SCHEMAS = {
    "review_rooms": ["id", "owner_id", "code", "title", "mode", "classes_json", "targets_json", "questions_json",
                     "source_json", "status", "duration", "created_at", "started_at", "ended_at", "review_qid", "reveal"],
    "review_attempts": ["id", "room_id", "student_id", "name", "class", "alias", "team", "answers_json",
                        "joined_at", "updated_at", "revision"],
}
TABLES = set(SCHEMAS)
PARTITIONED = set(SCHEMAS)
