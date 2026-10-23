// Generische Info-Buttons: ein <button class="info-btn" data-info-toggle="ID">i</button>
// oeffnet den Hinweistext mit dieser ID als schwebendes Popup in der Naehe
// des Buttons (position:fixed, ueber getBoundingClientRect platziert), statt
// ihn im Fliesstext einzublenden - fuer laengere Erklaerungen, die nicht
// staendig im Weg stehen sollen, aber bei Bedarf griffbereit sind. Es ist
// immer nur ein Popup gleichzeitig offen; Klick auf einen anderen Info-
// Button, in ein Feld oder sonst irgendwohin schliesst das offene wieder.
function closeInfoPopovers() {
  document.querySelectorAll(".info-popover:not([hidden])").forEach((el) => {
    el.hidden = true;
  });
}
function positionInfoPopover(btn, popover) {
  const rect = btn.getBoundingClientRect();
  popover.style.left = "0px";
  popover.style.top = "0px";
  popover.hidden = false;
  const popRect = popover.getBoundingClientRect();
  let left = rect.left;
  const maxLeft = window.innerWidth - popRect.width - 8;
  if (left > maxLeft) left = Math.max(8, maxLeft);
  let top = rect.bottom + 6;
  const maxTop = window.innerHeight - popRect.height - 8;
  if (top > maxTop) top = Math.max(8, rect.top - popRect.height - 6);
  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
}
document.addEventListener("click", (event) => {
  const infoBtn = event.target.closest("[data-info-toggle]");
  if (infoBtn) {
    const target = document.getElementById(infoBtn.getAttribute("data-info-toggle"));
    if (!target) return;
    const wasOpen = !target.hidden;
    closeInfoPopovers();
    if (!wasOpen) positionInfoPopover(infoBtn, target);
    event.stopPropagation();
    return;
  }
  if (!event.target.closest(".info-popover")) closeInfoPopovers();
});

// Würzekochen: Alpha (%) wird beim Auswählen eines Lagerartikels einmalig
// aus dessen hinterlegter Alphasäure übernommen - nur in dem Moment der
// Auswahl, keine dauerhafte Bindung. Manuelle Änderungen danach bleiben
// unangetastet, und spätere Änderungen am Lagerartikel wirken sich nicht
// rückwirkend auf bereits gespeicherte Suden aus (der Wert landet als
// eigenstaendiger Schnappschuss in HopAddition.alpha_acid_percent).
document.addEventListener("change", (event) => {
  const select = event.target.closest('select[name="hop_inventory_id"]');
  if (!select) return;
  const opt = select.options[select.selectedIndex];
  const alpha = opt ? opt.dataset.alpha : "";
  if (alpha) {
    const alphaInput = select.closest("tr").querySelector('input[name="hop_alpha"]');
    if (alphaInput) alphaInput.value = alpha;
  }
  updateIbuPreviews();
});

