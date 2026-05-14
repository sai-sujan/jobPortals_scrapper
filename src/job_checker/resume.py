import re
import zipfile
from pathlib import Path
from typing import List
from xml.etree import ElementTree


def extract_docx_text(path: Path) -> str:
    """Read visible text from a .docx file without external dependencies."""
    with zipfile.ZipFile(path) as docx:
        xml = docx.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    text_nodes: List[str] = []
    for node in root.iter():
        if node.tag.endswith("}t") and node.text:
            text_nodes.append(node.text)
    return "\n".join(text_nodes)


def extract_resume_terms(text: str) -> List[str]:
    terms = [
        "python",
        "django",
        "django rest framework",
        "fastapi",
        "flask",
        "restful api",
        "microservices",
        "sqlalchemy",
        "pydantic",
        "llm",
        "rag",
        "openai api",
        "langchain",
        "prompt engineering",
        "embeddings",
        "faiss",
        "vector search",
        "semantic search",
        "scikit-learn",
        "etl",
        "pandas",
        "numpy",
        "aws",
        "azure",
        "gcp",
        "docker",
        "jenkins",
        "linux",
    ]
    lowered = re.sub(r"\s+", " ", text.lower())
    return [term for term in terms if term in lowered]
