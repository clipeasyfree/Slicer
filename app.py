import streamlit as st
import re
import os
import zipfile
import subprocess

st.set_page_config(page_title="CapCut Clip Slicer", page_icon="⚡", layout="centered")

# Custom Dark Theme Styling
st.markdown("""
<style>
    .stApp { background-color: #0b0f19; color: #f8fafc; }
    .stTextInput > div > div > input { background-color: #111827; color: #38bdf8; border: 1px solid #374151; border-radius: 10px; }
    .stTextArea > div > div > textarea { background-color: #111827; color: #e2e8f0; font-family: monospace; border: 1px solid #374151; border-radius: 10px; }
    .stButton > button { background: linear-gradient(90deg, #10b981, #06b6d4); color: #000; font-weight: 800; border-radius: 12px; border: none; padding: 12px; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ CapCut Clip Slicer")
st.caption("Auto Timestamp Parser &bull; Ultra-Fast Slicing &bull; 1080p CapCut Ready (H.264/AAC)")

# 1. Video URL Input
video_url = st.text_input("1. Paste YouTube Video Link", placeholder="https://www.youtube.com/watch?v=...")

# 2. Raw Hooks & Timestamps Input
st.write("---")
col_title, col_sample = st.columns([3, 1])
with col_title:
    st.write("**2. Paste Ranked Clip Ideas**")
with col_sample:
    if st.button("Load Sample"):
        st.session_state["raw_clips"] = """1
02:20–04:10
💰 TJR spent $500K in one month
2
05:40–07:45
🧠 What emotions destroy traders
3
22:05–25:50
💵 How much you actually need to make $10K/day
4
25:50–27:35
🎓 Why you don't necessarily need to buy a course
5
30:10–32:35
🚨 Why prop firms can ban traders
6
36:10–37:30
💰 TJR's biggest single trade
7
40:15–42:50
🧨 “The biggest pyramid scheme…”
8
45:00–47:40
🏎️ Buying a Koenigsegg
9
01:04:00–01:08:50
🎓 Why TJR dropped out of college
10
01:08:50–01:11:35
🖤 TJR discusses his darkest period"""

default_text = st.session_state.get("raw_clips", "")
raw_input = st.text_area("Ranked clips text", value=default_text, height=160, label_visibility="collapsed")

# Auto-format helper: converts 1500 -> 15:00, 010400 -> 01:04:00
def format_time_str(val: str) -> str:
    digits = re.sub(r'[^0-9]', '', str(val))
    if not digits:
        return "00:00"
    if len(digits) <= 2:
        return f"00:{digits.zfill(2)}"
    elif len(digits) <= 4:
        return f"{digits[:-2].zfill(2)}:{digits[-2:]}"
    else:
        return f"{digits[:-4].zfill(2)}:{digits[-4:-2]}:{digits[-2:]}"

def clean_filename(text: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_\- ]', '', text).strip().replace(' ', '_')

# Parse clips from pasted text
parsed_clips = []
if raw_input.strip():
    lines = [l.strip() for l in raw_input.split('\n') if l.strip()]
    for i, line in enumerate(lines):
        time_match = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)\s*[–\-]\s*(\d{1,2}:\d{2}(?::\d{2})?)', line)
        if time_match:
            rank = len(parsed_clips) + 1
            if i > 0 and lines[i-1].isdigit():
                rank = int(lines[i-1])
            
            title = f"Clip {rank}"
            if i + 1 < len(lines) and not lines[i+1].isdigit() and '–' not in lines[i+1] and '-' not in lines[i+1]:
                title = lines[i+1]

            parsed_clips.append({
                "rank": rank,
                "title": title,
                "start": format_time_str(time_match.group(1)),
                "end": format_time_str(time_match.group(2))
            })

# 3. Clip Selection & Batch Controls
if parsed_clips:
    st.write("---")
    st.write("### 3. Choose How Many Clips to Download")
    
    total = len(parsed_clips)
    batch_mode = st.radio("Selection count", ["Top 3", "Top 5", "Top 10", "All Clips"], horizontal=True, label_visibility="collapsed")
    
    count_map = {"Top 3": 3, "Top 5": 5, "Top 10": 10, "All Clips": total}
    selected_count = min(count_map[batch_mode], total)
    
    st.info(f"Selected: **{selected_count} of {total} clips**")
    
    # Render editable cards
    selected_clips = []
    for idx, c in enumerate(parsed_clips[:selected_count]):
        with st.container():
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                clip_title = st.text_input(f"#{c['rank']} Hook", value=c['title'], key=f"title_{idx}")
            with c2:
                # typing 1500 automatically formats to 15:00 on change
                start_val = st.text_input(f"Start", value=c['start'], key=f"start_{idx}")
                start_fmt = format_time_str(start_val)
            with c3:
                end_val = st.text_input(f"End", value=c['end'], key=f"end_{idx}")
                end_fmt = format_time_str(end_val)
            
            selected_clips.append({
                "rank": c["rank"],
                "title": clip_title,
                "start": start_fmt,
                "end": end_fmt
            })

    st.write("---")
    if st.button("🚀 Srv / Cut & Download Selected Clips for CapCut"):
        if not video_url:
            st.error("Please enter a YouTube video URL first!")
        else:
            status_text = st.empty()
            progress_bar = st.progress(0)
            out_dir = "/tmp/capcut_clips"
            os.makedirs(out_dir, exist_ok=True)
            
            # Clean previous clips
            for f in os.listdir(out_dir):
                try: os.remove(os.path.join(out_dir, f))
                except: pass

            downloaded_files = []
            for i, clip in enumerate(selected_clips):
                status_text.write(f"⚡ Downloading & slicing section **#{clip['rank']}**: {clip['title']} ({clip['start']} &rarr; {clip['end']})...")
                safe_name = clean_filename(clip['title'])
                file_path = os.path.join(out_dir, f"{clip['rank']:02d}_{safe_name}.mp4")

                # Ultra-fast yt-dlp section download directly in CapCut-supported H.264/AAC
                cmd = [
                    "yt-dlp",
                    "--extractor-args", "youtube:player_client=android,web",
                    "--download-sections", f"*{clip['start']}-{clip['end']}",
                    "--force-keyframes-at-cuts",
                    "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
                    "--postprocessor-args", "ffmpeg:-c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart",
                    "-o", file_path,
                    video_url
                ]
                subprocess.run(cmd, capture_output=True, text=True)
                
                if os.path.exists(file_path):
                    downloaded_files.append(file_path)
                progress_bar.progress((i + 1) / len(selected_clips))

            if downloaded_files:
                zip_path = "/tmp/CapCut_Clips.zip"
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for f in downloaded_files:
                        zipf.write(f, arcname=os.path.basename(f))
                
                status_text.success("✅ Clips cut and optimized successfully for CapCut!")
                with open(zip_path, "rb") as zf:
                    st.download_button(
                        label="📥 Download All Clips (.zip)",
                        data=zf,
                        file_name="CapCut_Clips.zip",
                        mime="application/zip"
                    )
            else:
                st.error("Failed to download sections. Please check the video link.")

