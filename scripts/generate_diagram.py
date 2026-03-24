"""Co-Scientist Agent 시스템 아키텍처 다이어그램 생성 (Graphviz)."""
import os
import graphviz

os.environ["PATH"] += os.pathsep + r"C:\Program Files\Graphviz\bin"

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── 메인 시스템 흐름도 ──
dot = graphviz.Digraph(
    "Co-Scientist Agent Architecture",
    format="png",
    engine="dot",
    graph_attr={
        "rankdir": "TB",
        "bgcolor": "#FAFAFA",
        "fontname": "Malgun Gothic",
        "fontsize": "14",
        "pad": "0.5",
        "dpi": "150",
        "label": "Co-Scientist Agent — 시스템 아키텍처\n(Display R&D 논문 지원 시스템)",
        "labelloc": "t",
        "labeljust": "c",
        "fontcolor": "#1a1a2e",
    },
    node_attr={
        "fontname": "Malgun Gothic",
        "fontsize": "11",
        "style": "filled",
        "penwidth": "1.5",
    },
    edge_attr={
        "fontname": "Malgun Gothic",
        "fontsize": "9",
        "color": "#555555",
    },
)

# ── 사용자 인터페이스 ──
with dot.subgraph(name="cluster_ui") as c:
    c.attr(label="사용자 인터페이스", style="dashed,rounded", color="#888888", fontcolor="#555555")
    c.node("user", "👤 사용자\n(연구원)", shape="ellipse", fillcolor="#E8F5E9", color="#4CAF50")
    c.node("webui", "Open WebUI\n(Chat UI)", shape="box", fillcolor="#E3F2FD", color="#2196F3")
    c.node("cli", "CLI\n(scripts/cli.py)", shape="box", fillcolor="#E3F2FD", color="#2196F3")

# ── FastAPI 서버 ──
with dot.subgraph(name="cluster_api") as c:
    c.attr(label="FastAPI 서버 (Port 20035)", style="filled,rounded", color="#1565C0", fillcolor="#E8EAF6", fontcolor="#1565C0")
    c.node("chat_api", "/api/chat\n(Chat API)", shape="box", fillcolor="#C5CAE9", color="#3F51B5")
    c.node("openai_api", "/v1/chat/completions\n(OpenAI-compat)", shape="box", fillcolor="#C5CAE9", color="#3F51B5")
    c.node("doc_api", "/api/documents\n(Documents)", shape="box", fillcolor="#C5CAE9", color="#3F51B5")

# ── Supervisor 파이프라인 ──
with dot.subgraph(name="cluster_supervisor") as c:
    c.attr(label="Supervisor 파이프라인 (LangGraph)", style="filled,rounded", color="#E65100", fillcolor="#FFF3E0", fontcolor="#E65100")
    c.node("extract_dates", "① 날짜 추출\n(Regex 파서)", shape="box", fillcolor="#FFE0B2", color="#FF9800")
    c.node("extract_cond", "② 조건 추출\n(LLM 기반)", shape="box", fillcolor="#FFE0B2", color="#FF9800")
    c.node("classify", "③ 의도 분류\n(LLM 분류기)", shape="box", fillcolor="#FFE0B2", color="#FF9800")
    c.node("route", "④ 에이전트 라우팅", shape="diamond", fillcolor="#FFCC80", color="#F57C00")
    c.node("citation", "⑤ 참조/저작권 추가", shape="box", fillcolor="#FFE0B2", color="#FF9800")

# ── 14개 에이전트 (Phase별) ──
with dot.subgraph(name="cluster_phase1") as c:
    c.attr(label="Phase 1: 기본 검색/분석", style="filled,rounded", color="#2E7D32", fillcolor="#E8F5E9", fontcolor="#2E7D32")
    c.node("paper_qa", "Paper QA\n(논문 검색/Q&A)", shape="box", fillcolor="#C8E6C9", color="#4CAF50")
    c.node("lit_survey", "Literature Survey\n(문헌 리뷰)", shape="box", fillcolor="#C8E6C9", color="#4CAF50")
    c.node("deep_dive", "Paper Deep Dive\n(심층 분석)", shape="box", fillcolor="#C8E6C9", color="#4CAF50")
    c.node("analytics", "Analytics\n(통계/집계)", shape="box", fillcolor="#C8E6C9", color="#4CAF50")

with dot.subgraph(name="cluster_phase2") as c:
    c.attr(label="Phase 2: 아이디어 발굴", style="filled,rounded", color="#1565C0", fillcolor="#E3F2FD", fontcolor="#1565C0")
    c.node("idea_gen", "Idea Generator\n(연구 아이디어)", shape="box", fillcolor="#BBDEFB", color="#2196F3")
    c.node("cross_domain", "Cross Domain\n(타 분야 적용)", shape="box", fillcolor="#BBDEFB", color="#2196F3")
    c.node("trend", "Trend Analyzer\n(트렌드 분석)", shape="box", fillcolor="#BBDEFB", color="#2196F3")

