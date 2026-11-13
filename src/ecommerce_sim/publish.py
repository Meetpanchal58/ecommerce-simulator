"""Publish generated data to Hugging Face Datasets and Kaggle (used by the nightly workflow).

    python -m ecommerce_sim.publish huggingface data_full full
    python -m ecommerce_sim.publish kaggle data_full full

Only the analysis tables are published (plus derived tables and the hidden ground truth);
the simulator's memory (_state) stays in the GitHub release used by `ecommerce-sim download`.
Credentials come from the environment: HF_TOKEN; KAGGLE_API_TOKEN and KAGGLE_USERNAME.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HF_REPO = os.getenv("ECOMSIM_HF_REPO", "Meet58/ecommerce-simulator")
SKIP = ["_state/*", "_state/**"]

CARD = """---
license: mit
pretty_name: E-commerce Simulator
tags: [ecommerce, retail, synthetic, recommender-systems, marketing, tabular]
---
# E-commerce Simulator data

Synthetic, day-by-day data of an Indian online fashion shop: catalogue, sale events, marketing
(plan, hourly spend, attribution, CRM with control groups), purchase orders, inventory, prices,
customers, clickstream, impressions, sales (order lifecycle), reviews and support.
Refreshed every night. Folders: `small/`, `full/`, `large/`.

Generator, schema and docs: https://github.com/Meetpanchal58/ecommerce-simulator
"""


def huggingface(data_dir: Path, size: str) -> None:
    from huggingface_hub import HfApi

    api = HfApi(token=os.environ["HF_TOKEN"])
    api.create_repo(HF_REPO, repo_type="dataset", exist_ok=True)
    api.upload_file(path_or_fileobj=CARD.encode(), path_in_repo="README.md", repo_id=HF_REPO,
                    repo_type="dataset", commit_message="Dataset card")
    api.upload_folder(folder_path=str(data_dir), path_in_repo=size, repo_id=HF_REPO, repo_type="dataset",
                      ignore_patterns=SKIP, delete_patterns=["**"],
                      commit_message=f"Nightly update ({size})")
    print(f"Published {size} to https://huggingface.co/datasets/{HF_REPO}")


def kaggle(data_dir: Path, size: str) -> None:
    user = os.environ["KAGGLE_USERNAME"]
    dataset = f"{user}/ecommerce-simulator-{size}"
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "data"
        shutil.copytree(data_dir, staging, ignore=shutil.ignore_patterns("_state"))
        (staging / "dataset-metadata.json").write_text(json.dumps({
            "title": f"E-commerce Simulator ({size})", "id": dataset, "licenses": [{"name": "other"}],
            "subtitle": "Day-by-day synthetic Indian fashion e-commerce data, refreshed nightly",
        }))
        exists = subprocess.run(["kaggle", "datasets", "status", dataset], capture_output=True).returncode == 0
        command = (["kaggle", "datasets", "version", "-m", "Nightly update"] if exists
                   else ["kaggle", "datasets", "create", "--public"])
        subprocess.run(command + ["-p", str(staging), "--dir-mode", "zip"], check=True)
    print(f"Published {size} to https://www.kaggle.com/datasets/{dataset}")


if __name__ == "__main__":
    target, folder, size_name = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    {"huggingface": huggingface, "kaggle": kaggle}[target](folder, size_name)
