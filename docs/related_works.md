# Related Work
 
본 연구는 세 가지 선행 연구 흐름의 교차점에 위치한다:
(1) LLM inference serving의 KV-cache 관리,
(2) 모듈형·비-prefix KV 재사용,
(3) 코드 구조 인식 기반 최적화.
아래에서 각 갈래를 정리하고, 본 연구와의 차별점을 명시한다.
 
---
 
## 1. KV-Cache 관리 및 Prefix Caching
 
### 1.1 PagedAttention / vLLM
Kwon et al. (SOSP 2023) [62]은 PagedAttention을 도입해 KV-cache를 운영체제의 페이지 메모리처럼 관리함으로써 단편화를 줄이고 처리량을 대폭 향상시켰다. 이 위에 구현된 **prefix caching**은 요청들이 동일한 연속 prefix를 공유할 때 prefill 계산을 재사용하는 기법이다. 산업 표준 baseline으로 자리 잡았으나, 멀티턴 코딩 에이전트 세션에서는 타임스탬프·`tool_call_id`처럼 매 턴 변경되는 메타정보가 prefix 앞부분에 삽입되어 "완전 일치 prefix" 조건을 깨뜨린다. 본 연구가 수집한 SWE-bench Lite 기반 48개 trace(총 1,721턴)의 vanilla replay 실험 결과, TTFT가 턴이 늘수록 선형 증가하며 prefix caching replay에서도 동일한 선형 증가 패턴이 관측되었다. 이는 prefix caching의 실질적 hit이 0에 가까움을 시사하며, 본 연구의 동기를 실험적으로 뒷받침한다.
 
### 1.2 ShadowKV
Sun et al. (ICML 2024) [8]은 장문 컨텍스트 환경에서 KV-cache의 key를 낮은 랭크로 압축하고 value를 CPU에 오프로드하는 전략으로 처리량을 높였다. 멀티턴 세션의 KV 누적 설계를 참조하지만, 코딩 에이전트의 구조적 반복 패턴이나 동적 도구 출력 경계 문제를 다루지 않는다.
 
---
 
## 2. 모듈형·비-prefix KV 재사용
 
### 2.1 PromptCache
Gim et al. (MLSys 2024) [64]는 사용자가 사전 정의한 스키마 단위로 KV-cache를 재사용하는 방법을 제안했다. 시스템 프롬프트처럼 반복적으로 사용되는 고정 청크의 prefill을 건너뛸 수 있어 첫 응답 지연을 줄인다. 그러나 이 방법은 **정적으로 정의된 청크 경계**를 전제한다. 코딩 에이전트가 실행 중에 동적으로 생성하는 파일 내용·grep 결과·오류 메시지 등에는 사전 스키마를 적용하기 어려우며, RoPE 위치 불일치를 명시적으로 처리하지 않는다. 본 연구의 AST 서브트리 경계는 런타임에 Tree-sitter로 자동 추출되므로 이 한계를 극복한다.
 
### 2.2 CacheBlend
Yao et al. (EuroSys 2025) [63]은 RAG(Retrieval-Augmented Generation) 환경에서 비-prefix 구간의 KV를 선택적으로 재계산해 품질을 보정하는 기법을 제안했다. 모듈형 KV 재사용의 대표 baseline으로, token-level positional re-encoding을 수행한다. 그러나 **AST 서브트리와 같은 구조적 경계를 정의하지 않으며**, 코딩 에이전트의 동적 도구 출력처럼 경계가 사전에 알려지지 않은 상황에서는 적용이 어렵다. 본 연구의 α-rename 정규화는 변수명만 다를 뿐 구조가 같은 코드 블록을 동일 지문으로 묶어 CacheBlend가 포착하지 못하는 반복 패턴을 다룬다.
 
