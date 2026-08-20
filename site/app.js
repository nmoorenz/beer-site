(function () {
  "use strict";

  var RATING = {
    yeah: { emoji: "👍", label: "Yeah" },
    eh:   { emoji: "😐", label: "Eh" },
    nah:  { emoji: "👎", label: "Nah" },
  };

  var state = { beers: [], year: "all", rating: "all", brewery: "all", type: "all", tag: "all", sort: "newest" };
  var lb = { beer: null, index: 0 };

  var els = {
    grid:     document.getElementById("grid"),
    empty:    document.getElementById("empty"),
    loading:  document.getElementById("loading"),
    stats:    document.getElementById("stats"),
    controls: document.getElementById("controls"),
    year:     document.getElementById("year-filter"),
    rating:   document.getElementById("rating-filter"),
    brewery:  document.getElementById("brewery-filter"),
    type:     document.getElementById("type-filter"),
    tag:      document.getElementById("tag-filter"),
    sort:     document.getElementById("sort-order"),
    lightbox: document.getElementById("lightbox"),
  };

  function manifestUrl() {
    var cfg = window.BEER_SITE_CONFIG || {};
    return cfg.manifestUrl || "manifest.json";
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function setMeta(id, value) {
    var el = document.getElementById(id);
    el.textContent = value || "";
    el.style.display = value ? "" : "none";
  }

  function yearOf(b) {
    return b.year || String(b.date || "").slice(0, 4);
  }

  // -- Load --
  fetch(manifestUrl(), { cache: "no-store" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (data) {
      state.beers = (data && data.beers) || [];
      els.loading.hidden = true;
      if (!state.beers.length) { els.empty.hidden = false; renderStats(data); return; }
      els.controls.hidden = false;
      populateFilters();
      renderStats(data);
      render();
    })
    .catch(function (err) {
      els.loading.textContent = "Couldn't load the beer list. Try again later.";
      console.error("manifest load failed:", err);
    });

  function renderStats() {
    els.stats.innerHTML = "";
  }
  function countLocal() {
    var c = { total: state.beers.length, yeah: 0, eh: 0, nah: 0 };
    state.beers.forEach(function (b) { if (c[b.rating] != null) c[b.rating]++; });
    return c;
  }
  function stat(value, label) {
    return '<div class="stat"><b>' + esc(value) + "</b><span>" + esc(label) + "</span></div>";
  }

  function countMap(getter) {
    var m = {};
    state.beers.forEach(function (b) {
      var v = getter(b);
      (Array.isArray(v) ? v : [v]).forEach(function (x) { if (x) m[x] = (m[x] || 0) + 1; });
    });
    return m;
  }

  function fillSelect(sel, allLabel, getter, order, prefix) {
    var m = countMap(getter);
    sel.options[0].textContent = allLabel;
    var keys = Object.keys(m).sort();
    if (order === "desc") keys.reverse();
    keys.forEach(function (k) {
      sel.appendChild(new Option((prefix || "") + k + " (" + m[k] + ")", k));
    });
  }

  function populateFilters() {
    fillSelect(els.year, "All years", yearOf, "desc", "");
    fillSelect(els.brewery, "All breweries", function (b) { return b.brewery; }, "asc", "");
    fillSelect(els.type, "All types", function (b) { return b.type; }, "asc", "");
    fillSelect(els.tag, "All hashtags", function (b) { return b.tags || []; }, "asc", "#");

    // rating select is static markup; annotate the options with counts
    var rc = countMap(function (b) { return b.rating; });
    var names = { yeah: "\uD83D\uDC4D Yeah", eh: "\uD83D\uDE10 Eh", nah: "\uD83D\uDC4E Nah" };
    Array.prototype.forEach.call(els.rating.options, function (o) {
      if (o.value === "all") o.textContent = "All ratings";
      else o.textContent = (names[o.value] || o.value) + " (" + (rc[o.value] || 0) + ")";
    });
  }

  // -- Filter / sort / render --
  function visibleBeers() {
    var list = state.beers.filter(function (b) {
      return (state.year === "all" || yearOf(b) === state.year) &&
             (state.rating === "all" || b.rating === state.rating) &&
             (state.brewery === "all" || b.brewery === state.brewery) &&
             (state.type === "all" || b.type === state.type) &&
             (state.tag === "all" || (b.tags || []).indexOf(state.tag) >= 0);
    });
    if (state.sort === "brewery") {
      list.sort(function (a, b) { return (a.brewery || "").localeCompare(b.brewery || ""); });
    } else if (state.sort === "oldest") {
      list.sort(function (a, b) { return (a.date || "").localeCompare(b.date || ""); });
    } else {
      list.sort(function (a, b) { return (b.date || "").localeCompare(a.date || ""); });
    }
    return list;
  }

  function render() {
    var list = visibleBeers();
    els.grid.innerHTML = "";
    els.empty.hidden = list.length > 0;
    list.forEach(function (b) { els.grid.appendChild(card(b)); });
  }

  function card(b) {
    var r = RATING[b.rating] || { emoji: "", label: b.rating };
    var el = document.createElement("button");
    el.className = "card";
    el.setAttribute("aria-label", b.brewery + " " + b.name);
    var thumb = b.photos && b.photos.length
      ? '<img src="' + esc(b.photos[0].thumb) + '" alt="" loading="lazy" />'
      : '<span class="placeholder" aria-hidden="true">🍺</span>';
    var count = b.photos && b.photos.length > 1
      ? '<span class="photo-count" aria-hidden="true">▦ ' + b.photos.length + "</span>"
      : "";
    var typeLine = esc(b.type || "");
    if (b.abv) typeLine += (typeLine ? " · " : "") + esc(b.abv) + "%";
    el.innerHTML =
      '<div class="card-thumb">' + thumb + count + "</div>" +
      '<div class="card-body">' +
        '<div class="card-brewery">' + esc(b.brewery) + "</div>" +
        '<div class="card-name">' + esc(b.name) + "</div>" +
        '<div class="card-foot">' +
          '<span class="card-type">' + typeLine + "</span>" +
          '<span class="rating-pill ' + esc(b.rating) + '">' + r.emoji + " " + r.label + "</span>" +
        "</div>" +
      "</div>";
    el.addEventListener("click", function () { openLightbox(b); });
    return el;
  }

  // -- Lightbox --
  function sizeCardToPhoto(img) {
    var card = els.lightbox.querySelector(".lightbox-card");
    if (!card) return;
    var maxH = window.innerHeight * 0.72;
    var maxW = Math.min(window.innerWidth * 0.92, 900);
    var nw = img.naturalWidth || 4, nh = img.naturalHeight || 3;
    var w = nw * (maxH / nh);
    w = Math.min(w, maxW, nw);
    w = Math.max(w, 300);
    card.style.width = Math.round(w) + "px";
  }
  function openLightbox(b) {
    lb.beer = b; lb.index = 0;
    document.getElementById("lb-brewery").textContent = b.brewery;
    document.getElementById("lb-name").textContent = b.name;
    setMeta("lb-type", b.type);
    setMeta("lb-abv", b.abv ? b.abv + "%" : "");
    setMeta("lb-size", b.size);
    setMeta("lb-date", b.dateDisplay);
    document.getElementById("lb-tags").innerHTML =
      (b.tags || []).map(function (t) { return "<span>#" + esc(t) + "</span>"; }).join("");
    document.getElementById("lb-notes").textContent = b.notes || "";
    var r = RATING[b.rating] || { emoji: "", label: b.rating };
    var pill = document.getElementById("lb-rating");
    pill.className = "rating-pill " + b.rating;
    pill.textContent = r.emoji + " " + r.label;

    var multi = b.photos && b.photos.length > 1;
    document.getElementById("lb-prev").style.display = multi ? "" : "none";
    document.getElementById("lb-next").style.display = multi ? "" : "none";
    renderDots();
    showPhoto();
    els.lightbox.hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeLightbox() {
    els.lightbox.hidden = true;
    document.body.style.overflow = "";
    lb.beer = null;
  }
  function showPhoto() {
    if (!lb.beer) return;
    var photos = lb.beer.photos || [];
    var img = document.getElementById("lb-photo");
    img.onload = function () { sizeCardToPhoto(img); };
    img.src = (photos[lb.index] && photos[lb.index].full) || "";
    if (img.complete && img.naturalWidth) sizeCardToPhoto(img);
    var dots = els.lightbox.querySelectorAll(".lb-dot");
    dots.forEach(function (d, i) { d.classList.toggle("is-active", i === lb.index); });
  }
  function renderDots() {
    var wrap = document.getElementById("lb-dots");
    wrap.innerHTML = "";
    var n = (lb.beer.photos || []).length;
    if (n < 2) return;
    for (var i = 0; i < n; i++) {
      var d = document.createElement("span");
      d.className = "lb-dot";
      wrap.appendChild(d);
    }
  }
  function nav(dir) {
    if (!lb.beer) return;
    var n = (lb.beer.photos || []).length;
    lb.index = (lb.index + dir + n) % n;
    showPhoto();
  }

  // -- Events --
  els.year.addEventListener("change", function () { state.year = this.value; render(); });
  els.rating.addEventListener("change", function () { state.rating = this.value; render(); });
  els.brewery.addEventListener("change", function () { state.brewery = this.value; render(); });
  els.type.addEventListener("change", function () { state.type = this.value; render(); });
  els.tag.addEventListener("change", function () { state.tag = this.value; render(); });
  els.sort.addEventListener("change", function () { state.sort = this.value; render(); });

  document.getElementById("lb-prev").addEventListener("click", function () { nav(-1); });
  document.getElementById("lb-next").addEventListener("click", function () { nav(1); });
  els.lightbox.addEventListener("click", function (e) {
    if (e.target.hasAttribute("data-close")) closeLightbox();
  });
  document.addEventListener("keydown", function (e) {
    if (els.lightbox.hidden) return;
    if (e.key === "Escape") closeLightbox();
    else if (e.key === "ArrowLeft") nav(-1);
    else if (e.key === "ArrowRight") nav(1);
  });
})();
