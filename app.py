from datetime import date
from typing import Any, Dict, List
import pandas as pd
import streamlit as st

from deadlines import build_digest, normalize, to_ics
from extractor import extract_deadlines, get_demo_deadlines_result
from notifiers import (
    fetch_telegram_updates,
    get_telegram_instructions,
    is_placeholder_or_empty,
    send_email,
    send_telegram,
    send_whatsapp,
    validate_email,
    validate_phone,
)

# --- Page Configuration & Styling ---
st.set_page_config(
    page_title="DeadlineSnap | AI Syllabus & Deadline Extractor",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS styling for a polished, modern, mobile-responsive look
st.markdown(
    """
    <style>
    .main-header {
        font-size: clamp(1.6rem, 4vw, 2.3rem);
        font-weight: 800;
        background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
        line-height: 1.2;
    }
    .sub-caption {
        font-size: clamp(0.9rem, 2vw, 1.05rem);
        color: #64748b;
        margin-bottom: 1.5rem;
    }
    .status-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .status-configured { background-color: #dcfce7; color: #15803d; }
    .status-dryrun { background-color: #fef9c3; color: #a16207; }
    .status-missing { background-color: #fee2e2; color: #b91c1c; }
    .metric-card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 12px 16px;
        text-align: center;
        margin-bottom: 8px;
    }

    /* Mobile Responsive Optimizations */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            padding-top: 1.5rem !important;
        }
        .stButton > button {
            width: 100% !important;
            padding: 0.6rem 1rem !important;
        }
        .metric-card {
            padding: 8px 12px !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Session State Initialization ---
if "onboarded" not in st.session_state:
    st.session_state["onboarded"] = False
if "user_name" not in st.session_state:
    st.session_state["user_name"] = "Student"
if "channel" not in st.session_state:
    st.session_state["channel"] = "Email"
if "contact" not in st.session_state:
    st.session_state["contact"] = ""
if "deadlines" not in st.session_state:
    st.session_state["deadlines"] = []
if "extraction_status" not in st.session_state:
    st.session_state["extraction_status"] = None
if "extraction_reason" not in st.session_state:
    st.session_state["extraction_reason"] = ""
if "demo_mode" not in st.session_state:
    st.session_state["demo_mode"] = False


def check_channel_statuses() -> Dict[str, str]:
    """Check configuration status of external channels."""
    statuses = {}

    # Gemini
    try:
        gkey = st.secrets.get("GEMINI_API_KEY", "")
        statuses["gemini"] = "configured" if not is_placeholder_or_empty(gkey) else "missing"
    except Exception:
        statuses["gemini"] = "missing"

    # Email
    try:
        suser = st.secrets.get("SMTP_USER", "")
        spass = st.secrets.get("SMTP_PASSWORD", "")
        statuses["email"] = "configured" if not is_placeholder_or_empty(suser) and not is_placeholder_or_empty(spass) else "dry-run"
    except Exception:
        statuses["email"] = "dry-run"

    # Telegram
    try:
        ttoken = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        statuses["telegram"] = "configured" if not is_placeholder_or_empty(ttoken) else "dry-run"
    except Exception:
        statuses["telegram"] = "dry-run"

    # WhatsApp
    try:
        tsid = st.secrets.get("TWILIO_ACCOUNT_SID", "")
        tauth = st.secrets.get("TWILIO_AUTH_TOKEN", "")
        statuses["whatsapp"] = "configured" if not is_placeholder_or_empty(tsid) and not is_placeholder_or_empty(tauth) else "dry-run"
    except Exception:
        statuses["whatsapp"] = "dry-run"

    return statuses


# ==============================================================================
# 1. ONBOARDING SCREEN
# ==============================================================================
if not st.session_state["onboarded"]:
    st.markdown('<div class="main-header">📅 Welcome to DeadlineSnap</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-caption">Never miss an assignment, exam, or quiz. Set up your alert profile to get started.</div>',
        unsafe_allow_html=True,
    )

    with st.container():
        col_form, col_info = st.columns([3, 2], gap="large")

        with col_form:
            st.subheader("👤 Step 1: Your Alert Profile")

            input_name = st.text_input("Your Name", value="Alex", placeholder="e.g. Alex Doe")

            input_channel = st.radio(
                "Preferred Notification Channel",
                options=["Email", "Telegram", "WhatsApp"],
                horizontal=True,
                index=0,
            )

            contact_val = ""
            if input_channel == "Email":
                contact_val = st.text_input(
                    "Email Address",
                    placeholder="student@university.edu",
                    help="We'll send your deadline digest to this address.",
                )
            elif input_channel == "Telegram":
                contact_val = st.text_input(
                    "Telegram Chat ID",
                    placeholder="e.g. 123456789",
                    help="Your numeric Telegram chat ID. See guide on the right if you don't know it.",
                )
            elif input_channel == "WhatsApp":
                contact_val = st.text_input(
                    "WhatsApp Phone Number (E.164 with country code)",
                    placeholder="e.g. +14155552671 or +919876543210",
                    help="Include the country code starting with +.",
                )

            st.write("")
            col_btn1, col_btn2 = st.columns([2, 2])

            with col_btn1:
                if st.button("Get Started 🚀", type="primary", use_container_width=True):
                    # Validation
                    valid = True
                    error_msg = ""
                    if not input_name.strip():
                        valid = False
                        error_msg = "Please enter your name."
                    elif input_channel == "Email" and not validate_email(contact_val):
                        valid = False
                        error_msg = "Please enter a valid email address (e.g. name@school.edu)."
                    elif input_channel == "Telegram" and not contact_val.strip():
                        valid = False
                        error_msg = "Please enter a valid Telegram Chat ID."
                    elif input_channel == "WhatsApp" and not validate_phone(contact_val):
                        valid = False
                        error_msg = "Please enter a valid phone number with country code (e.g. +14155552671)."

                    if not valid:
                        st.error(error_msg)
                    else:
                        st.session_state["user_name"] = input_name.strip()
                        st.session_state["channel"] = input_channel
                        st.session_state["contact"] = contact_val.strip()
                        st.session_state["onboarded"] = True
                        st.rerun()

            with col_btn2:
                if st.button("Explore in Demo Mode ✨", use_container_width=True):
                    st.session_state["user_name"] = "Alex (Demo)"
                    st.session_state["channel"] = "Email"
                    st.session_state["contact"] = "demo.student@example.com"
                    st.session_state["demo_mode"] = True
                    st.session_state["onboarded"] = True
                    st.rerun()

        with col_info:
            st.subheader("💡 How DeadlineSnap Works")
            st.info(
                "1. **Snap & Upload**: Take a picture or upload images of your syllabus, course calendar, or timetable.\n\n"
                "2. **AI Extraction**: Gemini Vision reads the document and identifies all exams, quizzes, and deadlines.\n\n"
                "3. **Review & Dispatch**: Edit any date, download a calendar `.ics` file, and send alerts directly to your preferred device."
            )

            if input_channel == "Telegram":
                with st.expander("🤖 How to find your Telegram Chat ID", expanded=True):
                    st.markdown(get_telegram_instructions())
                    if st.button("🔍 Check Recent Bot Messages"):
                        success, updates, msg = fetch_telegram_updates()
                        if success and updates:
                            st.success(msg)
                            for chat in updates:
                                st.code(f"Chat ID: {chat['chat_id']} ({chat.get('first_name', '')} @{chat.get('username', '')})")
                        else:
                            st.warning(msg)

    st.stop()


# ==============================================================================
# 2. MAIN APPLICATION SCREEN
# ==============================================================================

# --- Sidebar ---
with st.sidebar:
    st.markdown("### 📅 **DeadlineSnap**")
    st.caption("AI Syllabus & Deadline Extractor")
    st.divider()

    # Demo Mode Toggle
    demo_toggle = st.checkbox(
        "✨ Demo Mode (Mock extraction)",
        value=st.session_state["demo_mode"],
        help="Test the full workflow using realistic mock data without requiring a Gemini API key.",
    )
    if demo_toggle != st.session_state["demo_mode"]:
        st.session_state["demo_mode"] = demo_toggle
        st.rerun()

    st.divider()

    # User Profile Card
    st.markdown("#### 👤 **User Profile**")
    st.markdown(f"**Name:** {st.session_state['user_name']}")
    st.markdown(f"**Channel:** {st.session_state['channel']}")
    st.markdown(f"**Target:** `{st.session_state['contact']}`")

    if st.button("✏️ Edit Profile", use_container_width=True):
        st.session_state["onboarded"] = False
        st.rerun()

    st.divider()

    # Channel Configuration Status
    st.markdown("#### 🔌 **System & Channel Status**")
    statuses = check_channel_statuses()

    # Gemini API
    if st.session_state["demo_mode"]:
        st.markdown("• **Gemini Vision**: 🟡 `Demo Mode`")
    elif statuses["gemini"] == "configured":
        st.markdown("• **Gemini Vision**: 🟢 `Configured`")
    else:
        st.markdown("• **Gemini Vision**: 🔴 `Missing Key (Switch to Demo Mode)`")

    # Email
    email_badge = "🟢 `Active`" if statuses["email"] == "configured" else "🟡 `Dry-Run Mode`"
    st.markdown(f"• **Email (SMTP)**: {email_badge}")

    # Telegram
    tg_badge = "🟢 `Active`" if statuses["telegram"] == "configured" else "🟡 `Dry-Run Mode`"
    st.markdown(f"• **Telegram**: {tg_badge}")

    # WhatsApp
    wa_badge = "🟢 `Active`" if statuses["whatsapp"] == "configured" else "🟡 `Dry-Run Mode`"
    st.markdown(f"• **WhatsApp**: {wa_badge}")

    st.caption("ℹ️ In Dry-Run mode, alerts are logged to console so you can test without live keys.")


# --- Main Header ---
col_title, col_actions = st.columns([3, 1])
with col_title:
    st.markdown('<div class="main-header">📅 DeadlineSnap</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-caption">Upload your syllabus or assignment sheet. Gemini Vision extracts your deadlines into an editable schedule.</div>',
        unsafe_allow_html=True,
    )

with col_actions:
    if st.session_state["deadlines"]:
        if st.button("🗑️ Clear Deadlines", use_container_width=True):
            st.session_state["deadlines"] = []
            st.session_state["extraction_status"] = None
            st.session_state["extraction_reason"] = ""
            st.rerun()


# --- Input Section (Upload / Camera) ---
st.subheader("📤 1. Upload or Snap Document")
tab_upload, tab_camera = st.tabs(["📁 File Upload (Multi-page)", "📸 Camera Capture"])

uploaded_files = []
camera_file = None

with tab_upload:
    uploaded_files = st.file_uploader(
        "Choose syllabus / timetable images",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        help="Upload one or multiple images of your syllabus or schedule pages.",
    )

with tab_camera:
    camera_file = st.camera_input("Take a photo of your assignment or syllabus sheet")

# Consolidate input images
input_images: List[Any] = []
if uploaded_files:
    input_images.extend(uploaded_files)
if camera_file:
    input_images.append(camera_file)

if input_images:
    with st.expander(f"🖼️ Preview Uploaded Document(s) ({len(input_images)} file(s))", expanded=False):
        cols = st.columns(min(len(input_images), 4))
        for idx, img in enumerate(input_images):
            with cols[idx % len(cols)]:
                st.image(img, caption=f"Page {idx+1}: {img.name if hasattr(img, 'name') else 'Camera Capture'}", use_container_width=True)

# Extraction Action Button
col_extract, col_dummy = st.columns([2, 3])
with col_extract:
    extract_clicked = st.button("⚡ Extract Deadlines", type="primary", use_container_width=True)

if extract_clicked:
    if not input_images and not st.session_state["demo_mode"]:
        st.warning("Please upload at least one image or enable Demo Mode.")
    else:
        with st.spinner("Analyzing document with Gemini Vision..."):
            if st.session_state["demo_mode"]:
                res = get_demo_deadlines_result()
            else:
                image_bytes_list = [img.getvalue() for img in input_images]
                mime_types_list = [img.type if hasattr(img, "type") and img.type else "image/png" for img in input_images]
                res = extract_deadlines(images=image_bytes_list, mime_types=mime_types_list)

            st.session_state["extraction_status"] = res.get("status")
            st.session_state["extraction_reason"] = res.get("reason", "")
            st.session_state["deadlines"] = res.get("deadlines", [])
            st.rerun()


# ==============================================================================
# 3. EXTRACTION RESULTS & EDITABLE TABLE
# ==============================================================================
if st.session_state["extraction_status"]:
    st.divider()
    status = st.session_state["extraction_status"]
    reason = st.session_state["extraction_reason"]
    deadlines = st.session_state["deadlines"]

    if status == "ok":
        st.success(f"🎉 Successfully extracted **{len(deadlines)}** deadline item(s)!")
    elif status == "partial":
        st.warning(f"⚠️ **Partial Extraction:** {reason or 'Some items may be incomplete due to image quality.'}")
    elif status == "no_deadlines_found":
        st.info(
            f"ℹ️ **No Deadlines Detected:** {reason or 'Could not find clear dates or assignments.'}\n\n"
            "**Tips for better results:**\n"
            "- Ensure the document is in focus with good lighting.\n"
            "- Capture the entire table or calendar section.\n"
            "- Check that dates (e.g. 'Oct 15' or '15/10') and task names are visible."
        )


if st.session_state["deadlines"]:
    st.subheader("📋 2. Review & Edit Extracted Deadlines")
    st.caption("You can edit titles, modify dates, change priority/types, or delete rows before sending alerts.")

    # Check for low-confidence items
    low_conf_count = sum(1 for d in st.session_state["deadlines"] if d.get("confidence") == "low" or not d.get("date"))
    if low_conf_count > 0:
        st.warning(f"⚠️ **{low_conf_count} item(s)** have uncertain or unparsed dates. Please review highlighted rows below.")

    # Prepare DataFrame for st.data_editor
    df_deadlines = pd.DataFrame(st.session_state["deadlines"])

    # Ensure required columns exist
    for col in ["title", "course", "date", "time", "type", "confidence", "raw_date_text"]:
        if col not in df_deadlines.columns:
            df_deadlines[col] = None

    edited_df = st.data_editor(
        df_deadlines,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "title": st.column_config.TextColumn("Title / Assignment", required=True, width="large"),
            "course": st.column_config.TextColumn("Course", width="medium"),
            "date": st.column_config.TextColumn("Due Date (YYYY-MM-DD)", width="medium"),
            "time": st.column_config.TextColumn("Time", width="small"),
            "type": st.column_config.SelectboxColumn(
                "Type",
                options=["assignment", "exam", "project", "quiz", "class", "other"],
                required=True,
                width="small",
            ),
            "confidence": st.column_config.SelectboxColumn(
                "Confidence",
                options=["high", "medium", "low"],
                required=True,
                width="small",
            ),
            "raw_date_text": st.column_config.TextColumn("Original Text", disabled=True, width="medium"),
        },
        key="deadlines_editor",
    )

    # Sync back edited DataFrame
    current_deadlines = edited_df.to_dict(orient="records")
    st.session_state["deadlines"] = current_deadlines

    # Quick metrics
    dated_items, unreviewed = normalize(current_deadlines)
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("Total Deadlines", len(current_deadlines))
    with col_m2:
        st.metric("Confirmed Dates", len(dated_items))
    with col_m3:
        st.metric("Needs Manual Review", len(unreviewed))


    # ==============================================================================
    # 4. DIGEST PREVIEW & NOTIFICATION DISPATCH
    # ==============================================================================
    st.divider()
    st.subheader("📬 3. Digest Preview & Alert Dispatch")

    digest_text = build_digest(
        name=st.session_state["user_name"],
        deadlines=current_deadlines,
        today=date.today(),
        max_chars=1500,
    )

    col_preview, col_send = st.columns([3, 2], gap="large")

    with col_preview:
        st.markdown("**Message Digest Preview**")
        st.text_area(
            "Plain-text message to be sent:",
            value=digest_text,
            height=260,
            help="Formatted to be compatible with WhatsApp, Telegram, and Email limits.",
            disabled=True,
        )
        char_count = len(digest_text)
        st.caption(f"📊 Length: **{char_count}** / 1500 characters")

    with col_send:
        st.markdown(f"**Send via {st.session_state['channel']}**")
        st.write(f"Recipient: **{st.session_state['user_name']}** (`{st.session_state['contact']}`)")

        # Send Action Button
        btn_label = f"🚀 Send Digest to {st.session_state['channel']}"
        if st.button(btn_label, type="primary", use_container_width=True):
            channel = st.session_state["channel"]
            contact = st.session_state["contact"]
            name = st.session_state["user_name"]

            with st.spinner(f"Sending digest via {channel}..."):
                if channel == "Email":
                    success, msg = send_email(
                        to_email=contact,
                        name=name,
                        subject=f"📅 Your DeadlineSnap Digest ({len(current_deadlines)} deadlines)",
                        body=digest_text,
                    )
                elif channel == "Telegram":
                    success, msg = send_telegram(
                        chat_id=contact,
                        text=digest_text,
                    )
                elif channel == "WhatsApp":
                    success, msg = send_whatsapp(
                        to_number=contact,
                        name=name,
                        summary=digest_text,
                    )
                else:
                    success, msg = False, "Unknown channel selected."

                if success:
                    st.success(f"✅ {msg}")
                    st.balloons()
                else:
                    st.error(f"❌ {msg}")

        st.write("")
        st.markdown("**Calendar Export**")
        ics_data = to_ics(current_deadlines)
        st.download_button(
            label="📅 Download .ics Calendar File",
            data=ics_data,
            file_name="deadlinesnap_schedule.ics",
            mime="text/calendar",
            use_container_width=True,
        )
        st.caption("Import `.ics` into Apple Calendar, Google Calendar, or Outlook.")
