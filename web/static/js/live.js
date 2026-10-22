/* Live / pending competition: fetch estimated rating changes, show the cube while waiting,
 * refresh while the competition is running. */
(function () {
  "use strict";
  var out = document.getElementById("live-out");
  if (!out) return;
  var comp = out.dataset.comp, sort = "gain", data = null, timer = null;

  function load(first) {
    var ld = first ? Kelso.loader(out, "Fetching live results from the WCA…") : null;
    fetch("/api/live/" + encodeURIComponent(comp)).then(function (r) { return r.json().then(function (j) { return [r.status, j]; }); })
      .then(function (res) {
        if (ld) ld.stop();
        var status = res[0], j = res[1];
        if (j.official) { location.reload(); return; }
        if (status !== 200) { out.innerHTML = '<p class="muted">' + Kelso.esc(j.error || "Could not load this competition.") + "</p>"; return; }
        data = j; render();
        if (j.ongoing) { clearTimeout(timer); timer = setTimeout(function () { load(false); }, j.ttl * 1000 + 2000); }
      })
      .catch(function () { if (ld) ld.stop(); out.innerHTML = '<p class="muted">Could not load this competition.</p>'; });
  }

  function gain(r) { return r.after != null ? r.after - (r.before || 0) : 0; }

  function render() {
    document.getElementById("comp-name").textContent = data.name;
    document.title = data.name + " · Kelso estimates";
    var info = data.info;
    document.getElementById("state").textContent = data.ongoing ? "live now" : "ended, awaiting the official export";
    document.getElementById("comp-meta").innerHTML = (info ? Kelso.flag(info.country_iso2) + " " + Kelso.esc(info.city || "") + " · " + info.start_date + (info.end_date !== info.start_date ? " – " + info.end_date : "") + " · " : "") +
      (data.ongoing ? '<span class="chip live">live</span> ' : "") + '<span class="muted">updated ' + new Date(data.fetched_at).toLocaleTimeString() + "</span>";
    var rows = data.rows.slice();
    rows.sort(sort === "after" ? function (a, b) { return (b.after || -1) - (a.after || -1); }
      : sort === "name" ? function (a, b) { return a.name.localeCompare(b.name); }
      : function (a, b) { return gain(b) - gain(a) || a.name.localeCompare(b.name); });
    var up = rows.filter(function (r) { return r.before != null && gain(r) >= 0.5; }).length;
    var first = rows.filter(function (r) { return r.before == null && r.after != null; }).length;
    var pbs = rows.reduce(function (s, r) { return s + r.changes.length; }, 0);
    var html = '<div class="summary">' +
      card("Competitors with results", rows.length) + card("Rating goes up", up) + card("First rating", first) + card("Personal bests", pbs) + "</div>" +
      '<div class="page-head"><h2 style="margin:0">Estimated rating changes</h2><nav class="sorts">' +
      ["gain", "after", "name"].map(function (s) { return '<a href="#" data-sort="' + s + '" class="' + (s === sort ? "on" : "") + '">' + { gain: "Biggest gain", after: "Rating", name: "Name" }[s] + "</a>"; }).join("") +
      '</nav></div><div class="table-wrap"><table class="t"><thead><tr><th>Name</th><th class="num">Before</th><th class="num">After (est.)</th><th class="num">Change</th><th class="num hide-sm">World rank</th><th class="hide-sm">Improved events</th></tr></thead><tbody>';
    rows.forEach(function (r) {
      var g = gain(r), ch = r.before == null ? (r.after != null ? '<span class="chip">first</span>' : "") : g >= 0.5 ? '<span class="up">' + Kelso.fmtDelta(g) + "</span>" : '<span class="muted">±0</span>';
      var name = r.wca_id ? '<a href="/persons/' + r.wca_id + '">' + Kelso.esc(r.name) + "</a>" : Kelso.esc(r.name) + ' <span class="chip">newcomer</span>';
      html += "<tr><td class=\"who\">" + Kelso.flag(r.iso2) + name + '</td><td class="num">' + (r.before != null ? Math.round(r.before) : "") +
        '</td><td class="num rating">' + (r.after != null ? Math.round(r.after) : "") + '</td><td class="num">' + ch +
        '</td><td class="num hide-sm">' + (r.rank_after || "") + '</td><td class="hide-sm"><span class="improved">' +
        r.changes.map(function (c) {
          var d = c.old_rating != null ? ' <span class="up small">' + Kelso.fmtDelta(c.rating - c.old_rating) + "</span>" : ' <span class="muted small">new</span>';
          return '<span class="imp" title="' + Kelso.SHORT[c.event] + ": " + Kelso.fmtResult(c.event, c.raw) + (c.old_raw ? " (PB was " + Kelso.fmtResult(c.event, c.old_raw) + ")" : "") + '">' +
            Kelso.icon(c.event) + "<span>" + Math.round(c.rating) + d + "</span></span>";
        }).join("") + "</span></td></tr>";
    });
    if (!rows.length) html += '<tr><td colspan="6" class="muted">No results entered yet.</td></tr>';
    out.innerHTML = html + "</tbody></table></div>";
    out.querySelectorAll("[data-sort]").forEach(function (a) {
      a.addEventListener("click", function (ev) { ev.preventDefault(); sort = a.dataset.sort; render(); });
    });
  }
  function card(k, v) { return '<div class="card"><div class="k">' + k + '</div><div class="v">' + v + "</div></div>"; }
  load(true);
})();
