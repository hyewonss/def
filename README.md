# 14팀 def
2026-spring capstone project
# SynTree KV : 코딩 에이전트를 위한 AST 기반 KV 재사용 추론 최적화

> **코딩 에이전트를 위한 AST 기반 KV cache 재사용** — long-context agentic workflow에서 반복되는 코드 구조를 AST 지문으로 탐지하고, 중복 prefill 비용을 제거합니다.

[![Status](https://img.shields.io/badge/status-research-blue?style=flat-square)](.)
[![Agent](https://img.shields.io/badge/agent-OpenHands-orange?style=flat-square)](https://github.com/All-Hands-AI/OpenHands)
[![Runtime](https://img.shields.io/badge/runtime-vLLM-green?style=flat-square)](https://github.com/vllm-project/vllm)
[![Hardware](https://img.shields.io/badge/GPU-RTX%205090%20×2-76b900?style=flat-square&logo=nvidia)](.)
[![Benchmark](https://img.shields.io/badge/eval-SWE--bench%20Lite-purple?style=flat-square)](https://www.swebench.com)

---

## 팀 정보

| 항목 | 내용 |
|------|------|
| 팀 번호 | 14 |
| 팀명 | def |
| 소속 | 이화여자대학교 |
| 지도교수 | 심재형 교수님 |
| 팀원 | 서혜원, 신은서, 이재린 |

---

## 개요

코딩 에이전트는 다중 턴 작업 과정에서 **같은 코드 파일을 반복적으로 읽습니다**. 대화 기록이 쌓일수록 동일한 코드 구조가 context에 반복 등장하지만, vLLM의 기존 prefix caching은 앞부분이 완전히 일치해야만 동작하기 때문에 매 턴마다 cache miss가 발생합니다.

**문제 정의:** 코딩 에이전트의 멀티턴 세션에서 중복 코드 블록이 반복 등장함에도 Serving Layer가 매 턴 전체를 prefill하여 불필요한 지연 비용이 발생한다.

**SynTree KV**은 코드 토큰에 AST(Abstract Syntax Tree) 구조 레이블을 부여하고, **BLAKE3 해시 기반 AST 지문**으로 context 내 중복 코드 블록을 탐지합니다. 동일 지문의 KV cache를 재사용함으로써 반복 prefill 비용을 제거하고 정확도를 유지하며 TTFT(Time-To-First-Token)를 단축합니다.

```
Turn 1:  [system] + [obs: file_A] + [action]               → file_A prefill 실행 + KV 저장
Turn 2:  [system] + [history_1] + [obs: file_A] + [action] → AST 지문 일치 → KV 재사용 ✓
Turn N:  [system] + [history_1..N] + [obs: file_A] + ...

                    ┌──────────────────────────────────────┐
                    │         TreeHit Cache Layer          │
                    │                                      │
                    │  AST fingerprint(file_A) → KV hit ✓  │
                    │  AST fingerprint(file_B) → KV hit ✓  │
                    │  AST fingerprint(file_C) → miss      │
                    └──────────────────────────────────────┘
                                       ↓
                     Turn 2..N에서 중복 코드 블록 prefill 생략
```

---

## 문제 의식

멀티턴 코딩 에이전트 세션에서는 같은 파일을 반복해서 읽게 되고, 매번 전체 prefill이 재실행됩니다. 기존 연구들은 이 문제를 다음과 같은 이유로 해결하지 못합니다.
 
| 방법 | 한계 |
|---|---|
| **vLLM prefix caching** | 연속된 앞부분 토큰이 완전 일치할 때만 재사용. 멀티턴 세션에서 `tool_call_id`, `timestamp` 같은 동적 값이 매 턴 prefix를 파괴 → 코드 블록 구간에서 사실상 미작동 |
| **PromptCache** | 사전 정의된 스키마 단위 재사용. RoPE position shift 미처리 → 위치가 달라진 KV 삽입 시 attention 왜곡 |
| **CacheBlend** | 품질 보정 가능하나 정적 chunk 경계 전제 → 코딩 에이전트의 동적 출력에 적용 불가 |
| **SnapKV** | attention score 기반 KV 압축 (현재 SOTA). 코드 구조 미활용, KV를 버리는 방식 → 정확도 손실 불가피 |
 
**실험으로 확인한 사실:** vLLM prefix caching은 hit rate 75.8%임에도 Vanilla decode 대비 TTFT 차이가 단 0.8ms에 불과합니다. 캐시 적중이 시스템 프롬프트 앞부분에서만 발생하고, 실제 코드 블록 구간에서는 캐시가 작동하지 않기 때문입니다.

---

## 핵심 아이디어

기존 prefix caching이 **중복 코드 블록**을 **다른 것**으로 인식할 때, SynTree KV는 **재사용 가능한 구조적 단위**로 인식합니다.
 
### ① AST 서브트리 단위 KV 재사용
 
Tree-sitter로 입력 코드를 실시간 파싱 → AST 생성 → 재사용 후보 필터링
 
**재사용 후보 조건:**
- AST 깊이 ≥ 2
- 토큰 수 ≥ 8
- 노드 유형 ∈ `{FunctionDef, ClassDef, ImportStmt, CallExpr, ...}`
prefix caching은 첫 토큰부터 완전히 일치해야 캐시를 사용하는 반면, SynTree KV는 함수·클래스 블록을 색인화하여 같은 블록이 재등장하면 즉시 호출합니다.
 
### ② α-rename 정규화 + BLAKE3 지문
 
변수 이름이 달라도 구조가 같으면 같은 블록으로 인식합니다.
 
```
입력 코드 → α-rename 정규화 → S-expression 직렬화 → BLAKE3 해시 → 32byte 지문 (캐시 조회 키)
```

α-rename에서 모든 식별자를 치환하는 `all` 방식과 모듈명·메서드명을 보존하는 `vars_only` 방식을 모두 지원합니다.
 
### ③ RoPE Re-positioning
 
재사용 KV는 원래 위치에서 계산된 값인데, 새 context에서는 다른 위치에 삽입됩니다. 그대로 삽입하면 위치 정보 불일치로 attention이 왜곡되므로, 위치 오프셋 Δ를 이용해 보정합니다.
 
```
K_new = R(Δ) · K_cached
 
Δ = 새 위치 - 원래 위치
R(Δ) = RoPE 회전 행렬
```
---

## 기술 스택

| 구성 요소 | 기술 |
|---|---|
| Coding Agent | [OpenHands](https://github.com/All-Hands-AI/OpenHands) |
| Inference Runtime | [vLLM](https://github.com/vllm-project/vllm) |
| 모델 | Qwen3-Coder-30B-A3B-Instruct-FP8, Qwen2.5-Coder-0.5B-Instruct |
| AST 파싱 | Tree-sitter (증분 파싱, Python) |
| 지문 생성 | BLAKE3 해시 (16자리) |
| 하드웨어 | NVIDIA RTX 5090 × 2 (VRAM 31.84 GB each) |
| 평가 | SWE-bench Lite (25개 이슈, 12개 레포) |
| OS | Linux |

---

## 전체 파이프라인

```
① 토큰화 + Tree-sitter 증분 파싱 → AST 생성
         ↓
② 자격 조건 필터링 (깊이 ≥ 2, 토큰 수 ≥ 8, 허용 노드 유형)
         ↓
③ α-rename → BLAKE3 지문 → SessionCacheTable 조회
         ↓
   hit / miss
    ↙        ↘
④-a 적중(hit)       ④-b 미적중(miss)
prefill skip +      정상 prefill 후
RoPE-shifted KV splice  SessionCacheTable 등록
         ↓
⑤ Prefill 완료 후 peak KV 측정 (0.85 × 4GB 초과 시 budget merge 발동)
         ↓
⑥ Decode 진행 (splice된/병합된 슬롯을 일반 슬롯과 동일하게 어텐션에 노출)
         ↓
⑦ 발열 지표 polling (32토큰마다, 임계 초과 시 자격 임계값·예산·정규화 강도 하강)
         ↓
⑧ 턴 종료 — LRU eviction (SessionCacheTable을 512MB 이내로 유지)
```

---

## 설치 및 실행 방법

### 사전 요구 사항

- CUDA 12.x 이상
- Python 3.10+
- NVIDIA GPU (VRAM 31GB+ 권장)

### 환경 구성

```bash
# 레포 클론
git clone https://github.com/capstone-2026-ewha/def.git
cd def

# conda 환경 생성 (vLLM 서빙용)
conda create -n vllm python=3.10
conda activate vllm
pip install vllm==0.8.x humming-kernels[cu13]

# conda 환경 생성 (trace 수집 및 분석용)
conda create -n openhands python=3.10
conda activate openhands
pip install open-hands-ai tree-sitter transformers blake3
```

### 모델 다운로드

```bash
# Qwen3-Coder-30B-A3B-FP8 모델 다운로드
huggingface-cli download Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8 \
    --local-dir ./models/Qwen3-Coder-30B-A3B-Instruct-FP8
```

### vLLM 서버 실행

```bash
conda activate vllm
vllm serve ./models/Qwen3-Coder-30B-A3B-Instruct-FP8 \
    --tool-call-parser qwen3_coder \
    --enable-expert-parallel \
    --tensor-parallel-size 2 \
    --max-model-len 131072 \
    --port 8000
```

### SWE-bench Trace 수집

```bash
conda activate openhands
python scripts/collect_traces_30b_fp8.py \
    --model-url http://localhost:8000/v1 \
    --output-dir ./traces/30b_run01 \
    --n-tasks 50
```

### AST Hit Rate 분석

```bash
# 4가지 조건 hit rate 분석 실행
python scripts/analyze_hitrate.py \
    --trace-dir ./traces/30b_run01 \
    --mode all          # all | vars_only
    --scope top_level   # top_level | all_nodes
```
---

## 시연

- [self_demo.md](./self_demo.md) 에서 배포한 라이브데모 상세확인 가능!
- 🔗라이브데모: https://def-omega.vercel.app/
- 🎥시연영상: https://youtu.be/oJYQL1lQmpE

---

## 📊 실험 결과

### exp1 — Hit Rate 분석 (30B FP8, 48개 유효 trace 기준)

GO 기준: hit rate ≥ 25% AND token ratio ≥ 30%

| 조건 | Hit Rate | Token Ratio | 판정 |
|------|----------|-------------|------|
| obs 단독 / vars_only | **32.6%** | 34.5% | ✅ GO |
| obs 단독 / all | 42.4% | 34.5% | ✅ GO |
| obs+action / vars_only | 42.6% | 40.0% | ✅ GO |
| obs+action / all | 51.1% | 40.0% | ✅ GO |

- α-rename 순수 기여: **+9.8%p** (exact-match 대비)
- 권장 수치: obs 단독 / vars_only / 최상위만 → **32.6% hit rate / 34.5% token ratio**

### exp2 — TTFT Baseline 비교 (Qwen2.5-Coder-0.5B 기준)

| 조건 | 평균 TTFT | vanilla 대비 |
|------|----------|-------------|
| Vanilla | 30.5 ms | — |
| vLLM prefix caching | 29.7 ms | -4.2% |
| **SynTree KV (목표)** | — | **목표: -30%+** |

> vLLM prefix caching은 hit rate 75.8%임에도 TTFT 개선이 0.8ms에 불과 — 코드 블록 구간에서 캐시가 실질적으로 작동하지 않음을 확인.

---

## 1학기 연구 결과

- [x] 문제 정의 및 선행 연구 조사
- [x] Qwen3-Coder-30B-A3B-FP8로 SWE-bench Lite trace 48개 수집
- [x] AST 지문 파이프라인 구현 (Tree-sitter + α-rename + BLAKE3)
- [x] Hit rate 분석 (4가지 조건) → **GO 판정**
- [x] Vanilla / vLLM prefix caching TTFT baseline 측정

## 2학기 구현 예정
- [ ] SessionCacheTable 구현 (PyTorch KV splice 훅)
- [ ] RoPE re-positioning 모듈 구현
- [ ] AST 인식 KV 재사용 통합 실험
- [ ] 최종 TTFT 비교 (vanilla / prefix caching / TreeHit)
- [ ] 논문 작성

---

## 레포 구조

```
def/
│
├── README.md                             ← 프로젝트 개요, 실행 방법, 폴더 구조, 주요 기능, 배포 링크
├── self_demo.md 
├── requirements.txt                      ← 재현에 필요한 패키지 목록
├── LICENSE
├── .gitignore
│
├── docs/
│   ├── Team_Ground_Rule.md
│	├── elevator_speech.md
│	├── project briefs.md
│	├── related_works.md
│	├── 14_def_FinalReport.pdf	          ← 최종보고서
│   └── 14_def_발표자료.pdf	              ← 발표자료 
│
└── experiments/
		├── scripts/
		│   ├── collect_traces_30b_fp8.py 
		│   ├── vanilla_replay.py
		│   ├── prefix_caching_replay.py 
		│   ├── hitrate_astkv.py 
		│   ├── astkv_fingerprint.py 
		│   └── visualize/ 
		│       ├── plot_ttft.py 
		│       └── plot_ttft_avg_comparison.py 
		│
		├── data/
		│		├── swe_bench_25.json             ← 실험에 사용한 SWE-bench 이슈 목록
		│   └── traces/ 
		│			  └── 30b_direct_run01
		│           └── trace 총 50개
		│
		└── results/ 
		    ├── 0.5b/
		    │   ├── prefix_caching_replay.log
		    │   ├── prefix_caching_results.json
		    │   ├── vanilla_replay_results.json
		    │   └── vanilla_replay.log
		    │
		    └── figures/ 
		        ├── ttft_comparison_0.5b.png
		        └── ttft_avg_comparison_0.5b.png

```

---

## References

- Kwon et al. *Efficient Memory Management for Large Language Model Serving with PagedAttention.* SOSP, 2023.
- Gim et al. *PromptCache: Modular Attention Reuse for Low-Latency Inference.* MLSys, 2024.
- Yao et al. *CacheBlend: Fast Large Language Model Serving for RAG with Cached Knowledge Fusion.* EuroSys, 2025.
- Li et al. *SnapKV: LLM Knows What You are Looking for Before Generation.* NeurIPS, 2024.
- Yao et al. *DeFT: Decoding with Flash Tree-attention for Efficient Tree-structured LLM Inference.* ICLR, 2024.

---

## 라이선스

본 프로젝트는 연구 목적으로 작성되었습니다. 코드는 [MIT License](LICENSE) 하에 배포됩니다.
