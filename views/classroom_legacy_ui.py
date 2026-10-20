"""Course references to pre-existing CSV records; original rows stay in place."""
import uuid
import streamlit as st

from classroom_core import ClassroomError, PermissionDenied
from classroom_core.legacy import resolve_reference

KINDS = {"material": "기존 자료실", "submission": "기존 과제방", "question": "기존 질문 보드",
         "sudanote": "기존 수다노트", "observation": "내 기존 관찰 기록"}
TABLES = {"material": "materials", "submission": "submissions", "question": "questions",
          "sudanote": "sudanotes", "observation": "observations"}


def render_legacy_records(service, course):
    if not st.toggle("기존 자료·기록 연결 보기", key="classroom_legacy_toggle_" + course["id"]):
        return
    import storage as db
    actor = service.actor()
    cid = course["id"]
    current = service._course(cid)
    teacher = actor["role"] == "teacher"
    kinds = list(KINDS) if teacher else ["material", "submission", "question", "sudanote"]
    st.caption("원본을 복제하지 않고 기존 기록의 ID만 연결합니다.")
    if teacher and not current.get("archived"):
        kind = st.selectbox("기록 종류", kinds, format_func=KINDS.get, key="classroom_legacy_kind_" + cid)
        rows = []
        for row in db.read(TABLES[kind]):
            if kind == "material":
                allowed = row.get("subject") == current["subject"]
            else:
                allowed = row.get("student_id") in current["student_ids"]
                if kind != "observation":
                    allowed = allowed and row.get("subject") == current["subject"]
            if allowed:
                rows.append(row)
        records = {r["id"]: r for r in rows}
        if records:
            selected = st.selectbox("연결할 원본", list(records),
                                    format_func=lambda value: " · ".join(str(records[value].get(k, "")) for k in ("student_id", "title", "created_at", "uploaded_at")),
                                    key="classroom_legacy_record_" + cid)
            if st.button("이 수업에 원본 연결", key="classroom_legacy_add_" + cid):
                resolve_reference(actor, cid, kind, selected)
                service._course(cid, teacher=True, write=True)
                # Deterministic ID makes repeated clicks idempotent.
                link_id = uuid.uuid5(uuid.NAMESPACE_URL, cid + ":" + kind + ":" + selected).hex
                old = service.store.get("legacy_links", link_id)
                if not old:
                    service._write("legacy_links", link_id, dict(id=link_id, course_id=cid, kind=kind,
                                                               record_id=selected, teacher_id=actor["id"]),
                                   None, "legacy.reference")
                st.success("원본 기록을 연결했습니다.")
        else:
            st.info("연결할 기존 기록이 없습니다.")
    links = [r for r in service.store.list("legacy_links") if r.get("course_id") == cid]
    visible = 0
    for link in links:
        kind = link["kind"]
        if kind not in kinds:
            continue
        try:
            row = resolve_reference(actor, cid, kind, link["record_id"])
        except PermissionDenied:
            continue
        visible += 1
        with st.expander(KINDS[kind] + " · " + (row.get("title") or row.get("created_at") or row["id"])):
            if kind == "sudanote":
                for i in range(1, 6):
                    st.write(row.get(f"q{i}", ""))
            else:
                st.write(row.get("description") or row.get("content", ""))
            if kind == "submission":
                st.write(row.get("feedback", ""))
                st.write(row.get("teacher_comment", ""))
            elif kind == "question":
                st.write(row.get("answer", ""))
            if row.get("file_id"):
                # Access was checked immediately above before loading bytes.
                resolve_reference(actor, cid, kind, link["record_id"])
                raw = db.load_file_cached(row["file_id"])
                if raw is not None:
                    st.download_button(row.get("file_name") or "첨부 파일", raw,
                                       file_name=row.get("file_name") or "attachment",
                                       key="classroom_legacy_file_" + link["id"])
    if not visible:
        st.info("아직 접근 가능한 기존 연결 기록이 없습니다.")
