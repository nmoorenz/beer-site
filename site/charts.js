(function () {
  "use strict";

  var MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

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

  var beers = [];

  fetch(manifestUrl(), { cache: "no-store" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (data) {
      beers = (data && data.beers) || [];
      document.getElementById("summary").textContent =
        beers.length + " beers logged" + (data.generated ? " · updated " + data.generated.slice(0, 10) : "");
      renderAll();
      var t;
      window.addEventListener("resize", function () { clearTimeout(t); t = setTimeout(renderAll, 200); });
    })
    .catch(function (err) {
      document.getElementById("summary").textContent = "Couldn't load the beer data.";
      console.error(err);
    });

  // -- counting --
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

  function renderAll() {
    drawHBar("#c-brewery", sortedByCount(countBy(function (b) { return b.brewery; })));

    drawVBar("#c-type", sortedByCount(countBy(function (b) { return b.type; })), { rotate: true });
    drawVBar("#c-tag", sortedByCount(countBy(function (b) { return b.tags || []; })), { rotate: true });

    // year: ordinal, fill gaps
    var yc = countBy(function (b) { return b.year || String(b.date || "").slice(0, 4); });
    var years = Object.keys(yc).map(Number).filter(function (n) { return n; });
    var yData = [];
    if (years.length) {
      for (var y = Math.min.apply(null, years); y <= Math.max.apply(null, years); y++)
        yData.push({ label: String(y), value: yc[y] || 0 });
    }
    drawVBar("#c-year", yData, {});

    // year-month: ordinal, fill every month in range
    var mc = countBy(function (b) {
      var d = String(b.date || ""); return d.length >= 6 ? d.slice(0, 4) + "-" + d.slice(4, 6) : null;
    });
    var keys = Object.keys(mc).sort();
    var ymData = [];
    if (keys.length) {
      var start = keys[0], end = keys[keys.length - 1];
      var yy = +start.slice(0, 4), mm = +start.slice(5, 7);
      var ey = +end.slice(0, 4), em = +end.slice(5, 7);
      while (yy < ey || (yy === ey && mm <= em)) {
        var key = yy + "-" + String(mm).padStart(2, "0");
        ymData.push({ label: key, value: mc[key] || 0 });
        mm++; if (mm > 12) { mm = 1; yy++; }
      }
    }
    drawVBar("#c-ym", ymData, {
      rotate: true,
      showLabel: function (d) { return d.label.slice(5) === "01"; },  // year starts
      fmt: function (l) { return l.slice(5) === "01" ? l.slice(0, 4) : l; }
    });

    // abv: ordinal 0.0 .. max in 0.1 steps
    var ac = {};
    beers.forEach(function (b) { var v = abvOf(b); if (v !== null) ac[v.toFixed(1)] = (ac[v.toFixed(1)] || 0) + 1; });
    var maxAbv = Object.keys(ac).reduce(function (mx, k) { return Math.max(mx, parseFloat(k)); }, 0);
    var aData = [];
    for (var a = 0; a <= maxAbv + 1e-9; a = Math.round((a + 0.1) * 10) / 10)
      aData.push({ label: a.toFixed(1), value: ac[a.toFixed(1)] || 0 });
    drawVBar("#c-abv", aData, {
      rotate: true,
      fmt: function (l) { return String(parseFloat(l)); }   // 0.0 -> "0", 0.1 -> "0.1", 5.0 -> "5"
    });

    // size: categorical, ordered by volume (ml) ascending, non-ml last
    var sc = countBy(function (b) { return b.size; });
    var sData = Object.keys(sc).map(function (k) { return { label: k, value: sc[k] }; })
      .sort(function (a, b) { return sizeMl(a.label) - sizeMl(b.label) || a.label.localeCompare(b.label); });
    drawVBar("#c-size", sData, { rotate: true });
  }

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
    var height = 300;
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

    // y axis (integer ticks)
    var yTicks = Math.min(maxV, 6);
    g.append("g").attr("class", "axis")
      .call(d3.axisLeft(y).ticks(yTicks).tickFormat(d3.format("d")));

    // x axis with optional label thinning + formatting
    var xAxis = d3.axisBottom(x).tickSize(4);
    if (opts.showLabel) {
      xAxis.tickValues(data.filter(opts.showLabel).map(function (d) { return d.label; }));
    }
    if (opts.fmt) xAxis.tickFormat(opts.fmt);
    var gx = g.append("g").attr("class", "axis").attr("transform", "translate(0," + innerH + ")").call(xAxis);
    if (opts.rotate) {
      gx.selectAll("text").attr("transform", "rotate(-45)").attr("text-anchor", "end").attr("dx", "-0.5em").attr("dy", "0.3em");
    }
  }
})();
