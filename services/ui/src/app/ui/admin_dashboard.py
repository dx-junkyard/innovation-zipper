"""
Admin Dashboard for Wikipedia Import and Knowledge Management

Provides UI for:
- Uploading and importing Wikipedia dumps
- Monitoring import job progress
- Real-time error notifications
- Knowledge base statistics
"""

import streamlit as st
import requests
import os
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any

# Admin API URL
ADMIN_API_URL = os.environ.get("ADMIN_API_URL", "http://admin-api:8000/api/v1/admin")


def get_admin_api_url(endpoint: str) -> str:
    """Get full admin API URL."""
    base = ADMIN_API_URL.rstrip('/')
    return f"{base}/{endpoint.lstrip('/')}"


def format_file_size(size_bytes: int) -> str:
    """Format file size to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def format_datetime(iso_str: Optional[str]) -> str:
    """Format ISO datetime string to readable format."""
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso_str


def get_status_color(status: str) -> str:
    """Get color for job status."""
    colors = {
        "pending": "gray",
        "running": "blue",
        "completed": "green",
        "failed": "red",
        "cancelled": "orange",
        "cancelling": "yellow"
    }
    return colors.get(status, "gray")


def render_job_card(job: Dict[str, Any]):
    """Render a single job status card."""
    status = job.get("status", "unknown")
    progress = job.get("progress", {})

    # Status indicator
    status_emoji = {
        "pending": "⏳",
        "running": "🔄",
        "completed": "✅",
        "failed": "❌",
        "cancelled": "🚫",
        "cancelling": "⚠️"
    }.get(status, "❓")

    col1, col2, col3 = st.columns([3, 2, 1])

    with col1:
        st.markdown(f"### {status_emoji} Job: `{job.get('job_id', 'N/A')[:8]}...`")
        st.caption(f"File: {os.path.basename(job.get('file_path', 'Unknown'))}")

    with col2:
        st.metric("Status", status.upper())
        if progress.get("percent_complete") is not None and status == "running":
            st.progress(progress["percent_complete"] / 100)

    with col3:
        if status == "running":
            if st.button("Cancel", key=f"cancel_{job['job_id']}"):
                try:
                    resp = requests.post(
                        get_admin_api_url(f"wikipedia/jobs/{job['job_id']}/cancel")
                    )
                    if resp.status_code == 200:
                        st.success("Cancellation requested")
                        st.rerun()
                    else:
                        st.error("Failed to cancel")
                except Exception as e:
                    st.error(f"Error: {e}")

    # Progress details
    if progress:
        cols = st.columns(4)
        cols[0].metric("Parsed", f"{progress.get('total_parsed', 0):,}")
        cols[1].metric("Imported", f"{progress.get('total_imported', 0):,}")
        cols[2].metric("Errors", progress.get('total_errors', 0))
        cols[3].metric("Batch", progress.get('current_batch', 0))

    # Message
    if job.get("message"):
        st.info(job["message"])

    # Timestamps
    st.caption(
        f"Created: {format_datetime(job.get('created_at'))} | "
        f"Started: {format_datetime(job.get('started_at'))} | "
        f"Completed: {format_datetime(job.get('completed_at'))}"
    )

    # Errors (collapsible)
    errors = job.get("errors", [])
    if errors:
        with st.expander(f"⚠️ Errors ({len(errors)})"):
            for err in errors[-10:]:  # Show last 10
                if isinstance(err, dict):
                    st.error(f"[{err.get('timestamp', '')}] {err.get('message', '')}")
                else:
                    st.error(err)


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}min"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def estimate_total_articles(file_size_bytes: int) -> int:
    """
    Estimate total articles based on file size.
    Japanese Wikipedia (~5GB bz2) has approximately 1.4 million articles.
    """
    # Rough estimate: ~3.5KB per article in compressed form
    return int(file_size_bytes / 3500)


def render_active_job_progress(job_id: str):
    """Render real-time progress for an active job."""
    st.markdown("---")
    st.subheader("📊 Import Progress")

    progress_container = st.container()

    # Create placeholders for dynamic updates
    with progress_container:
        try:
            resp = requests.get(
                get_admin_api_url(f"wikipedia/jobs/{job_id}"),
                timeout=10
            )

            if resp.status_code != 200:
                st.error("Failed to fetch job status")
                return

            job = resp.json().get("job", {})
            status = job.get("status", "unknown")
            progress = job.get("progress", {})
            config = job.get("config", {})

            # Status display
            status_emoji = {
                "pending": "⏳",
                "running": "🔄",
                "completed": "✅",
                "failed": "❌",
                "cancelled": "🚫",
                "cancelling": "⚠️"
            }.get(status, "❓")

            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"### {status_emoji} Status: **{status.upper()}**")
            with col2:
                if status == "running":
                    if st.button("🛑 Cancel Job", type="secondary"):
                        try:
                            cancel_resp = requests.post(
                                get_admin_api_url(f"wikipedia/jobs/{job_id}/cancel")
                            )
                            if cancel_resp.status_code == 200:
                                st.success("Cancellation requested")
                                time.sleep(1)
                                st.rerun()
                        except Exception as e:
                            st.error(f"Cancel failed: {e}")

            # Progress metrics
            total_parsed = progress.get("total_parsed", 0)
            total_imported = progress.get("total_imported", 0)
            total_errors = progress.get("total_errors", 0)
            current_batch = progress.get("current_batch", 0)

            # Estimate total (from config or file size estimation)
            max_articles = config.get("max_articles")
            if max_articles:
                estimated_total = max_articles
            else:
                # For Japanese Wikipedia, estimate ~1.4M articles
                estimated_total = 1400000

            # Calculate progress percentage
            if estimated_total > 0:
                percent_complete = min(100, (total_parsed / estimated_total) * 100)
            else:
                percent_complete = 0

            # Progress bar
            st.progress(percent_complete / 100)

            # Progress details in columns
            cols = st.columns(5)
            cols[0].metric("Parsed", f"{total_parsed:,}")
            cols[1].metric("Imported", f"{total_imported:,}")
            cols[2].metric("Errors", total_errors)
            cols[3].metric("Batch", current_batch)
            cols[4].metric("Progress", f"{percent_complete:.1f}%")

            # Estimated time calculation
            started_at = job.get("started_at")
            if started_at and total_parsed > 0 and status == "running":
                try:
                    start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                    elapsed = (datetime.now(start_time.tzinfo) - start_time).total_seconds()

                    articles_per_second = total_parsed / elapsed if elapsed > 0 else 0
                    remaining_articles = estimated_total - total_parsed

                    if articles_per_second > 0:
                        eta_seconds = remaining_articles / articles_per_second

                        st.info(
                            f"⏱️ Speed: **{articles_per_second:.1f}** articles/sec | "
                            f"Elapsed: **{format_duration(elapsed)}** | "
                            f"ETA: **{format_duration(eta_seconds)}**"
                        )
                except Exception:
                    pass

            # Message
            if job.get("message"):
                st.caption(f"💬 {job['message']}")

            # Errors preview
            errors = job.get("errors", [])
            if errors:
                with st.expander(f"⚠️ Recent Errors ({len(errors)})", expanded=False):
                    for err in errors[-5:]:
                        if isinstance(err, dict):
                            st.error(f"{err.get('message', '')}")
                        else:
                            st.error(err)

            # Auto-refresh for running jobs
            if status == "running":
                st.caption("🔄 Auto-refreshing every 3 seconds...")
                time.sleep(3)
                st.rerun()
            elif status in ["completed", "failed", "cancelled"]:
                st.success("Job finished. You can start a new import above.")
                if st.button("Clear and Start New Import"):
                    del st.session_state["active_job_id"]
                    st.rerun()

        except Exception as e:
            st.error(f"Error fetching job status: {e}")


def render_upload_section():
    """Render file upload section."""
    st.subheader("📤 Upload Wikipedia Dump")

    st.markdown("""
    Upload a Wikipedia dump file (`.xml.bz2` format).
    Japanese Wikipedia dumps can be downloaded from:
    [Wikipedia Database Downloads](https://dumps.wikimedia.org/jawiki/)
    """)

    uploaded_file = st.file_uploader(
        "Select Wikipedia dump file",
        type=["bz2", "xml"],
        help="Supported formats: .xml.bz2, .xml"
    )

    if uploaded_file:
        st.info(f"📁 Selected: {uploaded_file.name} ({format_file_size(uploaded_file.size)})")

        if st.button("Upload File", type="primary"):
            with st.spinner("Uploading... This may take a while for large files."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file, "application/octet-stream")}
                    resp = requests.post(
                        get_admin_api_url("wikipedia/upload"),
                        files=files,
                        timeout=3600  # 1 hour timeout for large files
                    )

                    if resp.status_code == 200:
                        result = resp.json()
                        st.success(f"✅ Upload successful!")
                        st.session_state["uploaded_file_path"] = result["file_path"]
                        st.json(result)
                    else:
                        st.error(f"Upload failed: {resp.text}")

                except requests.exceptions.Timeout:
                    st.error("Upload timed out. The file may be too large.")
                except Exception as e:
                    st.error(f"Upload error: {e}")


def render_import_section():
    """Render import configuration and start section."""
    # Check if there's an active job
    active_job_id = st.session_state.get("active_job_id")

    if active_job_id:
        # Show progress for active job
        render_active_job_progress(active_job_id)
        return

    st.subheader("🚀 Start Import Job")

    # File path input
    file_path = st.text_input(
        "File Path",
        value=st.session_state.get("uploaded_file_path", ""),
        placeholder="/data/wikipedia_dumps/jawiki-20260101-pages-articles.xml.bz2"
    )

    # Show estimated articles if file exists
    if file_path:
        try:
            import os
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                estimated = estimate_total_articles(file_size)
                st.info(
                    f"📁 File size: **{format_file_size(file_size)}** | "
                    f"Estimated articles: **~{estimated:,}**"
                )
        except Exception:
            pass

    # Import configuration
    col1, col2 = st.columns(2)

    with col1:
        batch_size = st.number_input(
            "Batch Size",
            min_value=10,
            max_value=1000,
            value=100,
            help="Number of articles per batch"
        )
        min_content_length = st.number_input(
            "Min Content Length",
            min_value=50,
            max_value=1000,
            value=100,
            help="Minimum article content length to import"
        )

    with col2:
        max_articles = st.number_input(
            "Max Articles (0 = unlimited)",
            min_value=0,
            max_value=10000000,
            value=0,
            help="Maximum number of articles to import (0 for all)"
        )

    # Estimate time
    if file_path and max_articles == 0:
        st.warning(
            "⚠️ Importing all articles from a full Wikipedia dump can take **several hours**. "
            "Consider setting a Max Articles limit for testing."
        )

    # Start button
    if st.button("Start Import", type="primary", disabled=not file_path):
        with st.spinner("Starting import job..."):
            try:
                payload = {
                    "file_path": file_path,
                    "batch_size": batch_size,
                    "min_content_length": min_content_length,
                    "max_articles": max_articles if max_articles > 0 else None
                }

                resp = requests.post(
                    get_admin_api_url("wikipedia/import"),
                    json=payload
                )

                if resp.status_code == 200:
                    result = resp.json()
                    st.success(f"✅ Import job started! Job ID: {result['job_id']}")
                    st.session_state["active_job_id"] = result["job_id"]
                    time.sleep(1)  # Small delay to let job start
                    st.rerun()
                else:
                    st.error(f"Failed to start import: {resp.text}")

            except Exception as e:
                st.error(f"Error: {e}")


def render_jobs_section():
    """Render job list and monitoring section."""
    st.subheader("📊 Import Jobs")

    # Refresh button
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 Refresh"):
            st.rerun()

    # Auto-refresh toggle
    with col2:
        auto_refresh = st.checkbox(
            "Auto-refresh (every 5s)",
            value=st.session_state.get("auto_refresh", False)
        )
        st.session_state["auto_refresh"] = auto_refresh

    # Fetch jobs
    try:
        resp = requests.get(get_admin_api_url("wikipedia/jobs"), params={"limit": 20})
        if resp.status_code == 200:
            jobs = resp.json().get("jobs", [])

            if not jobs:
                st.info("No import jobs found.")
            else:
                for job in jobs:
                    with st.container():
                        render_job_card(job)
                        st.divider()

        else:
            st.error(f"Failed to fetch jobs: {resp.text}")

    except Exception as e:
        st.error(f"Error fetching jobs: {e}")

    # Auto-refresh implementation
    if auto_refresh:
        time.sleep(5)
        st.rerun()


def render_embeddings_section():
    """Render embeddings processing section."""
    st.subheader("🧠 Process Embeddings")

    st.markdown("""
    After importing raw articles, process them to generate embeddings for RAG search.
    This runs in the background and can take a long time for large datasets.
    """)

    col1, col2 = st.columns(2)

    with col1:
        embed_batch_size = st.number_input(
            "Batch Size",
            min_value=10,
            max_value=200,
            value=50,
            help="Number of items per embedding batch"
        )

    with col2:
        max_batches = st.number_input(
            "Max Batches (0 = unlimited)",
            min_value=0,
            max_value=10000,
            value=0,
            help="Maximum batches to process (0 for all pending)"
        )

    if st.button("Start Embedding Processing", type="secondary"):
        with st.spinner("Starting embedding processing..."):
            try:
                payload = {
                    "batch_size": embed_batch_size,
                    "max_batches": max_batches if max_batches > 0 else None
                }

                resp = requests.post(
                    get_admin_api_url("wikipedia/process-embeddings"),
                    json=payload
                )

                if resp.status_code == 200:
                    result = resp.json()
                    st.success(f"✅ Embedding task started! Task ID: {result['task_id']}")
                else:
                    st.error(f"Failed: {resp.text}")

            except Exception as e:
                st.error(f"Error: {e}")


def render_stats_section():
    """Render knowledge base statistics."""
    st.subheader("📈 Knowledge Base Statistics")

    try:
        resp = requests.get(get_admin_api_url("stats"))
        if resp.status_code == 200:
            stats = resp.json().get("stats", {})

            kb_stats = stats.get("knowledge_base", {})
            col1, col2, col3 = st.columns(3)

            col1.metric("Collection", kb_stats.get("collection", "N/A"))
            col2.metric("Total Points", f"{kb_stats.get('points_count', 0):,}")
            col3.metric("Total Vectors", f"{kb_stats.get('vectors_count', 0):,}")

            st.metric("Recent Jobs", stats.get("recent_jobs", 0))

        else:
            st.warning("Could not fetch statistics")

    except Exception as e:
        st.warning(f"Stats unavailable: {e}")


def fetch_notifications() -> list:
    """Fetch notifications from admin API."""
    try:
        resp = requests.get(
            get_admin_api_url("notifications"),
            params={"limit": 20},
            timeout=5
        )
        if resp.status_code == 200:
            return resp.json().get("notifications", [])
    except Exception as e:
        st.sidebar.warning(f"Could not fetch notifications: {e}")
    return []


def clear_notifications_api():
    """Clear notifications via API."""
    try:
        resp = requests.delete(get_admin_api_url("notifications"), timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def render_notifications_panel():
    """Render real-time notifications panel in sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔔 Notifications")

    # Fetch notifications from API
    notifications = fetch_notifications()

    if not notifications:
        st.sidebar.info("No notifications")
    else:
        # Show notification count
        error_count = sum(1 for n in notifications if n.get("type") == "error")
        if error_count > 0:
            st.sidebar.error(f"⚠️ {error_count} error(s)")

        # Show last 5 notifications
        for notif in notifications[:5]:
            notif_type = notif.get("type", "info")
            message = notif.get("message", "")
            job_id = notif.get("job_id", "")[:8]
            timestamp = format_datetime(notif.get("timestamp"))

            # Create notification card
            if notif_type == "error" or notif_type == "failed":
                st.sidebar.error(f"❌ [{job_id}] {message}")
            elif notif_type == "completed":
                st.sidebar.success(f"✅ [{job_id}] {message}")
            elif notif_type == "cancelled":
                st.sidebar.warning(f"🚫 [{job_id}] {message}")
            else:
                st.sidebar.info(f"ℹ️ [{job_id}] {message}")

            st.sidebar.caption(timestamp)

    # Clear notifications button
    if notifications and st.sidebar.button("Clear All Notifications"):
        if clear_notifications_api():
            st.sidebar.success("Notifications cleared!")
            st.rerun()
        else:
            st.sidebar.error("Failed to clear notifications")


def show_admin_dashboard():
    """Main admin dashboard entry point."""
    st.header("🔧 Admin Dashboard")

    # Check authentication (simple check - can be enhanced)
    if "user_id" not in st.session_state:
        st.warning("Please log in to access admin features.")
        return

    # Render notifications panel
    render_notifications_panel()

    # Create tabs for different sections
    tab1, tab2, tab3, tab4 = st.tabs([
        "📤 Upload & Import",
        "📊 Job Monitor",
        "🧠 Embeddings",
        "📈 Statistics"
    ])

    with tab1:
        render_upload_section()
        st.divider()
        render_import_section()

    with tab2:
        render_jobs_section()

    with tab3:
        render_embeddings_section()

    with tab4:
        render_stats_section()


if __name__ == "__main__":
    st.set_page_config(
        page_title="Admin Dashboard",
        page_icon="🔧",
        layout="wide"
    )
    show_admin_dashboard()