// Würzekochen: IBU-Beitrag je Zeile nach der Tinseth-Formel, live im
// Bearbeiten-Formular berechnet (JS-Nachbau von formulas.tinseth_ibu) -
// auf Basis der geplanten Stammwürze, da der gemessene Wert ("nach dem
// Kochen") in diesem Formular gar nicht mehr gepflegt wird (eigener
// Dialog auf der Sud-Detailseite).
function platoToSg(plato) {
  return 1 + plato / (258.6 - (plato / 258.2) * 227.1);
}
function tinsethIbu(weightG, alphaPercent, boilTimeMin, batchVolumeL, ogPlato) {
  if (!(weightG > 0) || !(alphaPercent > 0) || !(batchVolumeL > 0) || !(ogPlato > 0)) return null;
  const ogSg = platoToSg(ogPlato);
  const bignessFactor = 1.65 * Math.pow(0.000125, ogSg - 1);
  const boilTimeFactor = (1 - Math.exp(-0.04 * boilTimeMin)) / 4.15;
  const utilization = bignessFactor * boilTimeFactor;
  const aauMgPerL = (weightG * (alphaPercent / 100) * 1000) / batchVolumeL;
  return Math.round(utilization * aauMgPerL * 10) / 10;
}
function updateIbuPreviews() {
  const rows = document.querySelectorAll('tbody[data-rows="hop"] tr');
  if (!rows.length) {
    updateHopSums();
    return;
  }
  const batchVolumeL = parseFloat(document.querySelector('input[name="target_volume_l"]')?.value);
  const ogPlato = parseFloat(document.querySelector('input[name="target_og_plato"]')?.value);
  rows.forEach((row) => {
    const preview = row.querySelector("[data-ibu-preview]");
    if (!preview) return;
    const weightG = parseFloat(row.querySelector('input[name="hop_amount_g"]')?.value);
    const alphaPercent = parseFloat(row.querySelector('input[name="hop_alpha"]')?.value);
    const boilTimeMin = parseFloat(row.querySelector('input[name="hop_time_min"]')?.value) || 0;
    const ibu = tinsethIbu(weightG, alphaPercent, boilTimeMin, batchVolumeL, ogPlato);
    preview.dataset.ibu = ibu === null ? "" : String(ibu);
    preview.textContent = ibu === null ? "–" : fmtNum(ibu, 1);
  });
  updateHopSums();
}
document.addEventListener("input", (event) => {
  if (
    event.target.matches(
      'input[name="hop_amount_g"], input[name="hop_alpha"], input[name="hop_time_min"], input[name="target_volume_l"], input[name="target_og_plato"]'
    )
  ) {
    updateIbuPreviews();
  }
});

// Generische Zeilen-Verwaltung für die dynamischen Tabellen im Sud-Formular.
// Jede Sektion hat: ein <tbody data-rows="NAME">, ein <template data-row-template="NAME">
// und einen Button [data-add-row="NAME"].

document.addEventListener("click", (event) => {
  const addBtn = event.target.closest("[data-add-row]");
  if (addBtn) {
    event.preventDefault();
    const name = addBtn.getAttribute("data-add-row");
    const tbody = document.querySelector(`[data-rows="${name}"]`);
    const template = document.querySelector(`[data-row-template="${name}"]`);
    if (tbody && template) {
      const clone = template.content.cloneNode(true);
      tbody.appendChild(clone);
    }
    updateGrainEbcInputs();
    updateColorEbcAutoState();
    updateIbuPreviews();
    updateFormSums();
    return;
  }

  const removeBtn = event.target.closest("[data-remove-row]");
  if (removeBtn) {
    event.preventDefault();
    removeBtn.closest("tr").remove();
    updateColorEbcAutoState();
    updateIbuPreviews();
    updateFormSums();
    return;
  }

  const upBtn = event.target.closest("[data-move-up]");
  if (upBtn) {
    event.preventDefault();
    const row = upBtn.closest("tr");
    const prev = row.previousElementSibling;
    if (prev) row.parentNode.insertBefore(row, prev);
    return;
  }

  const downBtn = event.target.closest("[data-move-down]");
  if (downBtn) {
    event.preventDefault();
    const row = downBtn.closest("tr");
    const next = row.nextElementSibling;
    if (next) row.parentNode.insertBefore(next, row);
  }
});

// Brautag-Zeitplan-Dialog: Dauer aus Beginn/Ende berechnen, sobald beide
// <input type="time">-Felder einer Zeile gefuellt sind (manuelle Eingabe
// der Dauer bleibt trotzdem jederzeit moeglich, wird nur bei einer
// Aenderung von Beginn/Ende ueberschrieben).
document.addEventListener("input", (event) => {
  const timeField = event.target.closest("[data-schedule-start], [data-schedule-end]");
  if (!timeField) return;
  const row = timeField.closest("[data-schedule-row]");
  if (!row) return;
  const start = row.querySelector("[data-schedule-start]").value;
  const end = row.querySelector("[data-schedule-end]").value;
  if (!start || !end) return;
  const [startH, startM] = start.split(":").map(Number);
  const [endH, endM] = end.split(":").map(Number);
  let minutes = (endH * 60 + endM) - (startH * 60 + startM);
  if (minutes < 0) minutes += 24 * 60; // Ende nach Mitternacht
  row.querySelector("[data-schedule-duration]").value = minutes;
});

