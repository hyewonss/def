"""
hitrate_astkv.py
----------------
2주차 GO/NO-GO 진단용 AST 서브트리 hit rate 분석.
4가지 조건 비교:
  1. observation only / alpha-rename all
  2. observation only / alpha-rename vars_only (함수/모듈명 보존)
  3. observation+action / alpha-rename all
  4. observation+action / alpha-rename vars_only (함수/모듈명 보존)
사용: python hitrate_astkv.py <trace_dir> <tokenizer_path>
"""

import sys, json, glob, os
from collections import Counter

SCRIPTS_DIR = os.path.expanduser("~/local-proj/ast-kv/scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
from astkv_fingerprint import parser, extract_subtrees, fingerprint, init_tokenizer, count_tokens

EXCLUDE = {"django__django-11019_run1", "matplotlib__matplotlib-23563_run0"}
GO_HIT_THRESHOLD = 25.0
GO_TOKEN_THRESHOLD = 30.0


def strip_line_numbers(text):
    out, hit = [], 0
    lines = text.split("\n")
    for ln in lines:
        idx = ln.find("\t")
        if idx != -1 and ln[:idx].strip().isdigit():
            out.append(ln[idx+1:]); hit += 1
        else:
            out.append(ln)
    return "\n".join(out) if hit >= max(1, len(lines)//2) else text


def iter_text_blocks(trace):
    for ev in trace.get("events", []):
        kind = ev.get("kind")
        if kind == "ObservationEvent":
            obs = ev.get("observation") or {}
            for blk in obs.get("content") or []:
                if isinstance(blk, dict) and blk.get("type") == "text":
                    txt = blk.get("text") or ""
                    if txt.strip():
                        yield ("observation", strip_line_numbers(txt))
        elif kind == "ActionEvent":
            act = ev.get("action") or {}
            if act.get("kind") != "FileEditorAction":
                continue
            for field in ("old_str", "new_str", "file_text"):
                txt = act.get(field)
                if txt and txt.strip():
                    yield (f"action_{field}", txt)


def fingerprints_and_tokens(text, rename_mode):
    """fingerprint 목록 + 자격 서브트리 토큰 수 + 전체 토큰 수 반환."""
    try:
        cb = text.encode("utf-8")
        total_tok = count_tokens(text)
        subs = extract_subtrees(parser.parse(cb).root_node, cb)
        fps = [fingerprint(n, cb, rename_mode=rename_mode) for n in subs]
        eligible_tok = sum(
            count_tokens(cb[n.start_byte:n.end_byte].decode("utf-8", "ignore"))
            for n in subs
        )
        return fps, eligible_tok, total_tok
    except Exception:
        return [], 0, 0


class Stat:
    def __init__(self, label, allowed_sources, rename_mode):
        self.label = label
        self.allowed = allowed_sources
        self.rename_mode = rename_mode
        self.global_seen = set()
        self.global_total = 0
        self.global_hit = 0
        self.total_eligible_tok = 0
        self.total_all_tok = 0
        self.per_session = []

    def accept(self, src_kind):
        return self.allowed is None or src_kind in self.allowed

    def add_session(self, name, blocks_by_mode):
        session_seen = set()
        s_total = s_hit = 0
        data = blocks_by_mode[self.rename_mode]
        for src_kind, fps, elig_tok, all_tok in data:
            if self.accept(src_kind):
                self.total_eligible_tok += elig_tok
                self.total_all_tok += all_tok
            if not self.accept(src_kind):
                continue
            for fp in fps:
                self.global_total += 1
                if fp in self.global_seen:
                    self.global_hit += 1
                else:
                    self.global_seen.add(fp)
                s_total += 1
                if fp in session_seen:
                    s_hit += 1
                else:
                    session_seen.add(fp)
        rate = (s_hit / s_total * 100) if s_total else 0.0
        self.per_session.append((name, s_total, s_hit, rate))

    def summary(self):
        micro_t = sum(t for _, t, _, _ in self.per_session)
        micro_h = sum(h for _, _, h, _ in self.per_session)
        micro = (micro_h / micro_t * 100) if micro_t else 0.0
        valid = [r for _, t, _, r in self.per_session if t > 0]
        macro = sum(valid) / len(valid) if valid else 0.0
        g_rate = (self.global_hit / self.global_total * 100) if self.global_total else 0.0
        tok_ratio = (self.total_eligible_tok / self.total_all_tok * 100) \
            if self.total_all_tok else 0.0
        return macro, g_rate, tok_ratio, micro_h, micro_t, self.global_hit, self.global_total


DEFAULT_TOKENIZER = "~/local-proj/ast-kv/models/Qwen3-Coder-30B-A3B-Instruct"


def main():
    if len(sys.argv) < 2:
        print(f"usage: python {sys.argv[0]} <trace_dir> [tokenizer_path]")
        sys.exit(1)
    trace_dir = os.path.expanduser(sys.argv[1])
    tok_path = os.path.expanduser(sys.argv[2] if len(sys.argv) >= 3 else DEFAULT_TOKENIZER)
    print(f"토크나이저 로딩: {tok_path}")
    init_tokenizer(tok_path)

    files = sorted(glob.glob(os.path.join(trace_dir, "*.json")))
    used = [f for f in files if os.path.basename(f)[:-5] not in EXCLUDE]
    skipped = [os.path.basename(f)[:-5] for f in files if os.path.basename(f)[:-5] in EXCLUDE]
    print(f"trace dir : {trace_dir}")
    print(f"전체 {len(files)}개 / 사용 {len(used)}개 / 제외 {len(skipped)}개")
    if skipped:
        print(f"제외: {', '.join(skipped)}")

    stats = [
        Stat("obs 단독   / alpha-rename all     ", {"observation"}, "all"),
        Stat("obs 단독   / alpha-rename vars_only", {"observation"}, "vars_only"),
        Stat("obs+action / alpha-rename all     ", None,             "all"),
        Stat("obs+action / alpha-rename vars_only", None,            "vars_only"),
    ]

    for i, f in enumerate(used):
        trace = json.load(open(f, encoding="utf-8"))
        name = os.path.basename(f)[:-5]

        raw_blocks = list(iter_text_blocks(trace))

        # rename_mode별 (src, fps, eligible_tok, all_tok) 미리 계산
        blocks_by_mode = {}
        for mode in ("all", "vars_only"):
            blocks_by_mode[mode] = [
                (src,) + fingerprints_and_tokens(text, mode)
                for src, text in raw_blocks
            ]

        for st in stats:
            st.add_session(name, blocks_by_mode)

        print(f"  [{i+1}/{len(used)}] {name} 처리 완료", flush=True)

    # 결과 출력
    print("\n" + "=" * 80)
    print(f"{'조건':<42} {'hitrate':>9} {'token ratio':>12} {'eligible':>9} {'hits':>6}")
    print("-" * 80)
    for st in stats:
        macro, g_rate, tok_ratio, micro_h, micro_t, g_hit, g_total = st.summary()
        print(f"{st.label:<42} {macro:>8.1f}% {tok_ratio:>11.1f}% {micro_t:>9} {micro_h:>6}")

    print()
    print("=" * 80)
    print(f"GO 기준 : hitrate ≥ {GO_HIT_THRESHOLD:.0f}%  AND  token ratio ≥ {GO_TOKEN_THRESHOLD:.0f}%")
    print("-" * 80)
    for st in stats:
        macro, g_rate, tok_ratio, micro_h, micro_t, g_hit, g_total = st.summary()
        hit_ok = macro >= GO_HIT_THRESHOLD
        tok_ok = tok_ratio >= GO_TOKEN_THRESHOLD
        go = "🟢 GO" if (hit_ok and tok_ok) else "🔴 NO-GO"
        print(f"  {st.label.strip():<44}: {go}  (hitrate {macro:.1f}%, token ratio {tok_ratio:.1f}%)")

    print("\n해석 메모:")
    print(" - hitrate: macro = task별 hit rate 평균 (세션 내)")
    print(" - token ratio: 전체 토큰 중 자격 서브트리 토큰 비율")
    print(" - obs+action의 action hit은 '편집 전 먼저 읽는다' 구조상 자명")
    print("   -> 메인 클레임은 obs 단독 기준 권장")
    print(" - all vs vars_only: all은 함수/모듈명까지 치환 -> hit rate 과대 추정 경향")


if __name__ == "__main__":
    main()
