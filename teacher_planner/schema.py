META = ['id', 'author_id', 'created_at', 'updated_at', 'revision', 'deleted_at']
SCHEMAS = {
    'teacher_diary': META + ['kind', 'date', 'time', 'deadline', 'title', 'body', 'done', 'important'],
    'teacher_timetable': META + ['weekday', 'period', 'class', 'subject', 'content'],
}
TABLES = frozenset(SCHEMAS)
