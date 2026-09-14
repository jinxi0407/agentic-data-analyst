"""Audited city-literal corrections only; original evidence is immutable."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import sqlglot
from sqlglot import exp

from app.tools.database import fetch_all
from eval.scoring import digest, fingerprint, write_json

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = ["app/agent/clarification.py", "app/agent/production.py", "app/main.py",
             "app/config.py", "app/tools/qwen.py", "app/tools/guardrail.py",
             "app/tools/database.py", "eval/strong_baseline.py", "eval/strong_baseline_v2.py",
             "eval/scoring.py", "eval/run_clarification.py"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_systems():
    hashes = {}
    for name in PROTECTED:
        original = subprocess.check_output(["git", "show", "30e9a08:" + name], cwd=ROOT)
        assert (ROOT / name).read_bytes() == original, f"Frozen code changed: {name}"
        hashes[name] = sha(ROOT / name)
    for name in ["eval/strong_baseline.py", "eval/strong_baseline_v2.py",
                 "app/tools/qwen.py", "app/tools/guardrail.py", "app/tools/database.py"]:
        assert (ROOT / name).read_bytes() == subprocess.check_output(["git", "show", "v1.0.0:"+name], cwd=ROOT)
    return hashes


def city_equalities(sql):
    tree = sqlglot.parse_one(sql, read="mysql")
    assert isinstance(tree, exp.Select)
    return [eq for eq in tree.find_all(exp.EQ) if isinstance(eq.left, exp.Column)
            and eq.left.name == "city" and isinstance(eq.right, exp.Literal) and eq.right.is_string]


def correct_literal(sql, original, actual):
    edits = []
    for eq in city_equalities(sql):
        if eq.right.this == original:
            start, end = eq.right.meta["start"], eq.right.meta["end"]
            assert sql[start:end+1] == "'"+original+"'"
            edits.append((start, end+1, "'"+actual+"'"))
    assert edits, "Proposal has no matching city predicate"
    for start, end, replacement in sorted(edits, reverse=True):
        sql = sql[:start] + replacement + sql[end:]
    return sql


def main():
    output = ROOT / "eval/clarification_city_audit.json"
    assert not output.exists(), "Audit already frozen; refusing overwrite"
    assert not list((ROOT/"eval").glob("clarification_holdout*results.json")), "Original holdout has results"
    assert not list((ROOT/"eval").glob("clarification_corrected*results.json")), "Corrected holdout has results"
    hashes = check_systems()
    evidence = fetch_all("SELECT province,city,COUNT(*) AS row_count FROM users GROUP BY province,city ORDER BY province,city")
    before = fingerprint(fetch_all)
    preview = ROOT/"eval/clarification_gt_correction_proposal.json"
    proposals = json.loads(preview.read_text())
    audit, unresolved, files = [], [], {}
    originals = {str(preview.relative_to(ROOT)): sha(preview)}
    for split in ["dev", "holdout"]:
        path = ROOT/f"eval/clarification_{split}.json"
        manifest_path = path.with_name(path.stem+"_manifest.json")
        cases = json.loads(path.read_text())
        manifest = json.loads(manifest_path.read_text())
        assert digest(cases) == manifest["cases_sha256"]
        assert before == manifest["database"], "Database differs from original freeze"
        originals[str(path.relative_to(ROOT))] = sha(path)
        originals[str(manifest_path.relative_to(ROOT))] = sha(manifest_path)
        revised = deepcopy(cases)
        for old, case in zip(cases, revised):
            entries = [p for p in proposals if p["split"] == split and p["case_id"] == case["id"]]
            assert len(entries) <= 1
            if entries:
                proposal = entries[0]
                assert proposal["dataset_sha256"] == digest(cases)
                assert proposal["original_reference_sql"] == old["reference_sql"]
                verified = []
                for change in proposal["changes"]:
                    original, actual = change["original_city"], change["actual_city"]
                    candidates = [r for r in evidence if r["city"] == original+"市"]
                    exact = [r for r in evidence if r["city"] == original]
                    if actual != original+"市" or len(candidates)!=1 or exact:
                        unresolved.append(dict(split=split,case_id=case["id"],city=original,
                                               reason="Suffix identity not uniquely supported; unchanged"))
                        continue
                    case["reference_sql"] = correct_literal(case["reference_sql"],original,actual)
                    verified.append(dict(original_city=original,corrected_city=actual,database_evidence=candidates,
                        reason=f"{original}与{actual}仅相差行政名称后缀市；数据库只有此唯一同名城市，省份证据如上。不是根据空结果选择替代城市。"))
                if verified:
                    case["ground_truth_result"] = fetch_all(case["reference_sql"])
                    audit.append(dict(split=split,case_id=case["id"],mappings=verified,
                        original_reference_sql=old["reference_sql"],corrected_reference_sql=case["reference_sql"],
                        original_ground_truth=old["ground_truth_result"],corrected_ground_truth=case["ground_truth_result"]))
            for eq in city_equalities(case["reference_sql"]):
                if not any(r["city"]==eq.right.this for r in evidence):
                    unresolved.append(dict(split=split,case_id=case["id"],city=eq.right.this,
                        reason="City literal absent from current database; preserved. Empty/zero/NULL may be legitimate."))
            assert {k:v for k,v in case.items() if k not in ("reference_sql","ground_truth_result")} == {
                k:v for k,v in old.items() if k not in ("reference_sql","ground_truth_result")}
            actual_result = fetch_all(case["reference_sql"])
            assert actual_result == case["ground_truth_result"], f"Unresolved reference mismatch: {case['id']}"
            if case["reference_sql"] == old["reference_sql"]:
                assert case == old
        target = ROOT/f"eval/clarification_{split}_corrected.json"
        assert not target.exists()
        write_json(target,revised)
        files[str(target.relative_to(ROOT))] = sha(target)
    assert before == fingerprint(fetch_all), "Database changed during audit"
    assert all(sha(ROOT/p)==h for p,h in originals.items())
    write_json(output,dict(corrections=audit,unresolved=unresolved,city_evidence=evidence,
        original_files_sha256=originals,corrected_files_sha256=files,database=before,
        reference_date="2026-09-12",system_commit="30e9a08",baseline_tag="v1.0.0",
        system_files_sha256=hashes,proposal_count=len(proposals),
        model_calls_before_refreeze=0,all_reference_sql_validated=True,
        unchanged_case_equality_verified=True))
    print(json.dumps({"corrected":{s:sum(r["split"]==s for r in audit) for s in ["dev","holdout"]},
                      "unresolved":len(unresolved),"database_unchanged":True},ensure_ascii=False))


if __name__ == "__main__":
    main()
