from __future__ import annotations

import argparse

STEPS = ["collect", "normalize", "structure", "build-texts", "embed", "load"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-step", choices=STEPS, default="collect")
    parser.add_argument("--to-step", choices=STEPS, default="load")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    selected = STEPS[STEPS.index(args.from_step) : STEPS.index(args.to_step) + 1]
    print("실행 예정 단계:", " -> ".join(selected), f"(limit={args.limit})")
    print("각 단계 스크립트는 개별 입력 파일을 받아 실행되도록 분리되어 있습니다.")


if __name__ == "__main__":
    main()

