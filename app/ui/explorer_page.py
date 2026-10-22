"""File Explorer: browse approved folders, select files and send them to the Command Center."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.actions import filesystem as fs
from app.core.action_schema import PathRef
from app.core.permissions import PathViolation
from app.ui import components as C
from app.ui import state

PREVIEW_TEXT = {"txt", "md", "csv", "json", "log", "py", "html", "css", "xml", "yml", "yaml", "ini", "toml"}
PREVIEW_IMG = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}


def _go(cmd: str, auto: str = "preview") -> None:
    state.queue_command(cmd, auto)
    st.switch_page(st.session_state.pages["command"])


def render() -> None:
    s = state.svc()
    st.markdown(C.page_title("File Explorer", "Browse approved folders · select files · hand them to the agent",
                             "folder"), unsafe_allow_html=True)
    roots = s.settings.root_aliases()
    if not roots:
        st.markdown(C.callout("warn", "<b>No approved folders.</b> Add one in Settings → Approved folders."),
                    unsafe_allow_html=True)
        return
    cur: PathRef = st.session_state.get("explorer_at") or PathRef(root=roots[0])
    if cur.root not in roots:
        cur = PathRef(root=roots[0])

    c1, c2 = st.columns([1.2, 3])
    root = c1.selectbox("Approved folder", roots, index=roots.index(cur.root))
    if root != cur.root:
        cur = PathRef(root=root)
    st.session_state.explorer_at = cur

    # breadcrumb
    crumbs = [PathRef(root=cur.root)]
    parts = cur.path.split("/") if cur.path else []
    for i in range(len(parts)):
        crumbs.append(PathRef(root=cur.root, path="/".join(parts[: i + 1])))
    with c2:
        st.caption("Location")
        bc = st.columns(min(len(crumbs), 6) + 1)
        for col, ref in zip(bc, crumbs[-6:]):
            if col.button(ref.name + " /", key=f"bc_{ref.display()}", width="stretch"):
                st.session_state.explorer_at = ref
                st.rerun()

    try:
        folder = s.perms.resolve(cur)
        rows, truncated = fs.list_entries(folder)
    except (PathViolation, OSError) as exc:
        st.markdown(C.callout("bad", f"<b>Cannot open this folder:</b> {exc}"), unsafe_allow_html=True)
        if st.button("Back to root"):
            st.session_state.explorer_at = PathRef(root=cur.root)
            st.rerun()
        return

    dirs = [r for r in rows if r["kind"] == "folder"]
    files = [r for r in rows if r["kind"] == "file"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Folders", len(dirs))
    m2.metric("Files", len(files))
    m3.metric("Total size", fs.human_size(sum(r["size"] for r in files)))
    m4.metric("Access", s.perms.find_root(cur.root).access.replace("_", "/"))

    if dirs:
        st.caption("Subfolders")
        cols = st.columns(6)
        for i, d in enumerate(dirs):
            if cols[i % 6].button(f"📁 {d['name']}", key=f"dir_{cur.display()}_{d['name']}", width="stretch"):
                st.session_state.explorer_at = cur.child(d["name"])
                st.rerun()

    left, right = st.columns([2.2, 1])
    with left:
        if not files:
            st.markdown("<div class='empty'>This folder has no files.</div>", unsafe_allow_html=True)
            picked = []
        else:
            df = pd.DataFrame(files)[["name", "category", "size_h", "modified"]]
            df.columns = ["Name", "Type", "Size", "Modified"]
            event = st.dataframe(df, hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row",
                                 key=f"grid_{cur.display()}", height=min(460, 38 + 35 * len(df)))
            picked = [cur.child(files[i]["name"]) for i in event.selection.rows]
        if truncated:
            st.caption("Showing the first 2000 items.")

    with right:
        st.markdown(C.panel("Selection", "tasks",
                            "".join(C.chip(p.name) for p in picked[:12]) or "<div class='empty'>Tick rows to select files.</div>",
                            meta=f"{len(picked)} selected"), unsafe_allow_html=True)
        if st.button("Use selection in Command Center", type="primary", icon=":material/send:", width="stretch",
                     disabled=not picked):
            st.session_state.selection = picked
            st.session_state.context_folder = cur
            state.push_event("INFO", f"{len(picked)} file(s) selected in {cur.display()}")
            _go("", auto=None)
        if st.button("Set this folder as context", icon=":material/my_location:", width="stretch"):
            st.session_state.context_folder = cur
            state.push_event("INFO", f"Context folder set to {cur.display()}")
            st.toast(f"Commands without a folder will now use {cur.display()}")

        with st.expander("Quick actions", expanded=True):
            new = st.text_input("New folder name", key="qa_folder", placeholder="e.g. Reports")
            if st.button("Create folder here", icon=":material/create_new_folder:", width="stretch",
                         disabled=not new.strip()):
                _go(f"create a folder named '{new.strip()}' in {cur.display().rstrip('/')}", "run")
            prefix = st.text_input("Rename selected with prefix", key="qa_prefix", placeholder="e.g. Event_")
            if st.button("Preview rename", icon=":material/drive_file_rename_outline:", width="stretch",
                         disabled=not (picked and prefix.strip())):
                st.session_state.selection = picked
                _go(f"preview renaming the selected files using the prefix {prefix.strip()}")
            dest = st.selectbox("Copy / move selected to", ["—"] + [d.display() for d in _all_dirs(s)], key="qa_dest")
            b1, b2 = st.columns(2)
            if b1.button("Copy", icon=":material/content_copy:", width="stretch", disabled=not picked or dest == "—"):
                st.session_state.selection = picked
                _go(f"copy the selected files to {dest.rstrip('/')}")
            if b2.button("Move", icon=":material/drive_file_move:", width="stretch", disabled=not picked or dest == "—"):
                st.session_state.selection = picked
                _go(f"move the selected files to {dest.rstrip('/')}")
            if st.button("Delete selected (quarantine)", icon=":material/delete:", width="stretch", disabled=not picked):
                st.session_state.selection = picked
                _go("delete the selected files")
            if st.button("Organize this folder (preview)", icon=":material/auto_fix_high:", width="stretch"):
                _go(f"organize the files in {cur.display().rstrip('/')} by type, but show me the proposed changes first")
            if st.button("Open in File Explorer", icon=":material/open_in_new:", width="stretch"):
                _go(f"open {cur.display().rstrip('/')} folder", "run")

        if len(picked) == 1:
            p = picked[0]
            ext = p.name.rsplit(".", 1)[-1].lower() if "." in p.name else ""
            path = s.perms.resolve(p)
            if ext in PREVIEW_IMG:
                st.image(str(path), caption=p.name)
            elif ext in PREVIEW_TEXT and path.stat().st_size < 200_000:
                st.code(path.read_text(encoding="utf-8", errors="replace")[:3000], language=None)


def _all_dirs(s) -> list[PathRef]:
    from app.core.workspace_index import WorkspaceIndex
    idx = WorkspaceIndex(s.perms)
    return idx.roots + idx.dirs
