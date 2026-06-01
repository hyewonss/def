# FAC-KV: 관련 연구 및 차별점

> 2026 Spring Capstone Project — 연구트랙 중간 과제  
> **Related Work 3편 / 우리 팀 연구의 차별점**

---

## 1. Related Work: 참고 논문 3편

### 논문 1. SWE-Pruner: Self-Adaptive Context Pruning for Coding Agents
> Wang et al., *arXiv:2601.16746*, 2026

코딩 에이전트의 SWE-Bench 실행 궤적을 분석했더니 전체 토큰 소비의 **76% 이상이 파일 읽기(read operation)** 에서 발생한다는 실증적 관찰에서 출발한 연구다. 기존 컨텍스트 압축 방법들이 perplexity 같은 고정 지표를 사용하거나 자연어 위주로 설계되어 코드의 구문적·논리적 구조를 손상시키는 문제를 지적한다.

해결책으로 에이전트가 파일을 읽기 전에 현재 목적(Goal Hint, 예: "focus on error handling")을 자연어로 명시하면, 0.6B 파라미터의 경량 neural skimmer가 해당 목표에 관련된 라인만 선별하여 에이전트에게 전달하는 **목표 기반 적응형 pruning** 방식을 제안한다. SWE-Bench Verified 기준 23~54%의 토큰 절감을 달성하면서 성공률을 유지하거나 오히려 개선하는 결과를 보였다.

**핵심 기여:** 에이전트의 현재 목적에 따라 동적으로 컨텍스트를 필터링하여 정보 밀도를 높이는 task-aware pruning 프레임워크.

---

### 논문 2. SWE-ContextBench: A Benchmark for Context Learning in Coding
> Zhu, Hu, Wu, *arXiv:2602.08316*, 2026

기존 코딩 에이전트 벤치마크(SWE-Bench 등)는 각 태스크를 독립적으로 평가하여 **에이전트가 이전 경험이나 컨텍스트를 얼마나 재활용(reuse)할 수 있는지를 전혀 측정하지 않는다**는 문제를 제기한다. 즉, "맞았느냐 틀렸느냐"만 보고, "어떻게 정보를 탐색하고 축적했느냐"는 보지 않는다.

이를 위해 GitHub 이슈와 PR 간의 실제 의존 관계를 기반으로 "연관 태스크 쌍"을 구성한 새 벤치마크를 제안한다. SWE-Bench Lite, Multilingual, Verified를 기반으로 1,100개 기본 태스크 + 376개 연관 태스크로 구성되며, 51개 저장소·9개 언어를 포함한다. 실험 결과 경험 검색과 요약이 성능과 효율성을 동시에 향상시킴을 보였다.

**핵심 기여:** 컨텍스트를 단순히 "잘 검색"하는 능력이 아닌, 과거 경험을 축적하고 재사용하는 능력을 분리해서 평가하는 프레임워크를 최초로 제시.

---

### 논문 3. CodeComp: Structural KV Cache Compression for Agentic Coding
> Chen et al., *arXiv:2604.10235*, 2026

코딩 에이전트가 긴 코드베이스를 처리할 때 KV 캐시가 주요 메모리 병목이 되는데, 기존의 attention score 기반 압축 방법들은 코드에서 의미적으로 중요한 구조적 토큰들(call site, branch condition, assignment 등)을 체계적으로 손실시킨다는 문제를 분석한다.

이를 해결하기 위해 **정적 프로그램 분석(static program analysis)** 을 LLM 추론 과정에 결합한다. Joern이 추출하는 Code Property Graph(CPG)를 prior로 활용하여, 코드 구조적으로 중요한 토큰을 보호하면서 KV 캐시를 압축한다. 추가 학습 없이(training-free) 동작하며, bug localization 및 code generation 벤치마크에서 attention-only 압축 방법들을 일관되게 능가했다.

**핵심 기여:** 코드의 구조(AST, 제어 흐름, 데이터 흐름)를 컨텍스트 압축 기준으로 직접 활용하는 최초의 KV 캐시 압축 프레임워크.

---

### 추가 참고 논문

| 논문 | 핵심 내용 |
|---|---|
| **SideQuest** (arXiv:2602.22603) | 장기 추론 에이전트에서 KV 캐시가 외부 검색 결과로 급격히 늘어나는 문제를, LRM 자신이 "보조 태스크(side quest)"로 KV 중요도를 판단하여 압축. 모델 자신의 추론 능력을 메모리 관리에 활용. |
| **Code Retrieval Survey** (preprints.org) | 렉시컬 검색(grep/ripgrep), 시맨틱 검색(RAG), LSP 통합, 에이전틱 검색, 멀티에이전트 등 코딩 에이전트의 코드 검색 기법 전반을 체계적으로 비교·분석한 탐색적 연구. |

---

## 2. 우리 팀 연구(FAC-KV)의 차별점

### 문제를 바라보는 시각 자체가 다르다

기존 연구들은 모두 **"어떤 토큰/라인/블록이 지금 덜 중요한가"** 라는 관점에서 출발한다.

- SWE-Pruner는 goal hint 기반으로 관련 라인만 골라 넣고,
- CodeComp는 코드 구조를 기준으로 덜 중요한 KV를 지우며,
- SideQuest는 모델 스스로 KV 중요도를 판단해 압축한다.