with dot.subgraph(name="cluster_phase3") as c:
    c.attr(label="Phase 3: 실험/전략", style="filled,rounded", color="#6A1B9A", fillcolor="#F3E5F5", fontcolor="#6A1B9A")
    c.node("experiment", "Experiment Planner\n(실험 설계)", shape="box", fillcolor="#E1BEE7", color="#9C27B0")
    c.node("patent", "Patent Landscaper\n(특허 분석)", shape="box", fillcolor="#E1BEE7", color="#9C27B0")
    c.node("competitive", "Competitive Intel\n(경쟁사 분석)", shape="box", fillcolor="#E1BEE7", color="#9C27B0")
    c.node("material", "Material Advisor\n(재료/공정 비교)", shape="box", fillcolor="#E1BEE7", color="#9C27B0")

with dot.subgraph(name="cluster_phase4") as c:
    c.attr(label="Phase 4: 산출물 생성", style="filled,rounded", color="#C62828", fillcolor="#FFEBEE", fontcolor="#C62828")
    c.node("report", "Report Drafter\n(보고서 초안)", shape="box", fillcolor="#FFCDD2", color="#F44336")
    c.node("peer_review", "Peer Review\n(가상 리뷰)", shape="box", fillcolor="#FFCDD2", color="#F44336")
    c.node("knowledge", "Knowledge Connector\n(전문가 매칭)", shape="box", fillcolor="#FFCDD2", color="#F44336")

# ── 데이터 저장소 ──
with dot.subgraph(name="cluster_data") as c:
    c.attr(label="데이터 저장소", style="filled,rounded", color="#37474F", fillcolor="#ECEFF1", fontcolor="#37474F")
    c.node("milvus", "Milvus\n(벡터 DB)\n의미 검색 / RAG", shape="cylinder", fillcolor="#B0BEC5", color="#607D8B")
    c.node("mariadb", "MariaDB\n(관계형 DB)\n통계 / 집계", shape="cylinder", fillcolor="#B0BEC5", color="#607D8B")

# ── 외부 서비스 ──
with dot.subgraph(name="cluster_ext") as c:
    c.attr(label="외부 서비스", style="filled,rounded", color="#795548", fillcolor="#EFEBE9", fontcolor="#795548")
    c.node("llm_svc", "LLM 서버\n(vLLM / LM Studio)\nOpenAI-compatible API", shape="box3d", fillcolor="#D7CCC8", color="#795548")
    c.node("embed_svc", "Embedding 서버\n(TEI / LM Studio)\nOpenAI-compatible API", shape="box3d", fillcolor="#D7CCC8", color="#795548")
    c.node("langfuse", "Langfuse\n(트레이싱/관측)", shape="box3d", fillcolor="#D7CCC8", color="#795548")

# ── 엣지 연결 ──
# 사용자 → API
dot.edge("user", "webui", "질문")
dot.edge("user", "cli", "질문")
dot.edge("webui", "openai_api", "HTTP")
dot.edge("cli", "chat_api", "HTTP")

# API → Supervisor
dot.edge("chat_api", "extract_dates", "AgentState")
dot.edge("openai_api", "extract_dates", "AgentState")

# Supervisor 파이프라인
dot.edge("extract_dates", "extract_cond", "", color="#E65100", penwidth="2")
dot.edge("extract_cond", "classify", "", color="#E65100", penwidth="2")
dot.edge("classify", "route", "", color="#E65100", penwidth="2")

# 라우팅 → 에이전트
for agent_id in ["paper_qa", "lit_survey", "deep_dive", "analytics",
                  "idea_gen", "cross_domain", "trend",
                  "experiment", "patent", "competitive", "material",
                  "report", "peer_review", "knowledge"]:
    dot.edge("route", agent_id, "", color="#F57C00", style="dashed", penwidth="0.8")

# 에이전트 → Citation
for agent_id in ["paper_qa", "lit_survey", "deep_dive", "analytics",
                  "idea_gen", "cross_domain", "trend",
                  "experiment", "patent", "competitive", "material",
                  "report", "peer_review", "knowledge"]:
    dot.edge(agent_id, "citation", "", color="#999999", style="dotted", penwidth="0.5")

# 에이전트 → 데이터/서비스
dot.edge("paper_qa", "milvus", "벡터 검색", color="#607D8B")
dot.edge("paper_qa", "mariadb", "원문 조회", color="#607D8B")
dot.edge("lit_survey", "milvus", "검색", color="#607D8B")
dot.edge("deep_dive", "mariadb", "원문 조회", color="#607D8B")
dot.edge("analytics", "mariadb", "SQL 집계", color="#607D8B", penwidth="2")
dot.edge("trend", "milvus", "검색", color="#607D8B")

# LLM/Embedding 연결
dot.edge("extract_cond", "llm_svc", "JSON 추출", color="#795548", style="dashed")
dot.edge("classify", "llm_svc", "의도 분류", color="#795548", style="dashed")
dot.edge("paper_qa", "llm_svc", "답변 생성", color="#795548", style="dashed")
dot.edge("paper_qa", "embed_svc", "쿼리 임베딩", color="#795548", style="dashed")

# Langfuse
dot.edge("chat_api", "langfuse", "트레이싱", color="#795548", style="dotted")

# 응답
dot.edge("citation", "chat_api", "응답\n{answer, sources}", color="#1565C0", penwidth="2")

# 렌더링
output_path = os.path.join(OUTPUT_DIR, "architecture")
dot.render(output_path, cleanup=True)
print(f"Diagram saved: {output_path}.png")
