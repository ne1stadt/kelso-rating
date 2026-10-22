# Code for "A Cross-Event Rating for Speedcubing on the Elo Scale"

Data: WCA results export, format version 2.0.2, 14 October 2026, read from the static JSON mirror
github.com/robiningelbrecht/wca-rest-api (branch v1), placed in `data/wca/`.
"This information is based on competition results owned and maintained by the World Cube Association,
published at https://www.worldcubeassociation.org/export/results as of 14 October 2026."

Python 3.11, numpy, pandas, scipy, pyarrow, pycountry-convert. Run from this folder, in order:

| Step | Script | Output | Paper |
| --- | --- | --- | --- |
| 1 | persons.py | persons.csv (id, name, country) | Section 2 |
| 2 | parse_rounds.py | rounds.parquet (one row per competitor, competition, event, round) | Section 2 |
| 3 | build_W.py | W_main.parquet (personal bests; BLD by single) | Section 2 |
| 4 | rebuild_main.py | R_main.parquet, O_main.parquet (event and overall ratings) | Sections 3, 5 |
| 5 | paper_numbers.py | paper_numbers.json (Table 1, profiles, distribution, ceilings, improvement, breadth, Clock) | 3.2, 5, 6 |
| 6 | h2h2.py | h2h2.json (pairwise and Plackett–Luce fits, per-event scales with clustered CIs, Figure 4) | 4.1 |
| 7 | validate_k.py, kse.py | kfit.json, kse.json (Table 4 and its SEs) | 4.2 |
| 8 | predcomp.py | predcomp.json (Table 5, prediction column) | 4.2 |
| 9 | agree.py | agree.json (Table 5, agreement columns; theoretical maximum) | 4.2, 5.4 |
| 10 | rev3_misc.py, then sens2.py | rev3_misc.json (correlations, floor, incentives, two-parameter rule, effective events), sens2.json (Table 6) | 3.2, 4.2, 4.3, 7.3, 7.5 |
| 10b | factor.py | factor.json (latent-trait comparison) | 4.4 |
| 11 | boot2.py SEED B OUT; boot_perf.py; table8.py | conversion and performance bootstrap replicates, Table 8 | 5.2 |
| 14 | bench.py | bench.json (Table 11 timings) | 7.4 |
| 12 | exposure_drift.py | exposure_drift.json (Table 10, Figure 7) | 6.3, 7.2 |
| 13 | fto.py | fto.csv (Figure 8) | Appendix B |

`core.py` holds the rating: kernel-continuized distributions (class KCDF), linking and event ratings (class Rater),
and the log-sum-exp aggregate (lse). The bootstrap in the paper is two runs of 200 replicates
(`boot2.py 101 200 bootA.npy`, `boot2.py 202 200 bootB.npy`).