이들의 공통점은 "무엇을 넣을지, 무엇을 지울지"를 더 잘 결정하는 것이 핵심이라는 점이다. 하지만 이 방향은 한 가지 근본적인 문제를 건드리지 않는다. 압축을 아무리 잘 해도, **매 턴마다 prefill은 여전히 반복된다.**

FAC-KV는 다른 질문에서 출발한다. **"무엇이 반복적으로 읽히는가?"**

코딩 에이전트가 실제로 낭비하는 비용의 본질은, 파일 내용이 전혀 바뀌지 않았는데도 대화 기록이 앞에 추가될 때마다 full prefill이 재실행된다는 점이다. 이는 압축이나 선택의 문제가 아니라, **position 의존성으로 인한 캐시 무효화** 문제다. vLLM을 포함한 기존 시스템의 prefix caching은 요청 간 앞부분이 완전히 일치할 때만 동작하는데, multi-turn agentic 환경에서는 매 턴마다 앞에 대화 기록이 추가되면서 이 조건이 깨진다.

FAC-KV는 **접근 빈도를 추적하여 자주 읽히는 코드 블록의 KV tensor를 GPU 메모리에 고정(pin)** 함으로써, context 내 위치가 바뀌어도 캐시 hit를 유지하는 **position-agnostic** 캐시 레이어를 제안한다. 이는 기존 압축 방법과 경쟁하는 것이 아니라 상호 보완적으로 동작한다. 압축이 "무엇을 넣을지"를 정한다면, FAC-KV는 "넣은 것을 얼마나 효율적으로 재사용할지"를 담당하는 별개의 레이어다.

---

### 우리 팀의 해석과 계획

**우리 팀의 해석**

FAC-KV의 핵심 수요자는 **코딩 에이전트를 직접 개발하거나 연구하는 엔지니어와 연구자**다. 이들은 SWE-Bench 류의 벤치마크를 반복 실행하거나 GitHub 이슈를 자동 해결하는 파이프라인을 운영하면서, 동일한 파일을 여러 턴에 걸쳐 반복해서 읽는 과정에서 매 턴 prefill 비용이 그대로 발생하는 문제를 체감하고 있다. 이들의 불만은 "토큰을 어떻게 줄이느냐"가 아니라 "왜 똑같은 파일인데 매번 다시 계산하지?"에 가깝다. FAC-KV는 바로 이 지점에 응답한다.

선행 연구가 이미 우리 가설에 우호적인 근거를 제공한다. SWE-Pruner는 코딩 에이전트의 전체 토큰 소비 중 76% 이상이 파일 읽기(read operation)에서 발생한다는 점을 실증했다. 이는 반복 참조 패턴이 실제로 존재한다는 것을 시사하며, 캐싱 전략이 효과를 낼 수 있는 구조적 여건이 갖춰져 있음을 의미한다.

**검증하고자 하는 핵심 가설**

현재 FAC-KV는 가설 단계에 있으며, 검증해야 할 핵심 명제는 다음과 같다.

> *"코딩 에이전트의 multi-turn 실행에서, 동일 코드 블록의 KV tensor를 position-agnostic하게 캐싱하면, 정확도 손실 없이 prefill 비용을 유의미하게 줄일 수 있다."*

이를 검증하기 위해 아래 순서로 실험을 설계할 계획이다.

1. **참조 빈도 분석**: SWE-Bench 실행 궤적에서 동일 파일/블록이 몇 턴에 걸쳐 반복 참조되는지 측정하여, 캐싱 가능한 패턴이 실제로 존재하는지 확인한다.
2. **캐시 무효화 지점 측정**: prefix caching이 multi-turn 대화에서 어느 시점에, 어느 비율로 깨지는지 정량화한다.
3. **position-agnostic 캐시 hit율 측정**: FAC-KV 적용 시 캐시 hit가 얼마나 회복되는지, 그에 따른 prefill latency 감소를 측정한다.
4. **정확도 영향 평가**: 캐시 고정이 모델 출력 품질에 미치는 영향을 SWE-Bench resolve rate 기준으로 확인한다.

**PMF 관점에서의 수요 정의**

이 연구의 PMF는 비교적 명확하게 정의할 수 있다. 코딩 에이전트를 반복 실행하는 개발자와 연구자는 추론 비용과 지연 시간에 민감하며, 현재 prefix caching의 한계를 이미 실무에서 경험하고 있다. FAC-KV가 이 문제를 정확도 손실 없이 해결한다면, 기존 압축 방법들과 달리 **추가적인 모델 수정 없이 인프라 레벨에서 바로 적용 가능하다**는 점이 실질적인 채택 유인이 된다. 사용자가 "이 기능이 없어지면 불편하다"고 느끼는 기준, 즉 PMF의 핵심은 반복 실행 비용을 낮추는 것이 에이전트 연구의 실험 속도와 직결된다는 점에 있다.

---

*참고 논문 링크*
- [arXiv:2601.16746](https://arxiv.org/pdf/2601.16746) — SWE-Pruner
- [arXiv:2602.08316](https://arxiv.org/pdf/2602.08316) — SWE-ContextBench
- [arXiv:2604.10235](https://arxiv.org/pdf/2604.10235) — CodeComp
- [arXiv:2602.22603](https://arxiv.org/pdf/2602.22603) — SideQuest
- [preprints.org](https://www.preprints.org/frontend/manuscript/161dfc371faa1178c5426838021ec200/download_pub) — Code Retrieval Survey