### 2.3 DeFT
Yao et al. (ICLR 2024) [59]는 트리 구조 기반 LLM 추론에서 KV 재사용을 다루는 직접적 선행 연구다. Section 3의 tree-attention mask 구성 방식과 KV 재사용 조건이 본 연구의 서브트리 hit 판정 로직의 설계 참조가 되었다. 다만 DeFT는 beam search나 speculative decoding과 같이 추론 시 트리 분기가 발생하는 구조를 대상으로 하며, 멀티턴 코딩 에이전트 세션에서 소스 코드 AST를 재사용 단위로 삼는 시나리오는 다루지 않는다.
 
---
 
## 3. KV 압축 및 예산 관리
 
### 3.1 SnapKV
Li et al. (NeurIPS 2024) [65]는 어텐션 스코어 기반으로 중요도가 낮은 KV 슬롯을 제거하는 SOTA 방법이다. 서버급 대형 모델에서는 어텐션 분포가 충분히 집중되어 있어 효과적이나, 소형 모델(Qwen3-Coder-30B 이하)은 어텐션 분포가 상대적으로 균일해 압축 시 정확도 하락 폭이 크다. 본 연구는 SnapKV를 baseline 중 하나로 포함해, AST 인식 재사용과 어텐션 기반 압축의 TTFT·정확도 트레이드오프를 직접 비교한다.
 
### 3.2 PyramidInfer
Yang et al. (ACL 2024) [3]는 레이어별로 KV 예산을 차등 배분해 압축률과 정확도 사이의 균형을 개선했다. 본 연구의 budget merge 설계—어텐션 가중치가 낮은 서브트리의 KV를 attention-weighted 평균 1개로 압축하는 방식—는 PyramidInfer의 레이어별 예산 개념을 참조하되, 서브트리 단위로 적용 범위를 재정의한다.
 
### 3.3 FastGen (Model Tells You What to Discard)
Ge et al. (ICLR 2024) [51]은 모델 자체의 어텐션 패턴을 이용해 KV cache 예산을 적응적으로 결정하는 foundational 방법론이다. Algorithm 1의 adaptive budget 결정 공식과 압축률 대 품질 트레이드오프 곡선은 본 연구의 budget merge ablation 설계에 직접 참조된다.
 
### 3.4 ChunkKV
Liu et al. (arXiv 2025) [23]은 토큰 단위 대신 청크 단위로 KV를 압축하면 semantic 보존에 유리하다는 논거를 제시했다. 청크 경계 설정 방식과 압축률별 pass@1 변화 데이터는 본 연구의 서브트리 토큰 임계값 {4, 8, 16} ablation 설계에 참조된다. 다만 ChunkKV는 정적 청크를 전제하며, α-rename 정규화로 변수명 변화에 invariant한 동적 구조 경계를 정의하는 본 연구와는 근본적으로 접근 방식이 다르다.
 
---
 
## 4. 코드 구조 인식 최적화
 
### 4.1 AI Coders Are among Us
Sun et al. (ISSTA 2024) [56]은 프로그래밍 언어의 grammar 구조를 LLM 코드 생성 효율화에 활용했다. Section 4의 grammar-aware chunking 방식과 코드 품질 평가 결과는 본 연구에서 AST 서브트리 경계 선택의 정당성을 서술하는 근거로 인용된다.
 
### 4.2 Tree-sitter 기반 증분 파싱
본 연구는 Tree-sitter의 증분 파싱(incremental parsing) 기능을 활용해 멀티턴 세션에서 새 도구 출력이 컨텍스트에 추가될 때마다 AST를 실시간으로 갱신한다. 이를 통해 매 턴 전체를 재파싱하는 비용 없이 자격 서브트리 목록을 효율적으로 유지할 수 있다.
 
---
 
## 5. LLM 코딩 에이전트 및 벤치마크
 
### 5.1 SWE-bench / SWE-bench Lite
Yang et al.이 제안한 SWE-bench는 실제 GitHub 이슈를 LLM이 자동 해결하는 능력을 평가하는 벤치마크다. 본 연구는 SWE-bench Lite(300 tasks, 12 repos)에서 repo 균형 샘플러(repo당 최대 2 task, `random.seed(42)`)로 선별한 태스크를 Qwen3-Coder-30B-A3B-FP8 모델과 OpenHands 프레임워크로 실행해 50개 trace를 수집했다(비정상 2개 제외, 유효 48개). 이 trace는 평균 35.9턴, 총 1,721턴으로 구성되며, hit rate 분석과 TTFT 실험의 기반 데이터로 사용된다.
 
