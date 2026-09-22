import os
import re
import zipfile
import subprocess
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List

app = FastAPI()

class ClipItem(BaseModel):
    rank: int
    title: str
    start: str
    end: str

class DownloadRequest(BaseModel):
    url: str
    clips: List[ClipItem]

def clean_filename(text: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_\- ]', '', text).strip().replace(' ', '_')

@app.get("/", response_class=HTMLResponse)
def index():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>CapCut Clip Slicer</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Plus Jakarta Sans', sans-serif; background: #080c14; color: #f8fafc; }
  </style>
</head>
<body class="min-h-screen p-4 flex flex-col items-center">
  <div class="w-full max-w-lg space-y-5 pb-12">
    
    <!-- Header -->
    <div class="flex items-center justify-between border-b border-slate-800 pb-4 pt-2">
      <div>
        <h1 class="text-2xl font-extrabold text-white flex items-center gap-2">
          ⚡ <span>CapCut Slicer</span>
        </h1>
        <p class="text-xs text-slate-400 mt-0.5">High-Speed Section Downloader (H.264/AAC)</p>
      </div>
      <span class="bg-emerald-500/10 text-emerald-400 text-[11px] font-semibold px-2.5 py-1 rounded-full border border-emerald-500/20">
        Ready
      </span>
    </div>

    <!-- Step 1: Video Link -->
    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg space-y-2">
      <label class="block text-xs font-bold uppercase tracking-wider text-slate-400">1. YouTube Link</label>
      <input type="text" id="videoUrl" placeholder="Paste YouTube link here..." 
        class="w-full bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-3 text-sm focus:outline-none focus:border-cyan-500 text-white placeholder-slate-500">
    </div>

    <!-- Step 2: Ranked List -->
    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg space-y-2.5">
      <div class="flex items-center justify-between">
        <label class="block text-xs font-bold uppercase tracking-wider text-slate-400">2. Paste Ranked Clip Ideas</label>
        <button onclick="loadSample()" class="text-xs text-cyan-400 font-bold active:scale-95 transition">Load Sample</button>
      </div>
      <textarea id="rawInput" rows="5" placeholder="1&#10;02:20–04:10&#10;💰 TJR spent $500K&#10;2&#10;05:40–07:45&#10;🧠 What emotions destroy traders"
        class="w-full bg-slate-950 border border-slate-700 rounded-xl p-3 text-xs font-mono text-slate-300 focus:outline-none focus:border-cyan-500"></textarea>
      
      <button onclick="parseClips()" class="w-full py-3 bg-slate-800 hover:bg-slate-700 active:scale-[0.98] text-cyan-300 font-bold text-sm rounded-xl transition border border-slate-700">
        ✨ Parse Timestamps & Hooks
      </button>
    </div>

    <!-- Step 3: Selection & Controls -->
    <div id="clipsSection" class="hidden bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg space-y-4">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <div>
          <h2 class="text-sm font-bold text-white">Select Clips</h2>
          <p id="selectionStats" class="text-[11px] text-slate-400">0 clips selected</p>
        </div>
        
        <!-- Batch Buttons -->
        <div class="flex items-center gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800">
          <button onclick="selectTop(3)" class="px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-800 text-slate-200">Top 3</button>
          <button onclick="selectTop(5)" class="px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-800 text-slate-200">Top 5</button>
          <button onclick="selectAll(true)" class="px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-800 text-cyan-400">All</button>
        </div>
      </div>

      <!-- Clips List -->
      <div id="clipList" class="space-y-2.5 max-h-[360px] overflow-y-auto pr-0.5"></div>

      <!-- Download Button -->
      <button id="downloadBtn" onclick="startDownload()" class="w-full py-3.5 bg-gradient-to-r from-emerald-500 to-teal-500 active:scale-[0.98] text-black font-extrabold text-sm rounded-xl transition shadow-lg shadow-emerald-500/20 flex items-center justify-center gap-2">
        📥 <span>Download Selected (.zip)</span>
      </button>

      <!-- Status Logs -->
      <div id="statusBox" class="hidden bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs font-mono text-cyan-300">
        <div id="statusText">Processing clips...</div>
      </div>
    </div>

  </div>

  <script>
    let clips = [];

    // Auto Timestamp Masking: Converts 1500 -> 15:00, 010400 -> 01:04:00
    function formatTimeInput(value) {
      let raw = value.replace(/[^0-9]/g, '');
      if (raw.length === 0) return '00:00';
      if (raw.length <= 2) return '00:' + raw.padStart(2, '0');
      if (raw.length <= 4) {
        let m = raw.slice(0, -2).padStart(2, '0');
        let s = raw.slice(-2);
        return m + ':' + s;
      }
      let s = raw.slice(-2);
      let m = raw.slice(-4, -2);
      let h = raw.slice(0, -4).padStart(2, '0');
      return h + ':' + m + ':' + s;
    }

    function handleTimeMask(el, index, field) {
      el.addEventListener('blur', () => {
        el.value = formatTimeInput(el.value);
        clips[index][field] = el.value;
      });
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') el.blur();
      });
    }

    function parseClips() {
      const text = document.getElementById('rawInput').value.trim();
      if (!text) return;

      const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
      clips = [];

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const timeMatch = line.match(/(\\d{1,2}:\\d{2}(?::\\d{2})?)\\s*[–\\-]\\s*(\\d{1,2}:\\d{2}(?::\\d{2})?)/);
        
        if (timeMatch) {
          let rank = clips.length + 1;
          if (i > 0 && /^\\d+$/.test(lines[i - 1])) {
            rank = parseInt(lines[i - 1]);
          }
          let title = (i + 1 < lines.length && !lines[i + 1].match(/^[0-9]+$/) && !lines[i + 1].includes('–')) 
                      ? lines[i + 1] 
                      : `Clip ${rank}`;

          clips.push({
            rank: rank,
            start: formatTimeInput(timeMatch[1]),
            end: formatTimeInput(timeMatch[2]),
            title: title,
            selected: true
          });
        }
      }

      renderClips();
    }

    function renderClips() {
      const container = document.getElementById('clipList');
      container.innerHTML = '';

      if (clips.length === 0) {
        alert('Could not find timestamps. Ensure format like: 02:20–04:10');
        return;
      }

      document.getElementById('clipsSection').classList.remove('hidden');

      clips.forEach((clip, idx) => {
        const row = document.createElement('div');
        row.className = `p-3 rounded-xl border flex flex-col gap-2 transition ${
          clip.selected ? 'bg-slate-950 border-cyan-500/40' : 'bg-slate-950/40 border-slate-800 opacity-60'
        }`;

        row.innerHTML = `
          <div class="flex items-center gap-2">
            <input type="checkbox" ${clip.selected ? 'checked' : ''} onchange="toggleSelect(${idx})" 
              class="w-4 h-4 rounded text-cyan-500 focus:ring-0">
            <span class="text-[10px] font-extrabold bg-slate-800 text-cyan-300 w-5 h-5 flex items-center justify-center rounded">#${clip.rank}</span>
            <input type="text" value="${clip.title}" onchange="clips[${idx}].title = this.value"
              class="bg-transparent text-xs font-semibold text-white focus:outline-none focus:border-b border-cyan-500 flex-1 truncate">
          </div>
          
          <div class="flex items-center justify-end gap-2">
            <div class="flex items-center bg-slate-900 border border-slate-800 rounded-lg px-2 py-1">
              <input type="text" id="start_${idx}" value="${clip.start}" 
                class="w-14 bg-transparent text-[11px] text-center font-mono font-bold text-cyan-400 focus:outline-none">
              <span class="text-[11px] text-slate-500 px-1">→</span>
              <input type="text" id="end_${idx}" value="${clip.end}" 
                class="w-14 bg-transparent text-[11px] text-center font-mono font-bold text-cyan-400 focus:outline-none">
            </div>
          </div>
        `;

        container.appendChild(row);
        handleTimeMask(document.getElementById(`start_${idx}`), idx, 'start');
        handleTimeMask(document.getElementById(`end_${idx}`), idx, 'end');
      });

      updateStats();
    }

    function toggleSelect(index) {
      clips[index].selected = !clips[index].selected;
      renderClips();
    }

    function selectTop(n) {
      clips.forEach((c, i) => c.selected = (i < n));
      renderClips();
    }

    function selectAll(state) {
      clips.forEach(c => c.selected = state);
      renderClips();
    }

    function updateStats() {
      const selCount = clips.filter(c => c.selected).length;
      document.getElementById('selectionStats').innerText = `${selCount} of ${clips.length} selected`;
    }

    async function startDownload() {
      const url = document.getElementById('videoUrl').value.trim();
      if (!url) {
        alert('Please enter a YouTube video URL first!');
        return;
      }

      const selected = clips.filter(c => c.selected);
      if (selected.length === 0) {
        alert('Please select at least 1 clip.');
        return;
      }

      const btn = document.getElementById('downloadBtn');
      const statusBox = document.getElementById('statusBox');
      const statusText = document.getElementById('statusText');

      btn.disabled = true;
      btn.classList.add('opacity-50');
      statusBox.classList.remove('hidden');
      statusText.innerHTML = '⚡ Server is downloading and slicing sections directly... Please wait...';

      try {
        const response = await fetch('/api/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: url, clips: selected })
        });

        if (!response.ok) {
          const err = await response.json();
          throw new Error(err.detail || 'Download failed');
        }

        statusText.innerHTML = '✅ Finished! Downloading your zip...';

        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = "CapCut_Clips.zip";
        document.body.appendChild(a);
        a.click();
        a.remove();

      } catch (err) {
        alert('Error: ' + err.message);
        statusText.innerHTML = '❌ Error occurred during download.';
      } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-50');
      }
    }

    function loadSample() {
      document.getElementById('rawInput').value = `1\\n02:20–04:10\\n💰 TJR spent $500K in one month\\n2\\n05:40–07:45\\n🧠 What emotions destroy traders\\n3\\n22:05–25:50\\n💵 How much you actually need to make $10K/day\\n4\\n25:50–27:35\\n🎓 Why you don't necessarily need to buy a course\\n5\\n30:10–32:35\\n🚨 Why prop firms can ban traders\\n6\\n36:10–37:30\\n💰 TJR's biggest single trade\\n7\\n40:15–42:50\\n🧨 “The biggest pyramid scheme…”\\n8\\n45:00–47:40\\n🏎️ Buying a Koenigsegg\\n9\\n01:04:00–01:08:50\\n🎓 Why TJR dropped out of college\\n10\\n01:08:50–01:11:35\\n🖤 TJR discusses his darkest period`;
      parseClips();
    }
  </script>
