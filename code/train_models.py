"""Compare training-only models on validation; never score final test rows."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import warnings

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, brier_score_loss, f1_score, log_loss,
                             precision_score, recall_score, roc_auc_score)
from sklearn.preprocessing import StandardScaler

from make_features import NUMERIC_FEATURES

SEED = 42
THRESHOLD = 0.5


class Features:
    """Train-fitted median imputation, missing flags, scaling, and tag vocabulary."""

    def __init__(self, numeric=None):
        self.numeric = list(NUMERIC_FEATURES if numeric is None else numeric)
        self.imputer = SimpleImputer(strategy="median", add_indicator=True,
                                     keep_empty_features=True)
        self.scaler = StandardScaler()

    def numbers(self, rows):
        return np.array([[np.nan if r[k] is None else r[k] for k in self.numeric]
                         for r in rows], dtype=float)

    def fit(self, rows):
        self.tags = sorted({tag for r in rows for tag in r["problem_tags"]})
        self.scaler.fit(self.imputer.fit_transform(self.numbers(rows)))
        return self

    def transform(self, rows):
        numbers = self.scaler.transform(self.imputer.transform(self.numbers(rows)))
        tags = np.array([[int(t in r["problem_tags"]) for t in self.tags] for r in rows])
        return np.column_stack([numbers, tags])


def development_rows(rows):
    # Filter before reading targets or building any learned transformations.
    train = [r for r in rows if r["split"] == "train"]
    validation = [r for r in rows if r["split"] == "validation"]
    if not train or not validation:
        raise ValueError("Training and validation rows are required")
    if max(r["timestamp"] for r in train) >= min(r["timestamp"] for r in validation):
        raise ValueError("Training must precede validation")
    for part in (train, validation):
        if {r["target"] for r in part} != {0, 1}:
            raise ValueError("Each development split must contain both classes")
    counts = Counter(r["analysis_id"] for r in train)
    expected = [len(train) / (len(counts) * counts[r["analysis_id"]]) for r in train]
    if not np.allclose([r["training_weight"] for r in train], expected):
        raise ValueError("Training weights must give each user equal total weight")
    return train, validation


def metrics(y, probability):
    y, probability = np.asarray(y), np.asarray(probability)
    predicted = probability >= THRESHOLD
    return {
        "log_loss": float(log_loss(y, probability, labels=[0, 1])),
        "brier": float(brier_score_loss(y, probability)),
        "roc_auc": float(roc_auc_score(y, probability)) if len(set(y)) == 2 else None,
        "accuracy": float(accuracy_score(y, predicted)),
        "precision": float(precision_score(y, predicted, zero_division=0)),
        "recall": float(recall_score(y, predicted, zero_division=0)),
        "f1": float(f1_score(y, predicted, zero_division=0)),
    }


def evaluate(rows, probability):
    y = np.array([r["target"] for r in rows])
    ids = np.array([r["analysis_id"] for r in rows])
    per_user = [metrics(y[ids == uid], probability[ids == uid]) for uid in sorted(set(ids))]
    average = {k: float(np.mean([m[k] for m in per_user if m[k] is not None]))
               if any(m[k] is not None for m in per_user) else None for k in per_user[0]}
    return {"submission": metrics(y, probability), "user_average": average,
            "rows": len(rows), "users": len(per_user),
            "users_with_auc": sum(m["roc_auc"] is not None for m in per_user)}


def candidates():
    for c in (0.1, 1.0):
        yield f"Logistic Regression C={c}", LogisticRegression(C=c, max_iter=3000, random_state=SEED)
    for depth in (8, 16):
        yield f"Random Forest depth={depth}", RandomForestClassifier(
            n_estimators=200, max_depth=depth, min_samples_leaf=10, n_jobs=2, random_state=SEED)
    for depth in (2, 3):
        yield f"Gradient Boosting depth={depth}", GradientBoostingClassifier(
            n_estimators=100, learning_rate=0.05, max_depth=depth, min_samples_leaf=20,
            random_state=SEED)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(folder, report_folder):
    gates = json.loads((folder / "coverage_gates.json").read_text())
    if not gates["all_passed"] or not all(gates["gates"].values()):
        raise ValueError("Resolve dataset coverage gates before training")
    schema = json.loads((folder / "schema.json").read_text())
    if schema["numeric_features"] != NUMERIC_FEATURES:
        raise ValueError("Unexpected feature schema")
    rows = json.loads((folder / "features.json").read_text())
    train, validation = development_rows(rows)
    del rows
    features = Features().fit(train)
    x_train, x_validation = features.transform(train), features.transform(validation)
    y_train = np.array([r["target"] for r in train])
    weights = np.array([r["training_weight"] for r in train])
    baseline = float(np.average(y_train, weights=weights))
    results = [{"name": "Acceptance-rate baseline", "parameters": {"probability": baseline},
                **evaluate(validation, np.full(len(validation), baseline))}]
    models = {}
    warnings.filterwarnings("error", category=ConvergenceWarning)
    for name, model in candidates():
        print(f"Training {name}", flush=True)
        model.fit(x_train, y_train, sample_weight=weights)
        probability = model.predict_proba(x_validation)[:, 1]
        results.append({"name": name, "parameters": model.get_params(), **evaluate(validation, probability)})
        models[name] = model
    best = min(results, key=lambda r: r["user_average"]["log_loss"])
    output = {"selection_metric": "user_average.log_loss", "threshold": THRESHOLD,
              "seed": SEED, "test_sets_scored": False, "selected": best["name"],
              "validation_rows": len(validation), "validation_users": len({r["analysis_id"] for r in validation}),
              "training_rows": len(train), "training_users": len({r['analysis_id'] for r in train}),
              "versions": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                           "numpy": np.__version__, "joblib": joblib.__version__},
              "sha256": {name: digest(folder / name) for name in
                         ("features.json", "schema.json", "splits.json", "manifest.json", "coverage_gates.json")},
              "code_sha256": digest(Path(__file__)), "numeric_features": features.numeric,
              "tag_vocabulary": features.tags, "results": results}
    report_folder.mkdir(parents=True, exist_ok=True)
    (report_folder / "model_results.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    # Local artifact only; reload only trusted files. No fitting on validation.
    joblib.dump({"numeric_features": features.numeric, "tags": features.tags,
                 "imputer": features.imputer, "scaler": features.scaler,
                 "models": models, "baseline": baseline,
                 "selected": best["name"], "metadata": output}, folder / "models.joblib")
    write_report(output, report_folder / "model_results.md")
    print(f"Selected by validation user-averaged log loss: {best['name']}", flush=True)
    return output


def write_report(output, path):
    lines = ["# Model validation results", "", "## Scope and selection", "",
             f"Fitted on {output['training_rows']:,} rows from {output['training_users']} users; evaluated on {output['validation_rows']:,} validation rows from {output['validation_users']} users.",
             "Final temporal and unseen-user tests have not been scored. These are development results, not evidence of generalization.", "",
             "Selection uses the lowest user-averaged validation log loss (lower is better), including the baseline as a candidate. Each user has equal influence on this metric. The small search has two settings per model; all settings are shown below. Classification uses a fixed threshold of 0.5, with acceptance as the positive class.", "",
             f"Selected candidate: **{output['selected']}**. This is provisional until the planned development sensitivity checks are complete.", "",
             "## Preprocessing and model choices", "",
             "Only training rows fit numeric medians, missing-value indicators, standard scaling, and the topic-tag vocabulary. Unknown tags are ignored; an entirely missing training column is filled with zero. Metadata and identifiers are excluded by an explicit feature allowlist. Scaling helps Logistic Regression; trees receive the same inputs for consistency and do not require scaling. Preprocessing summaries are unweighted; training loss uses the frozen equal-user sample weights for every model and the baseline.", "",
             "The baseline predicts the weighted training acceptance rate for every row. Logistic Regression models linear log odds with L2 regularization. Random Forest averages nonlinear trees; depth and minimum leaf size limit overfitting. Gradient Boosting adds shallow trees sequentially to optimize log loss. Seed 42 is used throughout. Exact settings, versions, and data/code hashes are in `model_results.json`; trained objects stay in ignored `data/processed/models.joblib`.", ""]
    for key, title in (("submission", "Submission-level metrics"), ("user_average", "User-averaged metrics")):
        lines += [f"## {title}", "", "| Model | Log loss | Brier | ROC-AUC | Precision | Recall | F1 | Accuracy |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for r in output["results"]:
            values = [r[key][k] for k in ("log_loss", "brier", "roc_auc", "precision", "recall", "f1", "accuracy")]
            lines.append("| " + r["name"] + " | " + " | ".join("N/A" if v is None else f"{v:.4f}" for v in values) + " |")
        lines += [""]
    lines += ["## Interpretation and remaining work", "",
              f"The selected candidate has user-averaged log loss {min(r['user_average']['log_loss'] for r in output['results']):.4f}, compared with {output['results'][0]['user_average']['log_loss']:.4f} for the constant baseline. This supports further development, but does not establish that the best validation candidate will win on future or unseen users.", "",
              "Log loss penalizes confident wrong probabilities; Brier measures squared probability error (both lower is better). ROC-AUC measures ranking rather than calibration. User metrics are computed per user then averaged; ROC-AUC excludes users with only one outcome. Undefined precision/recall/F1 are set to zero, so sparse-user classification metrics need care.", "",
              f"User-averaged ROC-AUC includes {output['results'][0]['users_with_auc']} of {output['validation_users']} validation users. Repeated submissions from each user are correlated; row counts are not independent sample counts. Model selection on this validation set makes these scores optimistic as final estimates.", "",
              "Still pending: no-difficulty and outcome-lag sensitivity checks, calibration plots, user-level uncertainty estimates, subgroup and representative-error analysis, and final temporal/unseen-user evaluation after settings are frozen. Snapshot tags/difficulty, verdict timing, self-selected problems, sparse cold-start evidence, and the absence of currently unrated training users limit claims. Predicting acceptance does not prove a DSA weakness or improved learning.", "",
              "## Reproduce", "", "```bash", "python3 -m pip install -r requirements.txt",
              "python3 code/train_models.py", "python3 -m unittest discover -s tests -v", "```", "",
              "Restore the archive and generate features first using the README commands. This script scores only training/validation development inputs and saves validation aggregates; it contains no final-test scoring path."]
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/processed"))
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    args = parser.parse_args()
    run(args.data, args.reports)