### 5.2 LLM Survey
Zhao et al. (Frontiers of Computer Science 2026) [1]은 LLM 및 코딩 에이전트의 최신 동향을 포괄적으로 정리한다. 단순 코드 자동 완성을 넘어 파일 읽기·실행·수정을 반복하는 멀티턴 tool-use 루프로 에이전트가 진화하고 있음을 배경으로 제시한다.
 
---
 
## 6. 선행 연구와의 차별점 요약
 
| 방법 | 동적 경계 | α-rename 정규화 | RoPE 위치 보정 | 코딩 에이전트 세션 |
|------|-----------|-----------------|----------------|-------------------|
| PagedAttention prefix caching [62] | ✗ | ✗ | N/A | ✗ |
| PromptCache [64] | ✗ | ✗ | ✗ | ✗ |
| CacheBlend [63] | ✗ | ✗ | △ (token-level) | ✗ |
| DeFT [59] | ✗ | ✗ | ✗ | ✗ |
| SnapKV [65] | N/A (압축) | ✗ | N/A | ✗ |
| ChunkKV [23] | ✗ | ✗ | ✗ | ✗ |
| **본 연구 (AST-KV)** | **✓ (Tree-sitter)** | **✓ (BLAKE3)** | **✓ (subtree-level)** | **✓ (SWE-bench trace)** |
 
본 연구의 핵심 차별점은 세 가지다. 첫째, AST 서브트리를 **런타임에 자동 추출**되는 동적 재사용 단위로 삼아 정적 스키마 없이도 코딩 에이전트의 도구 출력에 대응한다. 둘째, **α-rename 정규화**로 변수명이 다르지만 구조가 같은 코드 블록을 동일 지문으로 묶어 exact-match 캐시가 포착하지 못하는 반복 패턴을 식별한다—실험 결과 α-rename ON 조건에서 OFF 대비 +9.8%p의 추가 hit가 확인되었다. 셋째, 서브트리 단위 **RoPE re-positioning**으로 위치 불일치로 인한 어텐션 왜곡을 보정한다. 이 세 요소의 교차점을 다룬 선행 연구는 현재까지 발견되지 않았다.
 
---
 
## 참고문헌
 
- [1] Zhao et al., "A Survey of Large Language Models," *Frontiers of Computer Science*, 2026.
- [3] Yang et al., "PyramidInfer: Pyramid KV Cache Compression for High-throughput LLM Inference," *ACL*, 2024.
- [8] Sun et al., "ShadowKV: KV Cache in Shadows for High-Throughput Long-Context LLM Inference," *ICML*, 2024.
- [23] Liu et al., "ChunkKV: Semantic-Preserving KV Cache Compression for Efficient Long-Context LLM Inference," *arXiv*, 2025.
- [51] Ge et al., "Model Tells You What to Discard: Adaptive KV Cache Compression for LLMs," *ICLR*, 2024.
- [56] Sun et al., "AI Coders Are among Us: Rethinking Programming Language Grammar towards Efficient Code Generation," *ISSTA*, 2024.
- [59] Yao et al., "DeFT: Decoding with Flash Tree-attention for Efficient Tree-structured LLM Inference," *ICLR*, 2024.
- [62] Kwon et al., "Efficient Memory Management for Large Language Model Serving with PagedAttention," *SOSP*, 2023.
- [63] Yao et al., "CacheBlend: Fast Large Language Model Serving for RAG with Cached Knowledge Fusion," *EuroSys*, 2025.
- [64] Gim et al., "PromptCache: Modular Attention Reuse for Low-Latency Inference," *MLSys*, 2024.
- [65] Li et al., "SnapKV: LLM Knows What You are Looking for Before Generation," *NeurIPS*, 2024.
 




