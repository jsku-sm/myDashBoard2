"""No runtime dependencies: imported by the existing storage backend."""
SCHEMAS = {
    'as_cohorts': ['id','owner_id','year','name','description','start_date','end_date','state',
                   'members_json','revision','created_at','updated_at','history_json','request_hash'],
    'as_posts': ['id','cohort_id','owner_id','author_id','author_name','kind','title','body',
                 'visibility','published','pinned','lesson_date','due_at','allow_late',
                 'comments_enabled','resolved','attachments_json','links_json','revision',
                 'created_at','updated_at','deleted_at','request_hash'],
    'as_comments': ['id','cohort_id','owner_id','post_id','author_id','author_name','body',
                    'created_at','updated_at','revision','deleted_at','request_hash'],
    'as_submissions': ['id','cohort_id','owner_id','post_id','student_id','student_name',
                       'attempt','body','attachments_json','assignment_revision','late',
                       'created_at','feedback','feedback_at','revision','request_hash'],
}
TABLES = frozenset(SCHEMAS)
PARTITIONED = frozenset({'as_posts','as_comments','as_submissions'})
