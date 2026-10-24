"""Additive tables; existing student/quiz/assessment records are not migrated."""
SCHEMAS = {
    "game_profiles": ["id", "student_id", "name", "class", "state_json", "revision", "updated_at"],
    "game_questions": ["id", "owner_id", "topic_id", "question_json", "published", "revision", "updated_at"],
    "game_missions": ["id", "owner_id", "title", "topic_id", "targets_json", "active", "allow_points", "created_at"],
    "game_resources": ["id", "owner_id", "topic_id", "title", "file_id", "file_name", "mime", "classes_json", "created_at"],
}
TABLES = set(SCHEMAS)
PARTITIONED = {"game_profiles"}
