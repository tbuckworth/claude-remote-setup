#!/usr/bin/env python3
"""Extract experiment results from .eval files for email summary.

.eval files are ZIP archives. We read header.json (always small) which
contains aggregated scores, model info, and timing stats. This avoids
loading reductions.json which can be 400MB+.

Usage: python3 extract-eval-results.py <results_dir>
Output: JSON to stdout
"""
import json
import os
import sys
import zipfile
from pathlib import Path


def extract_from_eval(eval_path):
    """Extract key data from a single .eval file via header.json."""
    result = {"file": eval_path.name, "name": eval_path.stem}

    try:
        with zipfile.ZipFile(eval_path) as zf:
            if "header.json" not in zf.namelist():
                result["error"] = "no header.json in archive"
                result["size_mb"] = round(eval_path.stat().st_size / (1024 * 1024), 1)
                return result

            with zf.open("header.json") as f:
                header = json.load(f)

            # status, results, stats are TOP-LEVEL in header.json
            # eval info (task, model, metadata) is under "eval"
            ev = header.get("eval", {})
            result["status"] = header.get("status", "unknown")
            result["task"] = ev.get("task", "unknown")
            result["task_id"] = ev.get("task_id", "")
            result["created"] = ev.get("created", "")
            result["run_id"] = ev.get("run_id", "")

            # Model info
            model_roles = ev.get("model_roles", {})
            if "untrusted" in model_roles:
                result["model"] = model_roles["untrusted"].get("model", "unknown")
            elif model_roles:
                first = next(iter(model_roles.values()))
                result["model"] = first.get("model", "unknown")

            # Metadata — main_task lives in eval.metadata.setting
            metadata = ev.get("metadata", {})
            setting = metadata.get("setting", {})
            if isinstance(setting, dict):
                result["main_task"] = setting.get("main_task", "")
                result["side_task"] = setting.get("side_task", "")
                result["base_model"] = setting.get("base_model", "")
            else:
                result["main_task"] = ""
                result["side_task"] = ""

            # Mode (honest/attack) from metadata.mode or task name
            result["mode"] = metadata.get("mode", "")

            # Scores from top-level results
            results_obj = header.get("results", {})
            result["total_samples"] = results_obj.get("total_samples", 0)
            result["completed_samples"] = results_obj.get("completed_samples", 0)

            scores = {}
            for score in results_obj.get("scores", []):
                scorer_name = score.get("scorer", "unknown")
                # Extract primary metric value from metrics dict
                metrics = score.get("metrics", {})
                primary_value = None
                for metric_name, metric_obj in metrics.items():
                    if isinstance(metric_obj, dict):
                        primary_value = metric_obj.get("value")
                        break
                scores[scorer_name] = {
                    "value": primary_value,
                    "metrics": {k: v.get("value") if isinstance(v, dict) else v
                                for k, v in metrics.items()},
                }
            result["scores"] = scores

            # Stats from top-level
            stats = header.get("stats", {})
            result["started_at"] = stats.get("started_at", "")
            result["completed_at"] = stats.get("completed_at", "")
            total_tokens = 0
            for usage in stats.get("model_usage", {}).values():
                if isinstance(usage, dict):
                    total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            result["total_tokens"] = total_tokens

    except zipfile.BadZipFile:
        result["error"] = "corrupt ZIP file"
    except json.JSONDecodeError as e:
        result["error"] = f"invalid JSON: {e}"
    except Exception as e:
        result["error"] = str(e)

    result["size_mb"] = round(eval_path.stat().st_size / (1024 * 1024), 1)
    return result


def extract_results(results_dir):
    """Extract results from all .eval files in a directory (recursive)."""
    results_path = Path(results_dir).expanduser()
    eval_files = sorted(results_path.rglob("*.eval"))

    experiments = [extract_from_eval(ef) for ef in eval_files]

    successful = sum(1 for e in experiments if e.get("status") == "success")
    failed = sum(1 for e in experiments if e.get("status") == "error")
    errored = sum(1 for e in experiments if "error" in e)

    return {
        "results_dir": str(results_path),
        "total_eval_files": len(eval_files),
        "successful": successful,
        "failed": failed,
        "parse_errors": errored,
        "experiments": experiments,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: extract-eval-results.py <results_dir>"}))
        sys.exit(1)

    d = os.path.expanduser(sys.argv[1])
    if not os.path.isdir(d):
        print(json.dumps({"error": f"Directory not found: {d}"}))
        sys.exit(1)

    print(json.dumps(extract_results(d), indent=2))
