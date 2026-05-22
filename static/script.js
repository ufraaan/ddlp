const urlList = document.getElementById("url-list");
const addBtn = document.getElementById("add-url");
const formatSelect = document.getElementById("format");
const formatNote = document.getElementById("format-note");
const outputDir = document.getElementById("output-dir");
const browseBtn = document.getElementById("browse-btn");
const embedThumb = document.getElementById("embed-thumbnail");
const subsToggle = document.getElementById("subtitles-toggle");
const subLangs = document.getElementById("sub-langs");
const subtitleOpts = document.getElementById("subtitle-opts");
const playlistSection = document.getElementById("playlist-section");
const playlistLabel = document.getElementById("playlist-label");
const playlistCount = document.getElementById("playlist-count");
const playlistStart = document.getElementById("playlist-start");
const playlistEnd = document.getElementById("playlist-end");
const downloadBtn = document.getElementById("download-btn");
const status = document.getElementById("status");
const log = document.getElementById("log");

const NOTES = {
  best: "Prioritises quality over format. Output is commonly WebM.",
};

function updateFormatNote() {
  formatNote.textContent = NOTES[formatSelect.value] || "";
}

formatSelect.addEventListener("change", updateFormatNote);
updateFormatNote();

subsToggle.addEventListener("change", () => {
  subtitleOpts.hidden = !subsToggle.checked;
});

function getUrlInputs() {
  return urlList.querySelectorAll(".url-input");
}

function urlCheckDebounce() {
  clearTimeout(urlCheckDebounce._timer);
  urlCheckDebounce._timer = setTimeout(checkFirstUrl, 600);
}

async function checkFirstUrl() {
  const inputs = getUrlInputs();
  const url = inputs[0]?.value.trim();
  if (!url) {
    playlistSection.hidden = true;
    return;
  }

  try {
    const res = await fetch("/api/check-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) return;
    const data = await res.json();
    if (data.is_playlist) {
      playlistLabel.textContent = data.title || "Playlist";
      playlistCount.textContent = `${data.playlist_count} videos`;
      playlistStart.value = 1;
      playlistEnd.value = "";
      playlistEnd.max = data.playlist_count;
      playlistSection.hidden = false;
    } else {
      playlistSection.hidden = true;
    }
  } catch {
    playlistSection.hidden = true;
  }
}

function addUrlRow(value) {
  const row = document.createElement("div");
  row.className = "url-row";

  const input = document.createElement("input");
  input.type = "text";
  input.className = "url-input";
  input.placeholder = "https://youtube.com/watch?v=...";
  if (value) input.value = value;
  input.addEventListener("input", urlCheckDebounce);

  row.appendChild(input);

  const all = getUrlInputs();
  if (all.length > 0) {
    const remove = document.createElement("button");
    remove.className = "btn-remove";
    remove.textContent = "\u00d7";
    remove.addEventListener("click", () => {
      row.remove();
      updateRemoveButtons();
      urlCheckDebounce();
    });
    row.appendChild(remove);
  }

  urlList.appendChild(row);
  updateRemoveButtons();
  input.focus();
}

function updateRemoveButtons() {
  const rows = urlList.querySelectorAll(".url-row");
  rows.forEach((row, i) => {
    const rm = row.querySelector(".btn-remove");
    if (rm) {
      rm.style.display = rows.length > 1 ? "flex" : "none";
    }
  });
}

addBtn.addEventListener("click", () => addUrlRow());

urlList.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.classList.contains("url-input")) {
    e.preventDefault();
    addUrlRow();
  }
});

const firstInput = getUrlInputs()[0];
if (firstInput) {
  firstInput.addEventListener("input", urlCheckDebounce);
}

browseBtn.addEventListener("click", async () => {
  browseBtn.disabled = true;
  browseBtn.textContent = "Selecting\u2026";
  try {
    const res = await fetch("/api/pick-folder");
    if (res.ok) {
      const data = await res.json();
      outputDir.value = data.path;
    }
  } catch {
    // ignore
  } finally {
    browseBtn.disabled = false;
    browseBtn.textContent = "Browse";
  }
});

let abortController = null;

downloadBtn.addEventListener("click", async () => {
  if (abortController) return;

  const urlInputs = getUrlInputs();
  const urls = [];
  urlInputs.forEach((inp) => {
    const v = inp.value.trim();
    if (v) urls.push(v);
  });

  if (urls.length === 0) {
    urlInputs[0]?.focus();
    return;
  }

  abortController = new AbortController();
  downloadBtn.disabled = true;
  downloadBtn.textContent = "Downloading\u2026";
  status.hidden = false;
  log.innerHTML = "";

  try {
    const body = {
      urls,
      format: formatSelect.value,
      output_dir: outputDir.value.trim() || "./downloads",
      embed_thumbnail: embedThumb.checked,
      subtitles: subsToggle.checked,
      subtitle_langs: subLangs.value.trim() || "en",
    };

    if (!playlistSection.hidden) {
      const s = parseInt(playlistStart.value);
      const e = playlistEnd.value ? parseInt(playlistEnd.value) : null;
      if (!isNaN(s) && s > 0) body.playlist_start = s;
      if (e !== null && !isNaN(e) && e > 0) body.playlist_end = e;
    }

    const response = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: abortController.signal,
    });

    if (!response.ok) {
      appendLine("error", `Server error: ${response.status} ${response.statusText}`);
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n");
      buffer = parts.pop() || "";

      for (const part of parts) {
        if (part.startsWith("data: ")) {
          try {
            const data = JSON.parse(part.slice(6));
            handleEvent(data);
          } catch (e) {
            // ignore
          }
        }
      }
    }
  } catch (err) {
    if (err.name !== "AbortError") {
      appendLine("error", `Error: ${err.message}`);
    }
  } finally {
    abortController = null;
    downloadBtn.disabled = false;
    downloadBtn.textContent = "Download";
  }
});

function handleEvent(data) {
  switch (data.type) {
    case "start":
      appendLine("info", `[${data.index + 1}/${data.total}] Downloading\u2026`);
      break;
    case "output":
      appendLine(null, data.line);
      break;
    case "done":
      if (data.success) {
        appendLine("success", `[${data.index + 1}] Done`);
      } else {
        appendLine("error", `[${data.index + 1}] Failed`);
        if (data.error) {
          appendLine("error", data.error);
        }
      }
      break;
    case "complete":
      appendLine("info", "All done");
      break;
  }
}

function appendLine(cls, text) {
  if (!text) return;
  const p = document.createElement("div");
  if (cls) p.className = cls;
  p.textContent = text;
  log.appendChild(p);
  log.scrollTop = log.scrollHeight;
}
