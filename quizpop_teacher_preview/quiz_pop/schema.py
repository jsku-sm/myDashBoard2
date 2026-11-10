"""Teacher-published quizzes and per-student attempts; no legacy migration."""
SCHEMAS = {
    'quizpop_rooms': ['id','owner_id','code','title','stage','settings_json','questions_json',
                     'targets_json','status','publish_key','created_at','updated_at'],
    'quizpop_attempts': ['id','room_id','student_id','name','class','state_json','revision','joined_at','updated_at'],
}
TABLES = set(SCHEMAS)
PARTITIONED = set(SCHEMAS)
