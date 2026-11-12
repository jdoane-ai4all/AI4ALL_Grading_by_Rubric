"""Synthetic fixtures only. No real student work or labels are used in tests."""
import csv
import random

import pytest

from rubric_scoring.data import col_index


@pytest.fixture
def config():
    from rubric_scoring.data import load_config
    return load_config("config/study_config.json")


@pytest.fixture
def synthetic_labels_csv(tmp_path, config):
    """Mimics the Data-tab layout by column letter with fake projects."""
    rng = random.Random(0)
    cols = config["label_source"]["columns"]
    width = col_index("AK") + 1
    rows = [["h"] * width]
    for i in range(1, 141):
        r = [""] * width
        r[col_index(cols["project_id"])] = f"project-{i:03d}"
        r[col_index(cols["cohort"])] = rng.choice(["SU25", "FA25", "SU26"])
        # groups 1..135: projects 136-140 duplicate projects 1-5
        r[col_index(cols["duplicate_group"])] = f"g{(i - 1) % 135 + 1:03d}"
        r[col_index("AJ")] = "SHOULD-NEVER-BE-READ"
        if i % 10 != 0:  # 10% unlabeled
            sc = [rng.choices([5, 4, 3, 2, 1], [60, 22, 10, 5, 3])[0] for _ in range(6)]
            for k, v in zip(["project_description", "data_visualization", "algorithm",
                             "essential_question", "next_steps", "citations"], sc):
                r[col_index(cols[k])] = str(v)
            r[col_index(cols["total"])] = str(sum(sc))
        rows.append(r)
    p = tmp_path / "data_tab.csv"
    with open(p, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    return p