// Sud-Übersicht: Checkbox "Vergleichen" je Zeile - hebt die Zeile farblich
// hervor und haelt den Zaehler/Aktivierungszustand des "Vergleichen"-Buttons
// oben im Seitenkopf synchron (Button ist per form="compare-form" mit den
// verstreuten Checkboxen verbunden, siehe batch_list.html).
function updateCompareButton() {
  const btn = document.getElementById("compare-submit");
  if (!btn) return;
  const count = document.querySelectorAll("[data-compare-checkbox]:checked").length;
  btn.disabled = count === 0;
  btn.textContent = count > 0 ? `Vergleichen (${count})` : "Vergleichen";
}
document.addEventListener("change", (event) => {
  const checkbox = event.target.closest("[data-compare-checkbox]");
  if (!checkbox) return;
  checkbox.closest("tr").classList.toggle("row-selected", checkbox.checked);
  updateCompareButton();
});
updateCompareButton();

// Farbe (EBC) in Stammdaten: wird ausgegraut/schreibgeschuetzt, sobald die
// automatische Berechnung aus der Schüttung greift (jede Position mit einem
// Malz-Lagerartikel mit hinterlegter Eigenfarbe verknuepft - siehe dieselbe
// Bedingung in batch_calc.compute_metrics()). Verhindert, dass man aus
// Gewohnheit schon vor dem Ausfuellen der Schüttung (weiter unten im
// Formular) einen EBC-Wert eintraegt, der dann ungenutzt bleibt.
function updateColorEbcAutoState() {
  const input = document.getElementById("color-ebc-input");
  const hint = document.getElementById("color-ebc-auto-hint");
  if (!input || !hint) return;
  const rows = activeGrainRows();
  const auto = rows.length > 0 && rows.every((r) => r.ebc !== null);
  input.readOnly = auto;
}
document.addEventListener("change", (event) => {
  if (event.target.closest("[data-grain-select]")) {
    updateGrainEbcInputs();
    updateColorEbcAutoState();
    updateFormSums();
  }
});
document.addEventListener("input", (event) => {
  if (event.target.matches('input[name="grain_color_ebc"]')) updateColorEbcAutoState();
});

