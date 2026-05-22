import asyncio
import json
import platform
import shutil
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional

from pydantic import BaseModel

app = FastAPI(title="ddlp")

app.mount("/static", StaticFiles(directory="static"), name="static")

DOWNLOADS_DIR = Path("./downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

FORMAT_PRESETS = {
    "best": {
        "label": "Best quality",
        "format": "bestvideo+bestaudio/best",
        "extra_args": [],
    },
    "mp4": {
        "label": "MP4",
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "extra_args": [],
    },
    "webm": {
        "label": "WebM",
        "format": "bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]/best",
        "extra_args": [],
    },
    "audio-mp3": {
        "label": "Audio (MP3)",
        "format": "bestaudio",
        "extra_args": ["-x", "--audio-format", "mp3"],
    },
    "audio-opus": {
        "label": "Audio (Opus)",
        "format": "bestaudio",
        "extra_args": ["-x", "--audio-format", "opus"],
    },
}


class DownloadRequest(BaseModel):
    urls: list[str]
    format: str = "best"
    output_dir: str = "./downloads"
    embed_thumbnail: bool = False
    subtitles: bool = False
    subtitle_langs: str = "en"
    playlist_start: Optional[int] = None
    playlist_end: Optional[int] = None


class CheckUrlRequest(BaseModel):
    url: str


@app.get("/api/health")
def health():
    ytdlp = shutil.which("yt-dlp")
    return {"yt-dlp": ytdlp is not None}


@app.get("/api/pick-folder")
async def pick_folder():
    system = platform.system()

    if system == "Darwin":
        try:
            result = subprocess.run(
                ["osascript", "-e",
                 'POSIX path of (choose folder with prompt "Select download folder")'],
                capture_output=True, text=True, timeout=30,
            )
            path = result.stdout.strip()
            if result.returncode == 0 and path:
                return {"path": path}
        except Exception:
            pass

    elif system == "Windows":
        try:
            ps = '''
            Add-Type -AssemblyName System.Windows.Forms
            $f = New-Object System.Windows.Forms.FolderBrowserDialog
            $f.Description = "Select download folder"
            if ($f.ShowDialog() -eq "OK") { Write-Output $f.SelectedPath }
            '''
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=30,
            )
            path = result.stdout.strip()
            if result.returncode == 0 and path:
                return {"path": path}
        except Exception:
            pass

    else:
        for tool in ["zenity", "kdialog"]:
            try:
                if tool == "zenity":
                    result = subprocess.run(
                        [tool, "--file-selection", "--directory",
                         "--title=Select download folder"],
                        capture_output=True, text=True, timeout=30,
                    )
                else:
                    result = subprocess.run(
                        [tool, "--getexistingdirectory",
                         "--title=Select download folder"],
                        capture_output=True, text=True, timeout=30,
                    )
                path = result.stdout.strip()
                if result.returncode == 0 and path:
                    return {"path": path}
            except Exception:
                continue

    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.lift()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="Select download folder")
        root.destroy()
        if folder:
            return {"path": folder}
    except Exception:
        pass

    raise HTTPException(400, "Folder picker unavailable. Type the path manually.")


@app.post("/api/check-url")
async def check_url(req: CheckUrlRequest):
    try:
        process = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--flat-playlist",
            "--dump-single-json",
            "--no-download",
            "--skip-download",
            req.url.strip(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)

        if process.returncode != 0:
            return {"error": stderr.decode("utf-8", errors="replace")}

        data = json.loads(stdout.decode("utf-8", errors="replace"))

        result = {"title": data.get("title", "")}

        if "playlist_count" in data:
            result["is_playlist"] = True
            result["playlist_count"] = data["playlist_count"]
        else:
            result["is_playlist"] = False
            subs = set()
            for lang in data.get("subtitles", {}):
                subs.add(lang)
            for lang in data.get("automatic_captions", {}):
                subs.add(lang)
            result["subtitles"] = sorted(subs)

        return result

    except asyncio.TimeoutError:
        return {"error": "Timed out checking URL"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/download")
async def download(req: DownloadRequest):
    preset = FORMAT_PRESETS.get(req.format)
    if not preset:
        raise HTTPException(400, f"Unknown format: {req.format}")

    output_dir = Path(req.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    async def event_stream():
        for i, url in enumerate(req.urls):
            url = url.strip()
            if not url:
                continue

            try:
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "start",
                            "url": url,
                            "index": i,
                            "total": len(req.urls),
                        }
                    )
                    + "\n\n"
                )

                cmd = [
                    "yt-dlp",
                    "-f",
                    preset["format"],
                    "-o",
                    f"{output_dir}/%(title)s.%(ext)s",
                    "--newline",
                    "--no-colors",
                ]

                if req.embed_thumbnail:
                    cmd.append("--embed-thumbnail")

                if req.subtitles:
                    cmd.append("--write-subs")
                    cmd.append("--write-auto-subs")
                    cmd.append("--embed-subs")
                    if req.subtitle_langs.strip():
                        cmd.extend(["--sub-langs", req.subtitle_langs.strip()])

                if req.playlist_start is not None:
                    cmd.extend(["--playlist-start", str(req.playlist_start)])
                if req.playlist_end is not None:
                    cmd.extend(["--playlist-end", str(req.playlist_end)])

                cmd.extend(preset["extra_args"])
                cmd.append(url)

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )

                full_output = []
                async for raw in process.stdout:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                    full_output.append(line)
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "type": "output",
                                "line": line,
                                "url": url,
                                "index": i,
                            }
                        )
                        + "\n\n"
                    )

                await process.wait()

                if process.returncode == 0:
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "type": "done",
                                "url": url,
                                "index": i,
                                "success": True,
                            }
                        )
                        + "\n\n"
                    )
                else:
                    log_tail = "\n".join(full_output[-10:])
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "type": "done",
                                "url": url,
                                "index": i,
                                "success": False,
                                "error": log_tail or "Download failed",
                            }
                        )
                        + "\n\n"
                    )

            except Exception as e:
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "done",
                            "url": url,
                            "index": i,
                            "success": False,
                            "error": str(e),
                        }
                    )
                    + "\n\n"
                )

        yield "data: " + json.dumps({"type": "complete"}) + "\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/")
def index():
    return FileResponse("static/index.html")
