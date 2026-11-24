"use strict";

const byId = (id) => document.getElementById(id);
const letters = ["A", "B", "C"];
const coverInputs = ["cover-a", "cover-b", "cover-c"].map(byId);
const coverBatch = byId("cover-batch");
const restoreInputs = ["card-first", "card-second"].map(byId);
const sourceInput = byId("source");
const workspace = byId("ruang-kerja");
const demoSelect = byId("demo-circuit");
const evalSelect = byId("eval-circuit");
const jsonLimit = 65_536;
const pngLimit = 13 * 1024 * 1024;
const fileLabels = new Map(
  [...document.querySelectorAll("[data-file-for]")].map((label) => [label.dataset.fileFor, label]),
);
const objectUrls = new WeakMap();
const number = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });
const fileOrder = new Intl.Collator("id-ID", { numeric: true, sensitivity: "base" });
const textDecoder = new TextDecoder("utf-8");
const circuits = new Map();
const demoPromises = new Map();
const sourceDigests = new Map();
let lastCards;

function status(id, message = "", state = "info") {
  const element = byId(id);
  element.textContent = message;
  element.dataset.state = state;
  element.hidden = !message;
}

function replaceUrl(element, blob, attribute = "href") {
  if (objectUrls.has(element)) URL.revokeObjectURL(objectUrls.get(element));
  const url = URL.createObjectURL(blob);
  objectUrls.set(element, url);
  element[attribute] = url;
}

function bytesFromBase64(data) {
  return Uint8Array.from(atob(data), (character) => character.charCodeAt(0));
}