// Live-Summen unter den Bereichen des Sud-Formulars (Schüttung, Maischplan,
// Hopfen, Stopfhopfen, Karbonisierung, Zeitplan) - werden bei jeder Eingabe
// neu berechnet, ohne zu speichern.
function fmtNum(n, decimals) {
  return n.toLocaleString("de-DE", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}
function fmtMinutes(min) {
  if (min < 60) return `${fmtNum(min, 0)} min`;
  const h = Math.floor(min / 60);
  const m = Math.round(min - h * 60);
  return `${h} h ${m} min`;
}
function numVal(row, name) {
  const v = parseFloat(row.querySelector(`input[name="${name}"]`)?.value);
  return Number.isFinite(v) ? v : 0;
}
function setSums(name, items) {
  const el = document.querySelector(`[data-sums="${name}"]`);
  if (!el) return;
  el.textContent = "";
  items.forEach(([label, value]) => {
    const span = document.createElement("span");
    span.className = "form-sum";
    span.append(`${label}: `);
    const strong = document.createElement("strong");
    strong.textContent = value;
    span.append(strong);
    el.append(span);
  });
}

// Schüttungszeilen, die tatsächlich etwas enthalten (die serverseitige
// Speicherung überspringt Zeilen ohne Lagerartikel und Namen ebenfalls).
function activeGrainRows() {
  const result = [];
  document.querySelectorAll('tbody[data-rows="grain"] tr').forEach((row) => {
    const select = row.querySelector("[data-grain-select]");
    const name = row.querySelector('input[name="grain_malt_name"]')?.value.trim();
    if (!select?.value && !name) return;
    // null = kein EBC-Wert hinterlegt/eingetragen; 0 ist ein gültiger Wert.
    let ebc = null;
    const raw = select?.value
      ? select.options[select.selectedIndex]?.dataset.ebc
      : row.querySelector('input[name="grain_color_ebc"]')?.value;
    if (raw !== undefined && raw.trim() !== "" && Number.isFinite(parseFloat(raw))) ebc = parseFloat(raw);
    result.push({ row, kg: numVal(row, "grain_amount_kg"), ebc });
  });
  return result;
}

// EBC-Feld je Schüttungszeile: bei Lagerartikel dessen Eigenfarbe
// (schreibgeschützt), sonst frei eintragbar - ein zuvor von Hand
// eingetragener Wert bleibt beim Zwischenwechsel erhalten.
function updateGrainEbcInputs() {
  document.querySelectorAll('tbody[data-rows="grain"] tr').forEach((row) => {
    const select = row.querySelector("[data-grain-select]");
    const input = row.querySelector('input[name="grain_color_ebc"]');
    if (!select || !input) return;
    if (select.value) {
      if (!input.readOnly) input.dataset.manual = input.value;
      const ebc = select.options[select.selectedIndex]?.dataset.ebc;
      input.value = ebc || "";
      input.placeholder = "kein EBC";
      input.readOnly = true;
    } else if (input.readOnly) {
      input.value = input.dataset.manual || "";
      input.placeholder = "EBC";
      input.readOnly = false;
    }
  });
}

function updateGrainSums() {
  if (!document.querySelector('[data-sums="grain"]')) return;
  const rows = activeGrainRows();
  const volume = parseFloat(document.querySelector('input[name="target_volume_l"]')?.value);
  const totalKg = rows.reduce((sum, r) => sum + r.kg, 0);
  const allEbc = rows.length > 0 && rows.every((r) => r.ebc !== null);
  const mcu = (r) => (r.kg > 0 && r.ebc > 0 ? r.kg * (r.ebc / 1.97) * 8.3454 : 0);
  const mcuTotal = rows.reduce((sum, r) => sum + mcu(r), 0);
  let beerEbc = null;
  if (allEbc && volume > 0) {
    beerEbc = mcuTotal > 0 ? Math.round(1.4922 * Math.pow(mcuTotal / volume, 0.6859) * 1.97 * 10) / 10 : 0;
  }
  document.querySelectorAll("[data-grain-share]").forEach((el) => (el.textContent = "–"));
  rows.forEach((r) => {
    const el = r.row.querySelector("[data-grain-share]");
    if (el && beerEbc !== null) el.textContent = fmtNum(mcuTotal > 0 ? (beerEbc * mcu(r)) / mcuTotal : 0, 1);
  });
  let colorText = "–";
  if (beerEbc !== null) colorText = `${fmtNum(beerEbc, 1)} EBC`;
  else if (rows.length && !allEbc) colorText = "– (EBC fehlt bei mind. einem Malz)";
  else if (rows.length && !(volume > 0)) colorText = "– (Ausschlagwürze fehlt)";
  setSums("grain", [
    ["Menge Malz gesamt", `${fmtNum(totalKg, 2)} kg`],
    ["Bierfarbe", colorText],
  ]);
}

function updateMashSums() {
  let total = 0;
  document.querySelectorAll('tbody[data-rows="mash"] tr').forEach((row) => (total += numVal(row, "mash_duration_min")));
  setSums("mash", [["Rasten gesamt", fmtMinutes(total)]]);
}

function updateHopSums() {
  if (!document.querySelector('[data-sums="hop"]')) return;
  let hopG = 0;
  let miscG = 0;
  let ibu = 0;
  document.querySelectorAll('tbody[data-rows="hop"] tr').forEach((row) => {
    const select = row.querySelector('select[name="hop_inventory_id"]');
    const isMisc = !!select?.options[select.selectedIndex]?.dataset.misc;
    const g = numVal(row, "hop_amount_g");
    if (isMisc) miscG += g;
    else hopG += g;
    ibu += parseFloat(row.querySelector("[data-ibu-preview]")?.dataset.ibu) || 0;
  });
  const items = [
    ["Hopfen gesamt", `${fmtNum(hopG, 1)} g`],
    ["IBU gesamt", fmtNum(ibu, 1)],
  ];
  if (miscG > 0) items.splice(1, 0, ["Sonstige Zutaten gesamt", `${fmtNum(miscG, 1)} g`]);
  setSums("hop", items);
}

function updateSimpleSums() {
  let dryHop = 0;
  document.querySelectorAll('tbody[data-rows="dryhop"] tr').forEach((row) => (dryHop += numVal(row, "dryhop_amount_g")));
  setSums("dryhop", [["Stopfhopfen gesamt", `${fmtNum(dryHop, 1)} g`]]);
  let sugar = 0;
  document.querySelectorAll('tbody[data-rows="carb"] tr').forEach((row) => (sugar += numVal(row, "carb_sugar_g")));
  setSums("carb", [["Zucker gesamt", `${fmtNum(sugar, 1)} g`]]);
  let taskMin = 0;
  document.querySelectorAll('tbody[data-rows="task"] tr').forEach((row) => (taskMin += numVal(row, "task_duration_min")));
  setSums("task", [["Dauer gesamt", fmtMinutes(taskMin)]]);
}

function updateFormSums() {
  updateGrainSums();
  updateMashSums();
  updateHopSums();
  updateSimpleSums();
}
document.addEventListener("input", (event) => {
  if (event.target.closest("tbody[data-rows], input[name='target_volume_l']")) updateFormSums();
});
document.addEventListener("change", (event) => {
  if (event.target.closest("tbody[data-rows]")) updateFormSums();
});
updateGrainEbcInputs();
updateColorEbcAutoState();
updateIbuPreviews();
updateFormSums();

// Sud-Ansicht: Schüttungstabelle und Tortendiagramm gemeinsam hervorheben -
// Elemente mit gleichem data-pie-index innerhalb einer data-pie-group.
document.addEventListener("mouseover", (event) => {
  const group = event.target.closest("[data-pie-group]");
  if (!group) {
    // Auf Touch-Geräten feuert mouseout nicht - Tippen woanders löst die Hervorhebung.
    document.querySelectorAll("[data-pie-group] .is-hover").forEach((el) => el.classList.remove("is-hover"));
    return;
  }
  const hit = event.target.closest("[data-pie-index]");
  group.querySelectorAll("[data-pie-index].is-hover").forEach((el) => el.classList.remove("is-hover"));
  if (hit) group.querySelectorAll(`[data-pie-index="${hit.dataset.pieIndex}"]`).forEach((el) => el.classList.add("is-hover"));
});
document.addEventListener("mouseout", (event) => {
  const group = event.target.closest("[data-pie-group]");
  if (group && !group.contains(event.relatedTarget)) group.querySelectorAll(".is-hover").forEach((el) => el.classList.remove("is-hover"));
});

// Datumsfelder zeigen ihr Format sonst je nach Browser-/Systemsprache an
// (z.B. mm/dd/yyyy) statt einheitlich dd.mm.yyyy - flatpickr übernimmt die
// Anzeige, das eigentliche Feld sendet weiterhin ISO-Format (yyyy-mm-dd).
if (window.flatpickr) {
  document.querySelectorAll('input[type="date"]').forEach((el) => {
    flatpickr(el, {
      altInput: true,
      altFormat: "d.m.Y",
      dateFormat: "Y-m-d",
      locale: "de",
      allowInput: true,
    });
  });
}

// PWA: Service Worker registrieren (Voraussetzung fuer "Installieren"/"Zum
// Startbildschirm hinzufuegen" auf iPhone, Android, Windows und Mac - siehe
// manifest.json + sw.js). Schlaegt in Browsern ohne Unterstuetzung oder
// ohne sicheren Kontext (kein HTTPS/localhost) einfach fehl, ohne die App
// zu beeintraechtigen.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}
