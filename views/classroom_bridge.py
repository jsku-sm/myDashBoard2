"""Read the same classroom records from the original functional menus."""
import streamlit as st


def render_shared_records(user, kind, subject=None):
    key = "classroom_bridge_" + kind + "_" + (subject or "all")
    if not st.toggle("클래스룸 연결 기록 함께 보기", key=key):
        return
    from classroom_core import ClassroomService, ClassroomError, get_store
    from classroom_core.work import WorkService
    try:
        service = ClassroomService(get_store(), user)
        courses = [c for c in service.list_courses() if c.get("membership_status") != "pending"
                   and (subject is None or c.get("subject") == subject)]
        if not courses:
            st.info("승인되거나 담당하는 클래스룸 수업이 없습니다.")
            return
        mapping = {c["id"]: c for c in courses}
        cid = st.selectbox("연결한 수업", list(mapping), format_func=lambda value: mapping[value]["title"], key=key + "_course")
        course = mapping[cid]
        work = WorkService(service)
        st.caption("클래스룸과 같은 원본 기록을 조회합니다.")
        if kind == "assignments":
            from views.classroom_work import render_assignments
            render_assignments(service, course)
        elif kind in ("reflections", "observations"):
            rows = work.reflections(cid) if kind == "reflections" else work.observations(cid)
            if not rows:
                st.info("아직 연결한 기록이 없습니다.")
            for row in rows:
                title = row.get("student_id", "") + " · " + row.get("updated_at", "")
                with st.expander(title):
                    if row.get("legacy_ref"):
                        from classroom_core.legacy import resolve_reference
                        original = resolve_reference(user, cid, "sudanote" if kind == "reflections" else "observation", row["legacy_ref"])
                        if kind == "reflections":
                            for i in range(1, 6):
                                st.write(original.get(f"q{i}", ""))
                        else:
                            st.write(original.get("content", ""))
                    else:
                        st.write(row.get("body", ""))
                    if row.get("assignment_id"):
                        st.caption("연결 과제 ID · " + row["assignment_id"])
    except ClassroomError as error:
        st.info(str(error))
