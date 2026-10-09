#!/usr/bin/env python
"""
Abordagem B — usa Claude e Gemini como detectores de vulnerabilidade lendo o código
diretamente (sem ferramentas), para RQ1 (LLM vs. SAST) e RQ2 (Claude vs. Gemini).

Uso:
    python scripts/04_run_llm_detectors.py --input data/samples/pilot.jsonl
    python scripts/04_run_llm_detectors.py --input data/samples/pilot.jsonl --models claude
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.config import RESULTS_DIR  # noqa: E402
from common.llm_clients import call_claude, call_gemini  # noqa: E402
from common.prompts import DETECTOR_SYSTEM_PROMPT, build_detector_user_prompt  # noqa: E402
from common.schema import DetectionResult, read_jsonl, write_jsonl  # noqa: E402

JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_detector_json(text: str) -> dict:
    """Extrai o objeto JSON da resposta do LLM, tolerando que o modelo envolva a resposta
    em ```json ... ``` apesar da instrução para não fazer isso."""
    match = JSON_BLOCK_RE.search(text)
    if not match:
        raise ValueError(f"Resposta não contém um objeto JSON reconhecível: {text[:200]!r}")
    return json.loads(match.group(0))


def run_detector(call_fn, detector_name: str, sample: dict) -> DetectionResult:
    user_prompt = build_detector_user_prompt(sample["language"], sample["file_path"], sample["code"])
    resp = call_fn(DETECTOR_SYSTEM_PROMPT, user_prompt)

    if resp.error or resp.text is None:
        return DetectionResult(
            sample_id=sample["sample_id"], approach="B_llm", detector=detector_name,
            predicted_vulnerable=False, error=resp.error,
            latency_seconds=resp.latency_seconds,
        )

    try:
        parsed = parse_detector_json(resp.text)
        return DetectionResult(
            sample_id=sample["sample_id"], approach="B_llm", detector=detector_name,
            predicted_vulnerable=bool(parsed.get("is_vulnerable", False)),
            predicted_cwe=parsed.get("cwe_id"),
            confidence=parsed.get("confidence"),
            raw_output=resp.text,
            latency_seconds=resp.latency_seconds,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            estimated_cost_usd=resp.estimated_cost_usd,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        return DetectionResult(
            sample_id=sample["sample_id"], approach="B_llm", detector=detector_name,
            predicted_vulnerable=False, raw_output=resp.text,
            latency_seconds=resp.latency_seconds, error=f"parse_error: {exc}",
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--models", nargs="+", default=["claude", "gemini"], choices=["claude", "gemini"])
    args = parser.parse_args()

    samples = list(read_jsonl(Path(args.input)))
    detections: list[DetectionResult] = []

    detector_fns = {"claude": call_claude, "gemini": call_gemini}

    for sample in tqdm(samples, desc="Rodando detectores LLM"):
        for model_name in args.models:
            result = run_detector(detector_fns[model_name], model_name, sample)
            detections.append(result)
            if result.error:
                print(f"[erro] {sample['sample_id']} / {model_name}: {result.error}")

    write_jsonl(RESULTS_DIR / "detection_B_llm.jsonl", (d.to_dict() for d in detections))
    print(f"[ok] {len(detections)} resultados -> results/detection_B_llm.jsonl")


if __name__ == "__main__":
    main()
