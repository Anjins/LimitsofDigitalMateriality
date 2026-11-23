let lastResult = null;
let showingArchive = false;

const el = (id) => document.getElementById(id);

async function pollVitals() {
  try {
    const res = await fetch("/api/vitals");
    const v = await res.json();
    el("vitals").textContent = `cpu ${v.cpu.toFixed(0)}% ram ${v.ram.toFixed(0)}%`;
  } catch {}
}

setInterval(pollVitals, 1500);
pollVitals();

el("gensSlider").oninput = () => {
  el("gensVal").textContent = el("gensSlider").value;
};

el("intensitySlider").oninput = () => {
  el("intensityVal").textContent = Number(el("intensitySlider").value).toFixed(2);
};

el("healSlider").oninput = () => {
  el("healVal").textContent = Number(el("healSlider").value).toFixed(2);
};

el("simLoad").oninput = () => {
  el("simLoadVal").textContent = `${el("simLoad").value}%`;
};

el("modeSelect").onchange = () => {
  el("customLoadGroup").classList.toggle("hidden", el("modeSelect").value !== "custom");
};

el("toggleViewBtn").onclick = () => {
  showingArchive = !showingArchive;
  el("labView").classList.toggle("hidden", showingArchive);
  el("galleryView").classList.toggle("hidden", !showingArchive);
  if (showingArchive) loadGallery();
};

el("runBtn").onclick = async () => {
  el("runBtn").disabled = true;
  el("saveBtn").disabled = true;
  el("statusBox").textContent = "running...";

  const mode = el("modeSelect").value;
  const profileName = el("modeSelect").options[el("modeSelect").selectedIndex].text;

  const fd = new FormData();
  if (el("fileInput").files[0]) {
    fd.append("image", el("fileInput").files[0]);
  }
  fd.append("gens", el("gensSlider").value);
  fd.append("intensity", el("intensitySlider").value);
  fd.append("heal", el("healSlider").value);
  fd.append("scars", el("scarsCheck").checked);
  fd.append("mode", mode);
  fd.append("simLoad", el("simLoad").value);
  fd.append("profileName", profileName);

  try {
    const res = await fetch("/api/run", { method: "POST", body: fd });
    const data = await res.json();
    lastResult = data;

    el("stripImg").src = data.stripImage;
    el("stripImg").classList.remove("hidden");
    if (showingArchive) el("toggleViewBtn").click();

    el("statusBox").textContent = "done";
    el("saveBtn").disabled = false;
  } catch (err) {
    el("statusBox").textContent = err.message;
  } finally {
    el("runBtn").disabled = false;
  }
};

el("saveBtn").onclick = async () => {
  if (!lastResult) return;
  el("saveBtn").disabled = true;
  await fetch("/api/gallery", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      summary: lastResult.summary,
      recipe: lastResult.recipe,
      stripImage: lastResult.stripImage,
    }),
  });
  el("statusBox").textContent = "saved";
  loadGallery();
};

async function loadGallery() {
  const res = await fetch("/api/gallery");
  const items = await res.json();
  el("galleryCount").textContent = items.length;

  const gv = el("galleryView");
  gv.innerHTML = items.length ? "" : "empty";

  items.forEach((item) => {
    const s = item.summary;
    const r = item.recipe;
    const div = document.createElement("div");
    div.className = "archive-item";
    div.innerHTML = `
      <img class="strip" src="${item.imageUrl}" alt="" />
      <div class="archive-meta">
        ${s.profileName} | ${item.timestamp} | gens:${r.gens} int:${r.intensity} heal:${r.heal} | load:${s.meanLoad}% scars:${s.scarredFrames}
        <button>fork</button>
      </div>
    `;
    div.querySelector("button").onclick = () => {
      el("gensSlider").value = r.gens;
      el("gensSlider").oninput();
      el("intensitySlider").value = r.intensity;
      el("intensitySlider").oninput();
      el("healSlider").value = r.heal;
      el("healSlider").oninput();
      el("scarsCheck").checked = r.scars;
      if (showingArchive) el("toggleViewBtn").click();
    };
    gv.appendChild(div);
  });
}

loadGallery();