"""LangGraph 워크플로우 시각화 모듈

워크플로우 그래프를 다양한 형식으로 시각화하는 기능을 제공합니다.
단일 책임 원칙: 시각화 기능만 담당합니다.
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

from langgraph.graph.graph import CompiledGraph

from .graph import create_workflow

logger = logging.getLogger(__name__)


def visualize_workflow(workflow: Optional[CompiledGraph] = None, 
                      output_format: str = "mermaid",
                      save_to_file: Optional[str] = None) -> str:
    """워크플로우 그래프를 시각화합니다
    
    Args:
        workflow: 시각화할 워크플로우 (None이면 기본 워크플로우 생성)
        output_format: 출력 형식 ("mermaid", "ascii", "dot")
        save_to_file: 파일로 저장할 경로 (선택적)
        
    Returns:
        시각화된 그래프 문자열
    """
    if workflow is None:
        workflow = create_workflow()
    
    try:
        graph = workflow.get_graph()
        
        if output_format == "mermaid":
            visualization = graph.draw_mermaid()
        elif output_format == "ascii":
            visualization = graph.draw_ascii()
        elif output_format == "dot":
            # GraphViz DOT 형식 (langgraph에서 지원하는 경우)
            if hasattr(graph, 'draw_dot'):
                visualization = graph.draw_dot()
            else:
                logger.warning("DOT 형식이 지원되지 않습니다. Mermaid로 대체합니다.")
                visualization = graph.draw_mermaid()
        else:
            raise ValueError(f"지원되지 않는 형식: {output_format}")
        
        # 파일로 저장
        if save_to_file:
            _save_visualization_to_file(visualization, save_to_file, output_format)
        
        return visualization
        
    except Exception as e:
        logger.error(f"그래프 시각화 오류: {e}")
        return f"시각화 실패: {e}"


def print_workflow_structure(workflow: Optional[CompiledGraph] = None):
    """워크플로우 구조를 콘솔에 출력합니다
    
    Args:
        workflow: 출력할 워크플로우 (None이면 기본 워크플로우 생성)
    """
    if workflow is None:
        workflow = create_workflow()
    
    try:
        graph = workflow.get_graph()
        
        print("\n" + "="*60)
        print("MCP HOST WORKFLOW STRUCTURE")
        print("="*60)
        
        # ASCII 형식으로 출력
        ascii_graph = graph.draw_ascii()
        print(ascii_graph)
        
        # 노드 정보 출력
        print("\n" + "-"*40)
        print("NODES INFORMATION")
        print("-"*40)
        
        nodes = graph.nodes
        for node_id, node_data in nodes.items():
            print(f"• {node_id}")
            if hasattr(node_data, 'func') and hasattr(node_data.func, '__doc__'):
                doc = node_data.func.__doc__
                if doc:
                    first_line = doc.strip().split('\n')[0]
                    print(f"  └─ {first_line}")
        
        # 엣지 정보 출력
        print("\n" + "-"*40)
        print("EDGES INFORMATION")
        print("-"*40)
        
        edges = graph.edges
        for edge in edges:
            if hasattr(edge, 'source') and hasattr(edge, 'target'):
                print(f"• {edge.source} → {edge.target}")
        
        print("="*60 + "\n")
        
    except Exception as e:
        logger.error(f"워크플로우 구조 출력 오류: {e}")
        print(f"구조 출력 실패: {e}")


def export_workflow_mermaid(workflow: Optional[CompiledGraph] = None,
                           output_dir: str = "docs/graphs") -> str:
    """워크플로우를 Mermaid 형식으로 내보냅니다
    
    Args:
        workflow: 내보낼 워크플로우 (None이면 기본 워크플로우 생성)
        output_dir: 출력 디렉토리
        
    Returns:
        생성된 파일 경로
    """
    if workflow is None:
        workflow = create_workflow()
    
    try:
        # Mermaid 다이어그램 생성
        mermaid_content = visualize_workflow(workflow, "mermaid")
        
        # 파일 경로 설정
        output_path = Path(output_dir) / "mcp_workflow.html"
        
        # HTML 파일로 저장
        visualize_workflow(workflow, "mermaid", str(output_path))
        
        # 순수 Mermaid 파일도 저장
        mermaid_path = Path(output_dir) / "mcp_workflow.mmd"
        mermaid_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(mermaid_path, 'w', encoding='utf-8') as f:
            f.write(mermaid_content)
        
        logger.info(f"Mermaid 파일 생성: {mermaid_path}")
        logger.info(f"HTML 파일 생성: {output_path}")
        
        return str(output_path)
        
    except Exception as e:
        logger.error(f"Mermaid 내보내기 오류: {e}")
        return ""


def get_workflow_stats(workflow: Optional[CompiledGraph] = None) -> Dict[str, Any]:
    """워크플로우 통계 정보를 반환합니다
    
    Args:
        workflow: 분석할 워크플로우 (None이면 기본 워크플로우 생성)
        
    Returns:
        워크플로우 통계 정보
    """
    if workflow is None:
        workflow = create_workflow()
    
    try:
        graph = workflow.get_graph()
        
        # 노드 분석
        nodes = graph.nodes
        node_types = {}
        for node_id, node_data in nodes.items():
            node_type = type(node_data).__name__
            node_types[node_type] = node_types.get(node_type, 0) + 1
        
        # 엣지 분석
        edges = graph.edges
        edge_count = len(edges)
        
        # 조건부 엣지 찾기
        conditional_edges = 0
        for edge in edges:
            if hasattr(edge, 'condition') or 'conditional' in str(type(edge)).lower():
                conditional_edges += 1
        
        return {
            "total_nodes": len(nodes),
            "total_edges": edge_count,
            "conditional_edges": conditional_edges,
            "node_types": node_types,
            "start_node": getattr(graph, 'first_node', 'Unknown'),
            "end_nodes": [node for node in nodes if 'END' in str(node)]
        }
        
    except Exception as e:
        logger.error(f"워크플로우 통계 수집 오류: {e}")
        return {"error": str(e)}


def create_workflow_documentation(workflow: Optional[CompiledGraph] = None,
                                 output_file: str = "docs/workflow_documentation.md") -> str:
    """워크플로우 문서를 마크다운 형식으로 생성합니다
    
    Args:
        workflow: 문서화할 워크플로우 (None이면 기본 워크플로우 생성)
        output_file: 출력 파일 경로
        
    Returns:
        생성된 문서 파일 경로
    """
    if workflow is None:
        workflow = create_workflow()
    
    try:
        graph = workflow.get_graph()
        stats = get_workflow_stats(workflow)
        
        # 마크다운 문서 생성
        doc_content = []
        doc_content.append("# MCP Host 워크플로우 문서\n")
        doc_content.append("## 개요\n")
        doc_content.append("LangGraph를 사용하여 구성된 MCP Host의 대화형 워크플로우입니다.\n")
        
        # 통계 정보
        doc_content.append("## 워크플로우 통계\n")
        doc_content.append(f"- **총 노드 수**: {stats['total_nodes']}")
        doc_content.append(f"- **총 엣지 수**: {stats['total_edges']}")
        doc_content.append(f"- **조건부 엣지 수**: {stats['conditional_edges']}")
        doc_content.append(f"- **시작 노드**: {stats['start_node']}")
        doc_content.append(f"- **종료 노드**: {', '.join(map(str, stats['end_nodes']))}\n")
        
        # 노드 타입 분포
        if stats['node_types']:
            doc_content.append("### 노드 타입 분포\n")
            for node_type, count in stats['node_types'].items():
                doc_content.append(f"- **{node_type}**: {count}개")
            doc_content.append("")
        
        # 노드 상세 정보
        doc_content.append("## 노드 상세 정보\n")
        nodes = graph.nodes
        for node_id, node_data in nodes.items():
            doc_content.append(f"### {node_id}\n")
            
            # 함수 문서화 문자열 추가
            if hasattr(node_data, 'func') and hasattr(node_data.func, '__doc__'):
                doc = node_data.func.__doc__
                if doc:
                    doc_content.append(f"**설명**: {doc.strip().split(chr(10))[0]}\n")
            
            doc_content.append(f"**타입**: {type(node_data).__name__}\n")
        
        # Mermaid 다이어그램 추가
        doc_content.append("## 워크플로우 다이어그램\n")
        doc_content.append("```mermaid")
        mermaid_content = visualize_workflow(workflow, "mermaid")
        doc_content.append(mermaid_content)
        doc_content.append("```\n")
        
        # 파일로 저장
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(doc_content))
        
        logger.info(f"워크플로우 문서 생성: {output_path}")
        return str(output_path)
        
    except Exception as e:
        logger.error(f"워크플로우 문서 생성 오류: {e}")
        return ""


def _save_visualization_to_file(visualization: str, file_path: str, output_format: str):
    """시각화 결과를 파일로 저장합니다 (내부 함수)
    
    Args:
        visualization: 시각화 문자열
        file_path: 저장할 파일 경로
        output_format: 출력 형식
    """
    output_path = Path(file_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        if output_format == "mermaid":
            # Mermaid HTML 래퍼 추가
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>MCP Host Workflow Graph</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .mermaid {{ text-align: center; }}
        h1 {{ color: #4d4d4d; text-align: center; font-size: 16px; }}
    </style>
</head>
<body>
    <h1>MCP Host 워크플로우</h1>
    <div class="mermaid">
{visualization}
    </div>
    <script>
        mermaid.initialize({{startOnLoad: true, theme: 'default'}});
    </script>
</body>
</html>"""
            f.write(html_content)
            logger.info(f"Mermaid HTML 파일 저장: {output_path}")
        else:
            f.write(visualization)
            logger.info(f"그래프 파일 저장: {output_path}") 