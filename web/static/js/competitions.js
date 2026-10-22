/* Running and recently ended competitions come from the WCA API; they load after the page so
 * the official list never waits for an upstream service. */
(function () {
  "use strict";
  var host = document.getElementById("live-lists");
  if (!host) return;
  var ld = Kelso.loader(host, "Checking the WCA for running competitions…");
  function card(c, chip) {
    var dates = c.start_date + (c.end_date !== c.start_date ? " – " + c.end_date.slice(5) : "");
    return '<a class="card comp-card" href="/competitions/' + encodeURIComponent(c.id) + '"><div class="n">' + Kelso.flag(c.country_iso2) + " " + Kelso.esc(c.name) +
      '</div><div class="m"><span>' + Kelso.esc(c.city || "") + "</span><span>" + dates + "</span>" + chip + "</div></a>";
  }
  fetch("/api/competitions/live").then(function (r) { return r.json(); }).then(function (d) {
    ld.stop();
    if (d.error) { host.innerHTML = '<p class="muted small">Live competitions are unavailable right now (the WCA API did not respond).</p>'; return; }
    var html = "";
    if (d.ongoing.length) {
      html += '<h2><span class="chip live">live</span> Happening now</h2><div class="comp-grid">' +
        d.ongoing.map(function (c) { return card(c, '<span class="chip est">estimates</span>'); }).join("") + "</div>";
    }
    if (d.pending.length) {
      html += "<h2>Ended, awaiting official export</h2><div class=\"comp-grid\">" + d.pending.slice(0, 60).map(function (c) {
        return card(c, c.results_posted_at ? '<span class="chip">results posted</span>' : '<span class="chip">results pending</span>');
      }).join("") + "</div>" + (d.pending.length > 60 ? '<p class="muted small">and ' + (d.pending.length - 60) + " more.</p>" : "");
    }
    host.innerHTML = html;
  }).catch(function () { ld.stop(); host.innerHTML = ""; });
})();
