<a id="team-14"></a>
## Team 14 def

| 항목 | 내용 |
|------|------|
| 프로젝트명 | 코딩 에이전트를 위한 AST 기반 kv 재사용 추론 최적화 |
| 서비스명(브랜드) | |
| 트랙 | 연구 |
| 팀명 | def |
| 팀구성 | 서혜원, 신은서, 이재린 |
| 팀지도교수 | 심재형 교수님 |
| 무엇을 만들고자 하는가 | AI 코딩 에이전트가 멀티턴 세션에서 반복적으로 등장하는 코드 블록을 매번 처음부터 재계산하는 문제를 해결한다. 코드의 AST 구조를 활용해 함수·클래스·import 같은 블록 단위로 KV Cache를 재사용하고, 위치가 달라지더라도 RoPE re-positioning으로 보정하여 첫 응답 지연(TTFT)을 줄이는 추론 최적화 레이어를 구현한다.|
| 고객 (누구를 위해) | - 로컬 LLM으로 코딩 에이전트를 운용하는 개인 개발자 / 연구자 <br>- API 비용 대신 온디바이스 추론을 선택한 팀 (스타트업, 보안 민감 조직) <br>- NVIDIA GPU 기반 자체 인프라 운용 조직 |
| Pain Point (해결할 문제) | 코딩 에이전트의 멀티턴 세션에서 매 턴마다 타임스탬프·도구 호출 ID(tool_call_id) 등 동적 메타정보가 프롬프트 앞부분에 삽입된다. 이로 인해 "연속된 앞부분 토큰이 완전히 동일"해야 작동하는 vLLM prefix caching의 hit rate가 12%에 그쳐 매 턴 전체를 재계산(full prefill)하는 상황이 반복된다. 한편 코딩 컨텍스트에는 같은 함수 정의·import 구문이 세션 전반에 걸쳐 반복 등장하는 구조적 패턴이 존재하는데, 기존 prefix caching은 이를 전혀 활용하지 못한다. 결과적으로 멀티턴 세션에서 컨텍스트가 누적될수록 prefill 재계산 비용이 선형 증가하여 TTFT(첫 응답 지연)가 급격히 늘어난다. |
| 사용 기술 | - 에이전트 프레임워크 : OpenHands SDK <br>- Serving layer : vLLM <br>- 모델 : Qwen3-Coder-30B-A3B-FP8, Qwen2.5-Coder-0.5B-Instruct <br>- 타겟 하드웨어 : NVIDIA RTX 5090 × 2장 (VRAM 31.84GB × 2, Linux) <br>- AST 파싱 : Tree-sitter Python 바인딩 (증분 파싱) <br>- 지문 산출 : BLAKE3 해시 (α-rename 정규화 + S-expression 직렬화) <br>- KV Cache 제어 : vLLM block manager 커스터마이징 + RoPE Δ-rotation 모듈 <br>- 벤치마크 : SWE-bench Lite (50 멀티턴 trace, OpenHands 에이전트로 수집) <br>- 평가 지표 : TTFT(ms/턴), AST 서브트리 hit rate(%), Peak KV 메모리(MB)|
| 기대 효과 | - Prefill latency 감소: AST 서브트리 단위 KV Cache 재사용으로 반복 등장하는 코드 블록의 재계산 제거 <br>- 동적 메타정보 문제 해결: tool_call_id·타임스탬프 등으로 인한 prefix 불일치를 우회하여 멀티턴 세션 전반에서 cache hit 유지 <br>- 위치 독립적 재사용: RoPE re-positioning으로 위치가 달라진 서브트리도 KV를 올바르게 재사용 <br>- Long context 환경 대응: 히스토리가 누적되어 컨텍스트 길이가 증가해도 TTFT 선형 증가 억제|
| GitHub Repo | [https://github.com/capstone-2026-ewha/def](https://github.com/capstone-2026-ewha/def) |
| Team Ground Rule | [https://github.com/capstone-2026-ewha/def/blob/main/Team_Ground_Rule.md](https://github.com/capstone-2026-ewha/def/blob/main/Team_Ground_Rule.md) |
| 최종수정일 | 2026-06-01 |
