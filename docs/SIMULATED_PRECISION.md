# SIMULATED precision analysis (not empirical results)

Every number below comes from simulation. Inputs taken from the real audit: score-5 counts per criterion among 128 eligible artifacts. Assumptions: how non-5 scores divide among levels 1-4 (60/25/10/5% for 4/3/2/1), and the AI error scenarios. Widths are the central 95% range of the metric across 2,000 simulated test sets. They approximate CI widths if projects were independent. Duplicate groups make the real intervals slightly wider.

| criterion | AI scenario | n test | mean MAE | MAE 95% width | exact-agreement width | mean QWK | QWK width | expected n human<=3 |
|---|---|---|---|---|---|---|---|---|
| data_visualization | strong_agreement | 45 | 0.17 | 0.22 | 0.20 | 0.82 | 0.38 | 4.1 |
| data_visualization | strong_agreement | 64 | 0.17 | 0.20 | 0.17 | 0.83 | 0.31 | 5.8 |
| data_visualization | strong_agreement | 82 | 0.17 | 0.18 | 0.16 | 0.84 | 0.26 | 7.5 |
| data_visualization | strong_agreement | 96 | 0.17 | 0.16 | 0.15 | 0.84 | 0.25 | 8.8 |
| data_visualization | moderate_agreement | 45 | 0.28 | 0.31 | 0.24 | 0.72 | 0.50 | 4.0 |
| data_visualization | moderate_agreement | 64 | 0.28 | 0.27 | 0.22 | 0.73 | 0.39 | 5.8 |
| data_visualization | moderate_agreement | 82 | 0.28 | 0.22 | 0.18 | 0.74 | 0.35 | 7.5 |
| data_visualization | moderate_agreement | 96 | 0.28 | 0.21 | 0.17 | 0.74 | 0.32 | 8.7 |
| data_visualization | weak_agreement | 45 | 0.41 | 0.36 | 0.27 | 0.60 | 0.57 | 4.1 |
| data_visualization | weak_agreement | 64 | 0.42 | 0.30 | 0.23 | 0.61 | 0.48 | 5.7 |
| data_visualization | weak_agreement | 82 | 0.41 | 0.27 | 0.20 | 0.62 | 0.42 | 7.5 |
| data_visualization | weak_agreement | 96 | 0.41 | 0.25 | 0.19 | 0.62 | 0.38 | 8.7 |
| next_steps | strong_agreement | 45 | 0.21 | 0.27 | 0.22 | 0.88 | 0.20 | 10.2 |
| next_steps | strong_agreement | 64 | 0.21 | 0.22 | 0.19 | 0.88 | 0.16 | 14.4 |
| next_steps | strong_agreement | 82 | 0.21 | 0.20 | 0.17 | 0.88 | 0.15 | 18.5 |
| next_steps | strong_agreement | 96 | 0.21 | 0.19 | 0.15 | 0.88 | 0.13 | 21.6 |
| next_steps | moderate_agreement | 45 | 0.35 | 0.33 | 0.29 | 0.80 | 0.28 | 10.1 |
| next_steps | moderate_agreement | 64 | 0.34 | 0.27 | 0.22 | 0.81 | 0.23 | 14.5 |
| next_steps | moderate_agreement | 82 | 0.35 | 0.24 | 0.21 | 0.80 | 0.20 | 18.4 |
| next_steps | moderate_agreement | 96 | 0.35 | 0.21 | 0.18 | 0.81 | 0.18 | 21.7 |
| next_steps | weak_agreement | 45 | 0.51 | 0.36 | 0.29 | 0.71 | 0.35 | 10.1 |
| next_steps | weak_agreement | 64 | 0.51 | 0.31 | 0.25 | 0.71 | 0.30 | 14.5 |
| next_steps | weak_agreement | 82 | 0.51 | 0.28 | 0.22 | 0.71 | 0.26 | 18.5 |
| next_steps | weak_agreement | 96 | 0.51 | 0.26 | 0.20 | 0.71 | 0.22 | 21.6 |

Reading guide: QWK intervals are wide and unstable under strong ceiling effects, which is why MAE, within-one agreement and severe-discrepancy rate are primary and QWK is secondary. With roughly 8-20 human scores of 3 or below per criterion in the test set, error rates on low-scoring work can be described but not estimated precisely. That limitation is reported, not hidden.