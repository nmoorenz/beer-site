(function () {
  "use strict";

  var RATING = {
    yeah: { emoji: "👍", label: "Yeah" },
    eh:   { emoji: "😐", label: "Eh" },
    nah:  { emoji: "👎", label: "Nah" },
  };

  var state = { beers: [], rating: "all", brewery: "all", sort: "newest", tags: [] };
  var lb = { beer: null, index: 0 };

  var els = {
    grid:     document.getElementById("grid"),
    empty:    document.getElementById("empty"),
    loading:  document.getElementById("loading"),
    stats:    document.getElementById("stats"),
    controls: document.getElementById("controls"),
    brewery:  document.getElementById("brewery-filter"),
    sort:     document.getElementById("sort-order"),
    tagBar:   document.getElementById("tag-bar"),
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

  function tagString(b) {
    return (b.tags && b.tags.length)
      ? b.tags.map(function (t) { return "#" + t; }).join(" ")
      : (b.type || "");
  }

  // -- Load --
  fetch(manifestUrl(), { cache: "no-store" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (data) {
      state.beers = (data && data.beers) || [];
      els.loading.hidden = true;
      if (!state.beers.length) { els.empty.hidden = false; renderStats(data); return; }
      els.controls.hidden = false;
      populateBreweries();
      renderTagBar();
      renderStats(data);
      render();
    })
    .catch(function (err) {
      els.loading.textContent = "Couldn't load the beer list. Try again later.";
      console.error("manifest load failed:", err);
    });

  function renderStats(data) {
    var c = (data && data.counts) || countLocal();
    els.stats.innerHTML =
      stat(c.total, "logged") +
      stat(c.yeah + " 👍", "yeah") +
      stat(c.eh + " 😐", "eh") +
      stat(c.nah + " 👎", "nah");
  }
  function countLocal() {
    var c = { total: state.beers.length, yeah: 0, eh: 0, nah: 0 };
    state.beers.forEach(function (b) { if (c[b.rating] != null) c[b.rating]++; });
    return c;
  }
  function stat(value, label) {
    return '<div class="stat"><b>' + esc(value) + "</b><span>" + esc(label) + "</span></div>";
  }

  function populateBreweries() {
    var names = {};
    state.beers.forEach(function (b) { if (b.brewery) names[b.brewery] = true; });
    Object.keys(names).sort().forEach(function (n) {
      var o = document.createElement("option");
      o.value = n; o.textContent = n;
      els.brewery.appendChild(o);
    });
  }

  function renderTagBar() {
    var set = {};
    state.beers.forEach(function (b) {
      (b.tags || []).forEach(function (t) { set[t] = true; });
    });
    var tags = Object.keys(set).sort();
    if (!tags.length) return;
    els.tagBar.hidden = false;
    els.tagBar.innerHTML = tags.map(function (t) {
      return '<button class="tag" data-tag="' + esc(t) + '">#' + esc(t) + "</button>";
    }).join("");
  }

  // -- Filter / sort / render --
  function visibleBeers() {
    var hasTags = state.tags.length > 0;
    var list = state.beers.filter(function (b) {
      var okRating  = state.rating === "all" || b.rating === state.rating;
      var okBrewery = state.brewery === "all" || b.brewery === state.brewery;
      var okTags = !hasTags || (b.tags || []).some(function (t) {
        return state.tags.indexOf(t) >= 0;
      });
      return okRating && okBrewery && okTags;
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
    var typeLine = esc(tagString(b));
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
  function openLightbox(b) {
    lb.beer = b; lb.index = 0;
    document.getElementById("lb-brewery").textContent = b.brewery;
    document.getElementById("lb-name").textContent = b.name;
    setMeta("lb-type", tagString(b));
    setMeta("lb-abv", b.abv ? b.abv + "%" : "");
    setMeta("lb-size", b.size);
    setMeta("lb-date", b.dateDisplay);
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
    document.getElementById("lb-photo").src = (photos[lb.index] && photos[lb.index].full) || "";
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
  document.getElementById("rating-filters").addEventListener("click", function (e) {
    var btn = e.target.closest(".chip"); if (!btn) return;
    state.rating = btn.dataset.rating;
    this.querySelectorAll(".chip").forEach(function (c) { c.classList.remove("is-active"); });
    btn.classList.add("is-active");
    render();
  });
  els.tagBar.addEventListener("click", function (e) {
    var btn = e.target.closest(".tag"); if (!btn) return;
    var t = btn.dataset.tag;
    var i = state.tags.indexOf(t);
    if (i >= 0) state.tags.splice(i, 1); else state.tags.push(t);
    btn.classList.toggle("is-active");
    render();
  });
  els.brewery.addEventListener("change", function () { state.brewery = this.value; render(); });
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