function fileAsBase64(file, limit) {
  if (!file) throw new Error("Lengkapi semua berkas yang diperlukan.");
  if (file.size > limit) throw new Error(`${file.name} melebihi batas ${number.format(limit)} byte.`);
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Tidak dapat membaca ${file.name}.`));
    reader.onload = () => resolve(reader.result.split(",", 2)[1]);
    reader.readAsDataURL(file);
  });
}

async function api(path, data) {
  let response;
  try {
    response = await fetch(`/api/${path}`, data === undefined ? undefined : {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  } catch {
    throw new Error("Server lokal terputus. Jalankan kembali SetupVault.");
  }
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Operasi gagal. Coba lagi.");
  return result;
}

function showView() {
  const view = location.hash.slice(1) || "cadangan";
  if (!["cadangan", "pulihkan", "evaluasi"].includes(view)) return;
  workspace.dataset.view = view;
  byId("session-aside").hidden = view === "evaluasi";
  for (const link of document.querySelectorAll("[data-nav]")) {
    const current = link.dataset.nav === view;
    byId(`view-${link.dataset.nav}`).hidden = !current;
    if (current) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

function setFile(input, file) {
  const transfer = new DataTransfer();
  transfer.items.add(file);
  input.files = transfer.files;
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

async function refreshSource() {
  const file = sourceInput.files[0];
  const details = byId("source-details");
  details.hidden = true;
  byId("source-preview").textContent = "";
  if (!file || file.size > jsonLimit) return;
  try {
    const preview = await file.text();
    if (file !== sourceInput.files[0]) return;
    byId("source-preview").textContent = preview;
    details.hidden = false;
  } catch {
    details.hidden = true;
  }
}

for (const input of [sourceInput, ...coverInputs, ...restoreInputs]) {
  input.addEventListener("change", () => {
    const label = fileLabels.get(input.id);
    const file = input.files[0];
    const field = input.closest(".file-field");
    const action = field.querySelector(".file-action");
    label.textContent = file?.name || "";
    label.title = file?.name || "";
    label.hidden = !file;
    field.toggleAttribute("data-selected", Boolean(file));
    field.querySelector(".file-state").textContent = file ? "Terpilih" : "Belum dipilih";
    action.textContent = `${file ? "Ganti" : "Pilih"} ${input === sourceInput ? "JSON" : "PNG"}`;
    if (restoreInputs.includes(input)) {
      byId("restore-result").hidden = true;
      byId("restored-preview").textContent = "";
      status("restore-status");
    } else {
      byId("backup-result").hidden = true;
      status("backup-status");
    }
    if (input === sourceInput) refreshSource();
  });
}

coverBatch.addEventListener("change", () => {
  const files = [...coverBatch.files];
  coverBatch.value = "";
  if (files.length !== coverInputs.length) {
    status("backup-status", "Pilih tepat tiga PNG untuk mengisi sampul A, B, dan C sekaligus.", "error");
    return;
  }
  files.sort((first, second) => fileOrder.compare(first.name, second.name));
  coverInputs.forEach((input, index) => setFile(input, files[index]));
  status("backup-status", "Sampul A, B, dan C diisi sesuai urutan nama berkas.", "good");
});

function loadDemo(circuit) {
  if (!demoPromises.has(circuit.id)) {
    const prefix = `${circuit.id}-${circuit.session}`;
    const version = String(circuit.version).padStart(2, "0");
    const request = api(`demo?circuit=${encodeURIComponent(circuit.id)}`).then(({ data, covers }) => ({
      source: new File([bytesFromBase64(data)], `${prefix}-setup-v${version}.json`, { type: "application/json" }),
      covers: covers.map((cover, index) => new File(
        [bytesFromBase64(cover)], `${prefix}-sampul-${letters[index]}.png`, { type: "image/png" },
      )),
    })).catch((error) => {
      demoPromises.delete(circuit.id);
      throw error;
    });
    demoPromises.set(circuit.id, request);
  }
  return demoPromises.get(circuit.id);
}

function circuitStats(circuit) {
  return `${circuit.length} km / ${circuit.turns} tikungan`;
}

function displayDemoCard(circuit, demo) {
  const preview = byId("session-preview");
  replaceUrl(preview, demo.covers[0], "src");
  preview.alt = `Kartu A sesi ${circuit.session} dengan peta ${circuit.name} dan kondisi sintetis`;
  preview.hidden = false;
  byId("session-placeholder").hidden = true;
}

async function refreshDemoCircuit() {
  const circuit = circuits.get(demoSelect.value);
  const placeholder = byId("session-placeholder");
  byId("load-demo").textContent = `Muat demo ${circuit.session}`;
  byId("session-stats").textContent = circuitStats(circuit);
  byId("open-map").disabled = false;
  byId("session-preview").hidden = true;
  placeholder.textContent = `Memuat kartu ${circuit.name}…`;
  placeholder.hidden = false;
  try {
    const demo = await loadDemo(circuit);
    if (demoSelect.value === circuit.id) displayDemoCard(circuit, demo);
  } catch {
    if (demoSelect.value === circuit.id) placeholder.textContent = "Kartu contoh belum dapat dimuat.";
  }
}

async function initCircuits() {
  const catalog = await api("circuits");
  for (const circuit of catalog.circuits) circuits.set(circuit.id, circuit);
  for (const select of [demoSelect, evalSelect]) {
    select.replaceChildren(...catalog.circuits.map(({ id, name }) => new Option(name, id)));
    select.value = catalog.default;
    select.disabled = false;
  }
  byId("load-demo").disabled = false;
  byId("run-evaluation").disabled = false;
  await refreshDemoCircuit();
}

async function work(controlIds, statusId, message, operation) {
  const controls = controlIds.map(byId);
  for (const control of controls) control.disabled = true;
  status(statusId, message);
  try {
    await operation();
  } catch (error) {
    status(statusId, error.message, "error");
  } finally {
    for (const control of controls) control.disabled = false;
  }
}

demoSelect.addEventListener("change", () => {
  refreshDemoCircuit();
  if ([sourceInput, ...coverInputs].some((input) => input.files.length)) {
    const { session } = circuits.get(demoSelect.value);
    status("backup-status", `Klik Muat demo ${session} untuk mengganti JSON dan sampul yang terpilih.`);
  }
});

byId("load-demo").addEventListener("click", () => {
  if (byId("backup-button").disabled) return;
  const circuit = circuits.get(demoSelect.value);
  work(["demo-circuit", "load-demo", "backup-button", "backup-fields"], "backup-status", "Memuat berkas demo…", async () => {
    const demo = await loadDemo(circuit);
    displayDemoCard(circuit, demo);
    setFile(sourceInput, demo.source);
    coverInputs.forEach((input, index) => setFile(input, demo.covers[index]));
    status("backup-status", `Satu JSON dan tiga sampul ${circuit.session} siap.`, "good");
  });
});

byId("backup-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const source = sourceInput.files[0];
  const covers = coverInputs.map((input) => input.files[0]);
  byId("backup-result").hidden = true;
  const controls = ["backup-button", "backup-fields"];
  if (circuits.size) controls.push("demo-circuit", "load-demo");
  work(controls, "backup-status", "Membuat tiga kartu PNG…", async () => {
    const [data, ...encodedCovers] = await Promise.all([
      fileAsBase64(source, jsonLimit),
      ...covers.map((file) => fileAsBase64(file, pngLimit)),
    ]);
    const result = await api("backup", { data, covers: encodedCovers });
    const files = result.cards.map((card, index) => new File(
      [bytesFromBase64(card)], `SetupVault-${result.package.slice(0, 12)}-${letters[index]}.png`,
      { type: "image/png" },
    ));
    lastCards = files;
    sourceDigests.set(result.package, result.digest);
    byId("backup-id").textContent = result.package;
    byId("backup-digest").textContent = result.digest;
    files.forEach((file, index) => {
      const link = byId(`download-${letters[index].toLowerCase()}`);
      replaceUrl(link, file);
      link.download = file.name;
    });
    byId("comparison").open = false;
    replaceUrl(byId("before-image"), covers[0], "src");
    replaceUrl(byId("after-image"), files[0], "src");
    status("backup-status", "Tiga bagian tersisip pada PNG. Unduh kartu untuk dibagikan.", "good");
    byId("backup-result").hidden = false;
    byId("backup-result").scrollIntoView({ block: "nearest" });
  });
});

byId("use-pair").addEventListener("click", () => {
  if (!lastCards) return;
  setFile(restoreInputs[0], lastCards[0]);
  setFile(restoreInputs[1], lastCards[2]);
  location.hash = "pulihkan";
  showView();
  byId("restore-title").focus({ preventScroll: true });
  window.scrollTo(0, 0);
  status("restore-status", "Kartu A dan C dipilih. Kartu B dianggap tidak tersedia.");
});

byId("restore-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const files = restoreInputs.map((input) => input.files[0]);
  byId("restore-result").hidden = true;
  byId("restored-preview").textContent = "";
  work(["restore-button", "restore-fields"], "restore-status", "Mengekstrak dan memeriksa dua kartu…", async () => {
    const cards = await Promise.all(files.map((file) => fileAsBase64(file, pngLimit)));
    const result = await api("restore", { cards });
    const sourceDigest = sourceDigests.get(result.package);
    if (sourceDigest && result.digest !== sourceDigest) {
      throw new Error("SHA-256 hasil berbeda dari berkas sumber. Pemulihan dihentikan.");
    }
    const data = bytesFromBase64(result.data);
    const preview = textDecoder.decode(data);
    const { circuit } = JSON.parse(preview);
    const circuitName = typeof circuit === "string" ? circuit.trim() : "";
    byId("restored-circuit").textContent = circuitName;
    byId("restored-circuit-row").hidden = !circuitName;
    byId("restore-id").textContent = result.package;
    byId("restore-digest").textContent = result.digest;
    byId("restored-pair").textContent = result.indices.map((index) => letters[index - 1]).join(" + ");
    byId("restored-preview").textContent = preview;
    const download = byId("download-json");
    replaceUrl(download, new Blob([data], { type: "application/json" }));
    download.download = `SetupVault-${result.package.slice(0, 12)}-pulih.json`;
    status("restore-proof", sourceDigest ? "SHA-256 hasil cocok dengan berkas sumber." : "", "good");
    status("restore-status", "Dua kartu valid. Rekonstruksi selesai.", "good");
    byId("restore-result").hidden = false;
    byId("restore-result").scrollIntoView({ block: "nearest" });
  });
});

const metricKeys = [
  "bytes", "successes", "attempts", "backup_ms", "restore_ms", "mse",
  "psnr_db", "ssim", "packet_bytes", "png_bytes",
];

function renderEvaluation(report) {
  const sum = (key) => report.rows.reduce((total, row) => total + row[key], 0);
  const checks = report.scenarios.filter((test) => test.pass !== null);
  byId("total-success").textContent = `${sum("successes")} / ${sum("attempts")}`;
  byId("total-images").textContent = report.image_comparisons;
  byId("total-rejections").textContent = `${checks.filter((test) => test.pass).length} / ${checks.length}`;
  byId("metrics").replaceChildren(...report.rows.map((row) => {
    const tr = document.createElement("tr");
    const values = [
      number.format(row.bytes), `${row.successes}/${row.attempts}`,
      row.backup_ms.toFixed(2), row.restore_ms.toFixed(2), row.mse.toFixed(6),
      row.psnr_db?.toFixed(2) ?? "∞", row.ssim.toFixed(6),
      number.format(row.packet_bytes), number.format(row.png_bytes),
    ];
    values.forEach((value, index) => {
      const cell = document.createElement(index === 0 ? "th" : "td");
      if (index === 0) cell.scope = "row";
      cell.textContent = value;
      tr.append(cell);
    });
    return tr;
  }));
  byId("eval-cases").replaceChildren(...report.scenarios.map((test) => {
    const item = document.createElement("li");
    const label = document.createElement("strong");
    const detail = document.createElement("span");
    label.textContent = test.label;
    const outcome = test.pass === null ? "Observasi" : test.pass ? "Lolos" : "Gagal";
    detail.textContent = `${outcome} · ${test.detail}`;
    item.append(label, detail);
    return item;
  }));
  const csv = [metricKeys.join(","), ...report.rows.map((row) => metricKeys.map((key) => row[key]).join(","))];
  replaceUrl(byId("download-csv"), new Blob([csv.join("\r\n") + "\r\n"], { type: "text/csv" }));
  byId("eval-result").hidden = false;
}

evalSelect.addEventListener("change", () => {
  byId("eval-result").hidden = true;
  status("eval-status");
});

byId("run-evaluation").addEventListener("click", () => {
  const circuit = circuits.get(evalSelect.value);
  byId("eval-result").hidden = true;
  work(["eval-circuit", "run-evaluation"], "eval-status", "Menjalankan 150 percobaan pemulihan dan 150 pengukuran citra…", async () => {
    const report = await api("evaluate", { circuit: circuit.id });
    renderEvaluation(report);
    byId("download-csv").download = `setupvault-evaluasi-${circuit.id}.csv`;
    const passed = report.rows.every((row) => row.successes === row.attempts)
      && report.scenarios.every((test) => test.pass !== false);
    status("eval-status", passed ? "Evaluasi selesai." : "Evaluasi selesai. Ada pengujian yang gagal.", passed ? "good" : "error");
  });
});

const trackDialog = byId("track-dialog");
const trackViewport = byId("track-viewport");
const trackZoom = byId("track-zoom");

byId("open-map").addEventListener("click", () => {
  const circuit = circuits.get(demoSelect.value);
  const image = byId("track-image");
  const timingLines = circuit.hasControlLine ? "garis start dan kontrol" : "start dan finish";
  image.src = `/${encodeURIComponent(circuit.id)}-detail.png`;
  image.alt = `Lintasan ${circuit.name} dengan nomor tikungan 1–${circuit.turns}, ${timingLines}, serta pit lane`;
  byId("track-title").textContent = circuit.name;
  byId("track-stats").textContent = `Grand Prix Circuit / ${circuitStats(circuit)}`;
  byId("track-start-legend").textContent = circuit.hasControlLine ? "Start" : "Start / finish";
  byId("track-control-legend").hidden = !circuit.hasControlLine;
  trackDialog.showModal();
});

trackZoom.addEventListener("click", () => {
  const zoomed = trackViewport.dataset.zoom !== "true";
  trackViewport.dataset.zoom = zoomed;
  trackZoom.textContent = zoomed ? "Perkecil" : "Perbesar";
});

trackDialog.addEventListener("close", () => {
  delete trackViewport.dataset.zoom;
  trackZoom.textContent = "Perbesar";
});

window.addEventListener("hashchange", showView);
showView();
if (location.protocol === "file:") {
  byId("server-notice").hidden = false;
  workspace.inert = true;
  byId("session-placeholder").textContent = "Kartu contoh tersedia saat server berjalan.";
} else {
  initCircuits().catch(() => {
    byId("server-notice").hidden = false;
    byId("session-placeholder").textContent = "Daftar sirkuit belum dapat dimuat.";
    status("eval-status", "Daftar sirkuit belum dapat dimuat. Muat ulang halaman.", "error");
  });
}
