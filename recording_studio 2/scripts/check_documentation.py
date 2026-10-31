"""Comprueba que cada módulo, clase y función Python tenga documentación de propósito."""
import ast
from pathlib import Path


def check(root):
    """Devuelve ubicaciones sin docstring; omite entornos virtuales y archivos generados."""
    missing=[]
    for folder in ("recording_studio","tests","examples","scripts"):
        for path in (root/folder).rglob("*.py"):
            tree=ast.parse(path.read_text(encoding="utf-8"))
            if not ast.get_docstring(tree):missing.append(f"{path.relative_to(root)}:1 module")
            for node in ast.walk(tree):
                if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) and not ast.get_docstring(node):
                    missing.append(f"{path.relative_to(root)}:{node.lineno} {node.name}")
    return missing


if __name__=="__main__":
    problems=check(Path(__file__).resolve().parents[1])
    if problems:raise SystemExit("\n".join(problems))
    print("Todos los módulos, clases y funciones Python tienen docstrings de propósito.")
