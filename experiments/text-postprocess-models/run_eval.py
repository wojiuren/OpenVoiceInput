from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parent
LLAMA_CLI = ROOT / "llama-cpp" / "llama-cli.exe"
EVAL_SET = ROOT / "eval-set.jsonl"
MODEL_MANIFEST = ROOT / "models.json"
RESULTS_DIR = ROOT / "results"
PROMPTS_DIR = ROOT / "generated-prompts"


TASK_SYSTEM_PROMPTS = {
    "polish": "你是中文语音输入后的文本整理器。/no_think",
    "hotwords": "你是中文语音输入后的候选热词提取器。/no_think",
}

GENERIC_HOTWORDS = {
    "测试",
    "模型",
    "术语",
    "内容",
    "关键词",
    "项目",
    "功能",
    "配置",
    "文本",
    "结果",
    "问题",
    "自动",
    "技术",
    "相关",
    "系统",
    "任务",
    "热词",
    "东西",
    "这个",
    "那个",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def model_ready(model: dict[str, Any]) -> tuple[bool, str]:
    model_path = ROOT / model["path"]
    if not model_path.exists():
        return False, f"missing: {model_path}"
    min_bytes = int(model.get("min_bytes") or 0)
    size = model_path.stat().st_size
    if min_bytes and size < min_bytes:
        return False, f"too_small: {size} < {min_bytes}"
    return True, f"ready: {size}"


def build_prompt(case: dict[str, Any]) -> str:
    task = case["task"]
    source = case["input"]
    if task == "polish":
        return (
            "请整理下面这段语音识别文本。\n"
            "规则：\n"
            "1. 只补标点、去掉明显口头填充词、修正明显同音字或错别字。\n"
            "2. 不增加新信息，不解释，不输出项目符号。\n"
            "3. 专有名词、英文产品名和代码词尽量保留原样。\n"
            "4. 只输出整理后的文本。\n\n"
            f"文本：\n{source}\n"
        )
    if task == "hotwords":
        return (
            "请从下面这段语音识别文本中提取候选热词。\n"
            "规则：\n"
            "1. 只提取值得加入术语表、热词表或快速记录规则的词。\n"
            "2. 包含人名、地名、项目名、模型名、功能名、技术名。\n"
            "3. 不要提取普通虚词或太泛的词。\n"
            "4. 只输出 JSON，格式为：{\"hotwords\":[\"词1\",\"词2\"],\"notes\":\"一句话说明\"}\n\n"
            f"文本：\n{source}\n"
        )
    raise ValueError(f"Unknown task: {task}")


def write_prompt(case: dict[str, Any]) -> Path:
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    prompt_path = PROMPTS_DIR / f"{case['id']}.txt"
    prompt_path.write_text(build_prompt(case), encoding="utf-8")
    return prompt_path


def run_case(model: dict[str, Any], case: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    model_path = ROOT / model["path"]
    model_arg = str(Path(model["path"]))
    prompt_path = write_prompt(case)
    prompt_arg = str(prompt_path.relative_to(ROOT))
    command = [
        str(LLAMA_CLI),
        "-m",
        model_arg,
        "-sys",
        TASK_SYSTEM_PROMPTS[case["task"]],
        "-f",
        prompt_arg,
        "--jinja",
        "-st",
        "--no-display-prompt",
        "--temp",
        str(args.temperature),
        "--top-k",
        "20",
        "--top-p",
        "0.8",
        "--repeat-penalty",
        "1.2",
        "-c",
        str(args.ctx_size),
        "-n",
        str(args.predict),
        "-t",
        str(args.threads),
        "--no-warmup",
        "--no-mmap",
        "--no-show-timings",
        "--simple-io",
    ]
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=args.timeout_s,
    )
    elapsed_s = time.perf_counter() - started
    raw_output = completed.stdout + ("\n[stderr]\n" + completed.stderr if completed.stderr else "")
    answer = extract_answer(completed.stdout, case["input"])
    row = {
        "model_id": model["id"],
        "model_display_name": model["display_name"],
        "case_id": case["id"],
        "task": case["task"],
        "elapsed_s": round(elapsed_s, 3),
        "returncode": completed.returncode,
        "answer": answer,
        "raw_output": raw_output,
        "expected_notes": case.get("expected_notes", ""),
        "command": command,
    }
    if case["task"] == "hotwords":
        row["hotword_cleanup"] = clean_hotword_answer(answer)
    return row


def extract_answer(raw_output: str, source_text: str) -> str:
    text = raw_output.replace("\r\n", "\n").strip()
    text = re.sub(r"(?s)^.*available commands:.*?\n\n", "", text).strip()
    text = re.sub(r"(?s)\[ Prompt:.*$", "", text).strip()
    text = re.sub(r"(?s)(^|\n)Exiting\.\.\..*$", "", text).strip()
    text = re.sub(r"(?s)\nload_backend:.*$", "", text).strip()
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    if not blocks:
        return ""
    answer = blocks[-1]
    return re.sub(r"(?m)^> ?", "", answer).strip()


def normalize_hotword(value: Any) -> str:
    word = str(value).strip()
    word = word.strip(" \t\r\n`'\"“”‘’[]()（）<>《》,，.。;；:：、")
    return re.sub(r"\s+", " ", word).strip()


def should_drop_hotword(word: str) -> bool:
    if not word:
        return True
    if word in GENERIC_HOTWORDS:
        return True
    if len(word) == 1 and not re.search(r"[A-Za-z0-9]", word):
        return True
    return False


def parse_hotword_json(answer: str) -> tuple[dict[str, Any] | None, str]:
    text = answer.strip()
    text = re.sub(r"(?s)^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"(?s)\s*```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None, "no_json_object"
    candidate = text[start : end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        return None, f"json_decode_error: {exc.msg}"
    if not isinstance(data, dict):
        return None, "json_not_object"
    return data, ""


def clean_hotword_answer(answer: str) -> dict[str, Any]:
    data, error = parse_hotword_json(answer)
    raw_words: list[Any] = []
    notes = ""
    if data is not None:
        raw_value = data.get("hotwords", [])
        if isinstance(raw_value, list):
            raw_words = raw_value
        notes_value = data.get("notes", "")
        if isinstance(notes_value, str):
            notes = notes_value

    cleaned: list[str] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for raw_word in raw_words:
        word = normalize_hotword(raw_word)
        key = word.casefold()
        if should_drop_hotword(word):
            if word:
                dropped.append(word)
            continue
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(word)

    return {
        "parse_ok": data is not None,
        "error": error,
        "hotwords": cleaned,
        "dropped_hotwords": dropped,
        "notes": notes,
    }


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        for row in rows:
            json.dump(row, file, ensure_ascii=False)
            file.write("\n")


def write_markdown_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Local Text Model Eval Results",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| Model | Case | Task | Seconds | Return | Answer | Cleaned hotwords | Dropped |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        answer = str(row["answer"]).replace("\n", "<br>").replace("|", "\\|")
        cleanup = row.get("hotword_cleanup") or {}
        cleaned_hotwords = ", ".join(cleanup.get("hotwords", [])).replace("|", "\\|")
        dropped_hotwords = ", ".join(cleanup.get("dropped_hotwords", [])).replace("|", "\\|")
        lines.append(
            f"| {row['model_id']} | {row['case_id']} | {row['task']} | "
            f"{row['elapsed_s']} | {row['returncode']} | {answer} | "
            f"{cleaned_hotwords} | {dropped_hotwords} |"
        )
    lines.extend(
        [
            "",
            "## Aggregate",
            "",
            "| Model | Task | Count | Average seconds |",
            "|---|---|---:|---:|",
        ]
    )
    groups = sorted({(str(row["model_id"]), str(row["task"])) for row in rows})
    for model_id, task in groups:
        task_rows = [
            row
            for row in rows
            if str(row["model_id"]) == model_id and str(row["task"]) == task
        ]
        avg_seconds = sum(float(row["elapsed_s"]) for row in task_rows) / len(task_rows)
        lines.append(f"| {model_id} | {task} | {len(task_rows)} | {avg_seconds:.3f} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def select_cases(cases: list[dict[str, Any]], task_filter: str) -> list[dict[str, Any]]:
    if task_filter == "all":
        return cases
    return [case for case in cases if case["task"] == task_filter]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local text post-processing model evals.")
    parser.add_argument("--model-id", default="all")
    parser.add_argument("--task", choices=["all", "polish", "hotwords"], default="all")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 8) // 2))
    parser.add_argument("--ctx-size", type=int, default=4096)
    parser.add_argument("--predict", type=int, default=180)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--timeout-s", type=int, default=240)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    cases = select_cases(load_jsonl(EVAL_SET), args.task)
    if args.limit:
        cases = cases[: args.limit]
    models = load_json(MODEL_MANIFEST)
    if args.model_id != "all":
        models = [model for model in models if model["id"] == args.model_id]

    if args.list:
        for model in models:
            ready, reason = model_ready(model)
            print(f"{model['id']}: {reason}")
        print(f"cases: {len(cases)}")
        return 0

    if not LLAMA_CLI.exists():
        print(f"Missing llama-cli: {LLAMA_CLI}", file=sys.stderr)
        return 2

    run_id = time.strftime("%Y%m%d-%H%M%S")
    all_rows: list[dict[str, Any]] = []
    for model in models:
        ready, reason = model_ready(model)
        if not ready:
            print(f"SKIP {model['id']}: {reason}")
            continue
        for case in cases:
            print(f"RUN {model['id']} {case['id']}")
            row = run_case(model, case, args)
            all_rows.append(row)
            print(f"DONE {model['id']} {case['id']} {row['elapsed_s']}s")

    if not all_rows:
        print("No eval rows were produced.", file=sys.stderr)
        return 1
    append_jsonl(RESULTS_DIR / "results.jsonl", all_rows)
    write_markdown_summary(RESULTS_DIR / f"summary-{run_id}.md", all_rows)
    print(f"Wrote {len(all_rows)} rows to {RESULTS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
