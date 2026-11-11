SCHEMAS = {
    "reward_rooms": ["id", "owner_id", "code", "title", "unit", "topics_json", "difficulty", "game", "mode",
                     "targets_json", "questions_json", "status", "duration", "seed", "goal", "created_at", "started_at", "ended_at"],
    "reward_attempts": ["id", "room_id", "student_id", "name", "class", "alias", "state_json", "revision", "joined_at", "updated_at"],
}
TABLES = set(SCHEMAS)
PARTITIONED = TABLES.copy()
