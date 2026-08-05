"""AST Parser module for Python 2 -> Python 3 migration pipeline."""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set, Union


@dataclass
class FunctionAST:
    """Container holding metadata and AST node for a parsed function."""

    name: str
    lineno: int
    end_lineno: int
    node: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    raw_code: str
    comments: List[str] = field(default_factory=list)


@dataclass
class ModuleAST:
    """Container holding module-level metadata and extracted functions."""

    tree: ast.Module
    functions: List[FunctionAST]
    future_imports: Set[str] = field(default_factory=set)


class CodeParser:
    """Parses Python source code into AST and extracts function definitions."""

    @staticmethod
    def normalize_python2_syntax(source: str) -> str:
        
        # Convert statement print to function call print while preserving indentation
        source = re.sub(
            r"^(\s*)print\s+([^\(\n#]+)",
            r"\1print(\2)",
            source,
            flags=re.MULTILINE,
        )
        # Convert legacy except Syntax: except Exc, var: -> except Exc as var:
        source = re.sub(
            r"except\s+([a-zA-Z0-9_\.]+)\s*,\s*([a-zA-Z0-9_]+)\s*:",
            r"except \1 as \2:",
            source,
        )
        # Convert diamond comparison operator <> -> !=
        source = re.sub(r"([^\s<]+)\s*<>\s*([^\s>]+)", r"\1 != \2", source)
        # Convert 2-arg raise statement: raise Exc, msg -> raise Exc(msg)
        source = re.sub(
            r"^(\s*)raise\s+([a-zA-Z0-9_\.]+)\s*,\s*([^\n#]+)",
            r"\1raise \2(\3)",
            source,
            flags=re.MULTILINE,
        )
        return source

    def parse_code(self, source: str) -> ast.Module:
        """Parses source string into a standard ast.Module.

        Falls back to normalization if initial ast.parse encounters a SyntaxError.
        """
        try:
            return ast.parse(source)
        except SyntaxError:
            normalized = self.normalize_python2_syntax(source)
            return ast.parse(normalized)

    def parse_file(self, file_path: Union[str, Path]) -> ast.Module:
        """Reads a file path and parses its contents into an ast.Module."""
        path = Path(file_path)
        source = path.read_text(encoding="utf-8")
        return self.parse_code(source)

    def extract_module(self, source: str) -> ModuleAST:
        """Parses source code into a ModuleAST containing functions and future imports."""
        tree = self.parse_code(source)
        lines = source.splitlines()
        functions: List[FunctionAST] = []
        future_imports: Set[str] = set()

        # Check future imports
        for stmt in tree.body:
            if isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__":
                for alias in stmt.names:
                    future_imports.add(alias.name)

        # Extract function definitions
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start_line = node.lineno
                end_line = getattr(node, "end_lineno", start_line)
                fn_raw = "\n".join(lines[start_line - 1 : end_line])

                # Collect header comments
                fn_comments: List[str] = []
                for idx in range(max(0, start_line - 5), start_line - 1):
                    if idx < len(lines) and lines[idx].strip().startswith("#"):
                        fn_comments.append(lines[idx].strip())

                functions.append(
                    FunctionAST(
                        name=node.name,
                        lineno=start_line,
                        end_lineno=end_line,
                        node=node,
                        raw_code=fn_raw,
                        comments=fn_comments,
                    )
                )

        return ModuleAST(tree=tree, functions=functions, future_imports=future_imports)

    def extract_functions(self, source: str) -> List[FunctionAST]:
        """Convenience method returning extracted function definitions."""
        return self.extract_module(source).functions
