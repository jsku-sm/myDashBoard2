"""Focused storage projections preserve histories while reducing shared-lock work."""
from copy import deepcopy
import json
import pytest
from cryptography.fernet import Fernet
from record_core.archive import ArchiveCrypto, TABLE_CATEGORIES, snapshot_tables, table_bundle
from game_core import play_lab_engine, function_quiz_engine


@pytest.mark.parametrize('table', TABLE_CATEGORIES)
def test_filtered_snapshot_preserves_complete_archive_and_empty_deletion(table):
    source={name:[] for name in TABLE_CATEGORIES}
    source['users']=[{'id':sid,'name':'검증'+sid,'class':'1-1'} for sid in ('1','2')]
    source[table]=[{'id':sid,'student_id':sid,'quiz_id':'q'+sid,'room_id':'r'+sid,
                    'details':{'attempts':[1,2]},'file_id':'file'+sid} for sid in ('1','2')]
    for related in ('quiz_sets','review_rooms','quizpop_rooms','reward_rooms'):
        source[related]=[{'id':('q' if related=='quiz_sets' else 'r')+sid,'title':'문제',
                          'targets_json':'private','questions':{'items':[1,2]}} for sid in ('1','2')]
    crypto=ArchiveCrypto(Fernet.generate_key().decode())
    snapshot=snapshot_tables(source,[(table,'1')])
    for sid in ('1','removed'):
        def build(data):
            return table_bundle(crypto,table,sid,data[table],data,lambda fid:fid.encode())[1]
        before,after=build(source),build(snapshot)
        assert before['payload']==after['payload'] and before['version']==after['version']
        assert before['attachments']==after['attachments']
    # A concurrent write after releasing the backend lock cannot change the snapshot.
    source[table][0]['details']['attempts'].append(3)
    assert snapshot[table][0]['details']['attempts']==[1,2]
    assert len(snapshot[table])==len(snapshot['users'])==1


def test_unrelated_student_tables_are_not_copied():
    class MustNotCopy:
        def __deepcopy__(self,memo):
            raise AssertionError('unrelated records should never be copied')
    source={'users':[{'id':'mine'},{'id':'other','history':MustNotCopy()}],
            'sudanotes':[{'student_id':'mine','q1':'학습 설명'}, {'student_id':'other','large':MustNotCopy()}],
            'game_profiles':[{'student_id':'mine','large':MustNotCopy()}]}
    assert snapshot_tables(source,[])=={}
    result=snapshot_tables(source,[('sudanotes','mine')])
    assert set(result)=={'users','sudanotes'} and len(result['sudanotes'])==1


def test_play_projections_leave_full_history_available_for_growth_and_records():
    arcade=play_lab_engine.initial()
    arcade['records']=[{'note':'기록'+str(i)} for i in range(35)]
    before=deepcopy(arcade)
    assert play_lab_engine.public(arcade,history=False)['records']==[]
    assert len(play_lab_engine.public(arcade)['records'])==30
    assert arcade==before
    quiz=function_quiz_engine.initial()
    quiz['records']=[{'note':'응답'+str(i)} for i in range(35)]
    before=deepcopy(quiz)
    assert function_quiz_engine.public(quiz,history=False)['records']==[]
    assert len(function_quiz_engine.public(quiz)['records'])==30
    assert quiz==before