</body>
</html>"""

@app.post("/api/download")
def download_clips(req: DownloadRequest):
    out_dir = "/tmp/clips_output"
    os.makedirs(out_dir, exist_ok=True)
    generated_files = []

    for f in os.listdir(out_dir):
        try: os.remove(os.path.join(out_dir, f))
        except: pass

    for clip in req.clips:
        safe_title = clean_filename(clip.title)
        filename = f"{clip.rank:02d}_{safe_title}.mp4"
        filepath = os.path.join(out_dir, filename)

        cmd = [
            "yt-dlp",
            "--extractor-args", "youtube:player_client=android,web",
            "--download-sections", f"*{clip.start}-{clip.end}",
            "--force-keyframes-at-cuts",
            "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
            "--postprocessor-args", "ffmpeg:-c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart",
            "-o", filepath,
            req.url
        ]

        subprocess.run(cmd, capture_output=True, text=True)
        if os.path.exists(filepath):
            generated_files.append(filepath)

    if not generated_files:
        raise HTTPException(status_code=500, detail="Failed to slice clips. Make sure the video is public.")

    zip_path = "/tmp/CapCut_Clips.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for f in generated_files:
            zipf.write(f, arcname=os.path.basename(f))

    return FileResponse(zip_path, media_type="application/zip", filename="CapCut_Clips.zip")

