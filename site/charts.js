(function () {
  "use strict";

  function manifestUrl() {
    var cfg = window.BEER_SITE_CONFIG || {};
    return cfg.manifestUrl || "manifest.json";
  }

  function abvOf(b) {
    var m = String(b.abv == null ? "" : b.abv).match(/[\d.]+/);
    return m ? Math.round(parseFloat(m[0]) * 10) / 10 : null;
  }
  function sizeMl(s) {
    var m = String(s).match(/(\d+)\s*ml/i);
    return m ? parseInt(m[1], 10) : Infinity;   // non-ml (Pint, Handle) sort last
  }

  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function monthName(mm) { return MONTHS[parseInt(mm, 10) - 1] || mm; }

  // collapse the many free-text styles into a handful of families
  function styleFamily(b) {
    var t = (b.type || "").toLowerCase();
    if (/cider/.test(t)) return "Cider";
    if (/sour|gose|berliner|lambic|\bwild\b|brett/.test(t)) return "Sour";
    if (/stout|porter/.test(t)) return "Stout/Porter";
    if (/ipa|india pale/.test(t)) return "IPA";
    if (/pale|\bapa\b|xpa/.test(t)) return "Pale";
    if (/wheat|weiss|hefe|witbier|\bwit\b/.test(t)) return "Wheat";
    if (/pilsner|pils/.test(t)) return "Pilsner";
    if (/lager/.test(t)) return "Lager";
    if (/\bale\b|saison|tripel|dubbel|blond|bitter/.test(t)) return "Ale";
    return "Other";
  }
  var STYLE_ORDER = ["IPA", "Pale", "Lager", "Pilsner", "Wheat", "Stout/Porter", "Sour", "Ale", "Cider", "Other"];

  function abvBand(b) {
    var v = abvOf(b);
    if (v === null) return null;
    if (v >= 10) return "10+";
    var lo = Math.floor(v);
    return lo + "-" + lo + ".9";
  }
  function abvBandsPresent() {
    var present = {};
    beers.forEach(function (b) { var k = abvBand(b); if (k) present[k] = 1; });
    var out = [];
    for (var i = 0; i <= 9; i++) { var k = i + "-" + i + ".9"; if (present[k]) out.push(k); }
    if (present["10+"]) out.push("10+");
    return out;
  }

  var beers = [];

  function countBy(getter) {
    var m = {};
    beers.forEach(function (b) {
      var v = getter(b);
      (Array.isArray(v) ? v : [v]).forEach(function (x) {
        if (x === null || x === undefined || x === "") return;
        m[x] = (m[x] || 0) + 1;
      });
    });
    return m;
  }
  function sortedByCount(mapObj) {
    return Object.keys(mapObj)
      .map(function (k) { return { label: k, value: mapObj[k] }; })
      .sort(function (a, b) { return b.value - a.value || a.label.localeCompare(b.label); });
  }

  // -- per-chart data builders --
  function dataYear() {
    var yc = countBy(function (b) { return b.year || String(b.date || "").slice(0, 4); });
    var years = Object.keys(yc).map(Number).filter(function (n) { return n; });
    var out = [];
    if (years.length) {
      for (var y = Math.min.apply(null, years); y <= Math.max.apply(null, years); y++)
        out.push({ label: String(y), value: yc[y] || 0 });
    }
    return out;
  }
  function dataYearMonth() {
    var mc = countBy(function (b) {
      var d = String(b.date || ""); return d.length >= 6 ? d.slice(0, 4) + "-" + d.slice(4, 6) : null;
    });
    var keys = Object.keys(mc).sort();
    var out = [];
    if (keys.length) {
      var yy = +keys[0].slice(0, 4), mm = +keys[0].slice(5, 7);
      var ey = +keys[keys.length - 1].slice(0, 4), em = +keys[keys.length - 1].slice(5, 7);
      while (yy < ey || (yy === ey && mm <= em)) {
        var key = yy + "-" + String(mm).padStart(2, "0");
        out.push({ label: key, value: mc[key] || 0 });
        mm++; if (mm > 12) { mm = 1; yy++; }
      }
    }
    return out;
  }
  function dataAbv() {
    var ac = {};
    beers.forEach(function (b) { var v = abvOf(b); if (v !== null) ac[v.toFixed(1)] = (ac[v.toFixed(1)] || 0) + 1; });
    var maxAbv = Object.keys(ac).reduce(function (mx, k) { return Math.max(mx, parseFloat(k)); }, 0);
    var out = [];
    for (var a = 0; a <= maxAbv + 1e-9; a = Math.round((a + 0.1) * 10) / 10)
      out.push({ label: a.toFixed(1), value: ac[a.toFixed(1)] || 0 });
    return out;
  }
  function dataSize() {
    var sc = countBy(function (b) { return b.size; });
    return Object.keys(sc).map(function (k) { return { label: k, value: sc[k] }; })
      .sort(function (a, b) { return sizeMl(a.label) - sizeMl(b.label) || a.label.localeCompare(b.label); });
  }

  // -- heat-map data builders --
  function dataHeatYM() {
    var cells = {}, years = {}, max = 0;
    beers.forEach(function (b) {
      var d = String(b.date || ""); if (d.length < 6) return;
      var y = d.slice(0, 4), mo = d.slice(4, 6);
      years[y] = 1; cells[y] = cells[y] || {};
      cells[y][mo] = (cells[y][mo] || 0) + 1;
      if (cells[y][mo] > max) max = cells[y][mo];
    });
    return { rows: Object.keys(years).sort(), cols: ["01","02","03","04","05","06","07","08","09","10","11","12"], cells: cells, max: max };
  }
  function dataHeatStyleAbv() {
    var cells = {}, max = 0;
    beers.forEach(function (b) {
      var k = abvBand(b); if (!k) return;
      var f = styleFamily(b);
      cells[f] = cells[f] || {};
      cells[f][k] = (cells[f][k] || 0) + 1;
      if (cells[f][k] > max) max = cells[f][k];
    });
    return { rows: STYLE_ORDER.filter(function (f) { return cells[f]; }), cols: abvBandsPresent(), cells: cells, max: max };
  }
  function dataHeatBreweryStyle() {
    var top = sortedByCount(countBy(function (b) { return b.brewery; })).slice(0, 12).map(function (d) { return d.label; });
    var topSet = {}; top.forEach(function (b) { topSet[b] = 1; });
    var cells = {}, famUsed = {}, max = 0;
    beers.forEach(function (b) {
      if (!topSet[b.brewery]) return;
      var f = styleFamily(b); famUsed[f] = 1;
      cells[b.brewery] = cells[b.brewery] || {};
      cells[b.brewery][f] = (cells[b.brewery][f] || 0) + 1;
      if (cells[b.brewery][f] > max) max = cells[b.brewery][f];
    });
    return { rows: top, cols: STYLE_ORDER.filter(function (f) { return famUsed[f]; }), cells: cells, max: max };
  }

  // -- chart registry (single source of truth for the dropdown) --
  var CHARTS = [
    { v: "brewery", label: "Breweries", sub: "more than one; singles listed below",
      render: function () {
        var all = sortedByCount(countBy(function (b) { return b.brewery; }));
        drawHBar("#chart", all.filter(function (d) { return d.value > 1; }));
        var singles = all.filter(function (d) { return d.value === 1; })
          .map(function (d) { return d.label; }).sort(function (a, b) { return a.localeCompare(b); });
        if (singles.length) {
          var p = document.createElement("p");
          p.className = "others";
          p.textContent = "One each (" + singles.length + "): " + singles.join(", ");
          document.getElementById("chart").appendChild(p);
        }
      } },
    { v: "type", label: "Types", sub: "more than one",
      render: function () { drawHBar("#chart", sortedByCount(countBy(function (b) { return b.type; })).filter(function (d) { return d.value > 1; })); } },
    { v: "tag", label: "Hashtags", sub: "more than one",
      render: function () { drawHBar("#chart", sortedByCount(countBy(function (b) { return b.tags || []; })).filter(function (d) { return d.value > 1; })); } },
    { v: "year", label: "By year", sub: "",
      render: function () { drawVBar("#chart", dataYear(), {}); } },
    { v: "ym", label: "By month", sub: "",
      render: function () { drawVBar("#chart", dataYearMonth(), {
        rotate: false,
        showLabel: function (d) { return d.label.slice(5) === "01"; },
        fmt: function (l) { return l.slice(0, 4); } }); } },
    { v: "abv", label: "ABV", sub: "%, 0.1 steps from 0 to the strongest",
      render: function () { drawVBar("#chart", dataAbv(), {
        rotate: false,
        showLabel: function (d) { return Math.abs(parseFloat(d.label) - Math.round(parseFloat(d.label))) < 1e-9; },
        fmt: function (l) { return String(parseFloat(l)); } }); } },
    { v: "size", label: "Size", sub: "",
      render: function () { drawVBar("#chart", dataSize(), {
        rotate: false, fmt: function (l) { return String(l).replace(/ml$/i, ""); } }); } },
    { v: "heat-ym", label: "Heat map: year x month", sub: "beers logged each month",
      render: function () { drawHeatmap("#chart", dataHeatYM(), { left: 52, cellH: 26, colFmt: monthName }); } },
    { v: "heat-style-abv", label: "Heat map: style x ABV", sub: "count by style family and ABV band",
      render: function () { drawHeatmap("#chart", dataHeatStyleAbv(), { left: 108, cellH: 30, top: 26 }); } },
    { v: "heat-brewery-style", label: "Heat map: brewery x style", sub: "top 12 breweries by style family",
      render: function () { drawHeatmap("#chart", dataHeatBreweryStyle(), { left: 132, cellH: 26, rotateCols: true, top: 54 }); } }
  ];

  var picker = document.getElementById("chart-picker");
  var titleEl = document.getElementById("chart-title");
  var subEl = document.getElementById("chart-sub");

  function currentChart() {
    return CHARTS.filter(function (c) { return c.v === picker.value; })[0] || CHARTS[0];
  }
  function renderCurrent() {
    var c = currentChart();
    titleEl.textContent = c.label;
    subEl.textContent = c.sub || "";
    c.render();
    try { localStorage.setItem("beerChart", c.v); } catch (e) {}
  }

  fetch(manifestUrl(), { cache: "no-store" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (data) {
      beers = (data && data.beers) || [];
      document.getElementById("summary").textContent =
        beers.length + " beers logged" + (data.generated ? " · updated " + data.generated.slice(0, 10) : "");
      CHARTS.forEach(function (c) { picker.appendChild(new Option(c.label, c.v)); });
      var saved;
      try { saved = localStorage.getItem("beerChart"); } catch (e) {}
      if (saved && CHARTS.some(function (c) { return c.v === saved; })) picker.value = saved;
      renderCurrent();
      picker.addEventListener("change", renderCurrent);
      var t;
      window.addEventListener("resize", function () { clearTimeout(t); t = setTimeout(renderCurrent, 200); });
    })
    .catch(function (err) {
      document.getElementById("summary").textContent = "Couldn't load the beer data.";
      console.error(err);
    });

  // -- horizontal bars (brewery) --
  function drawHBar(sel, data) {
    var host = document.querySelector(sel);
    host.innerHTML = "";
    if (!data.length) return;
    var width = host.clientWidth || 900;
    var m = { top: 6, right: 40, bottom: 6, left: 150 };
    var barH = 22, gap = 6;
    var innerH = data.length * (barH + gap);
    var height = innerH + m.top + m.bottom;

    var svg = d3.select(host).append("svg").attr("viewBox", "0 0 " + width + " " + height);
    var g = svg.append("g").attr("transform", "translate(" + m.left + "," + m.top + ")");
    var innerW = width - m.left - m.right;

    var x = d3.scaleLinear().domain([0, d3.max(data, function (d) { return d.value; })]).range([0, innerW]);
    var y = d3.scaleBand().domain(data.map(function (d) { return d.label; })).range([0, innerH]).padding(0.18);

    g.selectAll("rect").data(data).enter().append("rect")
      .attr("class", "bar").attr("x", 0).attr("y", function (d) { return y(d.label); })
      .attr("width", function (d) { return x(d.value); }).attr("height", y.bandwidth())
      .append("title").text(function (d) { return d.label + ": " + d.value; });

    g.selectAll("text.lbl").data(data).enter().append("text")
      .attr("class", "bar-label").attr("x", -8).attr("y", function (d) { return y(d.label) + y.bandwidth() / 2; })
      .attr("dy", "0.35em").attr("text-anchor", "end").text(function (d) { return d.label; });

    g.selectAll("text.val").data(data).enter().append("text")
      .attr("class", "bar-label").attr("x", function (d) { return x(d.value) + 5; })
      .attr("y", function (d) { return y(d.label) + y.bandwidth() / 2; })
      .attr("dy", "0.35em").text(function (d) { return d.value; });
  }

  // -- vertical bars --
  function drawVBar(sel, data, opts) {
    opts = opts || {};
    var host = document.querySelector(sel);
    host.innerHTML = "";
    if (!data.length) return;
    var width = host.clientWidth || 900;
    var m = { top: 12, right: 8, bottom: opts.rotate ? 70 : 34, left: 34 };
    var height = 360;
    var innerW = width - m.left - m.right;
    var innerH = height - m.top - m.bottom;

    var svg = d3.select(host).append("svg").attr("viewBox", "0 0 " + width + " " + height);
    var g = svg.append("g").attr("transform", "translate(" + m.left + "," + m.top + ")");

    var x = d3.scaleBand().domain(data.map(function (d) { return d.label; })).range([0, innerW]).padding(0.15);
    var maxV = d3.max(data, function (d) { return d.value; }) || 1;
    var y = d3.scaleLinear().domain([0, maxV]).nice().range([innerH, 0]);

    g.selectAll("rect").data(data).enter().append("rect")
      .attr("class", "bar").attr("x", function (d) { return x(d.label); }).attr("y", function (d) { return y(d.value); })
      .attr("width", x.bandwidth()).attr("height", function (d) { return innerH - y(d.value); })
      .append("title").text(function (d) { return d.label + ": " + d.value; });

    g.append("g").attr("class", "axis")
      .call(d3.axisLeft(y).ticks(Math.min(maxV, 6)).tickFormat(d3.format("d")));

    var xAxis = d3.axisBottom(x).tickSize(4);
    if (opts.showLabel) xAxis.tickValues(data.filter(opts.showLabel).map(function (d) { return d.label; }));
    if (opts.fmt) xAxis.tickFormat(opts.fmt);
    var gx = g.append("g").attr("class", "axis").attr("transform", "translate(0," + innerH + ")").call(xAxis);
    if (opts.rotate) {
      gx.selectAll("text").attr("transform", "rotate(-45)").attr("text-anchor", "end").attr("dx", "-0.5em").attr("dy", "0.3em");
    }
  }

  // -- heat map --
  function drawHeatmap(sel, hm, opts) {
    opts = opts || {};
    var host = document.querySelector(sel);
    host.innerHTML = "";
    if (!hm.rows.length || !hm.cols.length) return;
    var width = host.clientWidth || 900;
    var m = { top: opts.top || 26, right: 8, bottom: 6, left: opts.left || 120 };
    var innerW = width - m.left - m.right;
    var cell = innerW / hm.cols.length;
    var cellH = opts.cellH || Math.min(cell, 34);
    var innerH = hm.rows.length * cellH;
    var height = innerH + m.top + m.bottom;

    var svg = d3.select(host).append("svg").attr("viewBox", "0 0 " + width + " " + height);
    var g = svg.append("g").attr("transform", "translate(" + m.left + "," + m.top + ")");
    var color = d3.scaleLinear().domain([0, hm.max || 1]).range(["#FBF6EC", "#854F0B"]).interpolate(d3.interpolateRgb);

    hm.rows.forEach(function (r, ri) {
      hm.cols.forEach(function (c, ci) {
        var v = (hm.cells[r] && hm.cells[r][c]) || 0;
        var rect = g.append("rect").attr("class", "hcell")
          .attr("x", ci * cell).attr("y", ri * cellH)
          .attr("width", cell - 2).attr("height", cellH - 2).attr("rx", 3)
          .attr("fill", v ? color(v) : "#FBF6EC");
        rect.append("title").text(r + " / " + (opts.colFmt ? opts.colFmt(c) : c) + ": " + v);
        if (v && cell >= 24 && cellH >= 18) {
          g.append("text").attr("class", "hval")
            .attr("x", ci * cell + (cell - 2) / 2).attr("y", ri * cellH + cellH / 2).attr("dy", "0.35em")
            .attr("text-anchor", "middle").attr("fill", v > hm.max * 0.55 ? "#fff" : "var(--ink)")
            .text(v);
        }
      });
      g.append("text").attr("class", "hlabel")
        .attr("x", -8).attr("y", ri * cellH + cellH / 2).attr("dy", "0.35em")
        .attr("text-anchor", "end").text(r);
    });

    hm.cols.forEach(function (c, ci) {
      var cx = ci * cell + (cell - 2) / 2;
      var t = g.append("text").attr("class", "hlabel").attr("y", -8).text(opts.colFmt ? opts.colFmt(c) : c);
      if (opts.rotateCols) t.attr("x", 0).attr("text-anchor", "end").attr("transform", "translate(" + cx + ",0) rotate(-35)");
      else t.attr("x", cx).attr("text-anchor", "middle");
    });
  }
})();
