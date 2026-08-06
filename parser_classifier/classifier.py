"""
AST Classifier module for Python 2 -> Python 3 migration pipeline (Deploy or Die - Agent A).

Analyzes FunctionAST objects using ast.NodeVisitor to detect Python 2 patterns
and classify functions into 'template', 'llm', or 'skip'.

Owner: Om (Agent A: Parser & Classifier Engine)
Downstream Consumer: Suryansh (Agent B: Converter Engine)
"""

import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set
from parser import FunctionAST


class ClassificationCategory(str, Enum):
    TEMPLATE = "template"
    LLM = "llm"
    SKIP = "skip"


@dataclass
class PatternMatch:
    """Represents a single Python 2 idiom or pattern detected in AST."""

    pattern_id: str
    category: ClassificationCategory
    lineno: int
    col_offset: int
    description: str

    def to_dict(self) -> Dict:
        return {
            "pattern_id": self.pattern_id,
            "category": self.category.value,
            "lineno": self.lineno,
            "col_offset": self.col_offset,
            "description": self.description,
        }


@dataclass
class ClassificationResult:
    """Classification summary for a function definition, serializable for Suryansh (Converter)."""

    function_name: str
    category: ClassificationCategory
    patterns: List[PatternMatch] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "function_name": self.function_name,
            "category": self.category.value,
            "patterns": [p.to_dict() for p in self.patterns],
        }


class Python2PatternVisitor(ast.NodeVisitor):
    """AST Visitor that traverses a function scope to detect Python 2 patterns."""

    # Builtin functions removed or renamed in Py3 (Deterministic / Template)
    REMOVED_BUILTINS = {
        "xrange": "Deprecated Py2 builtin 'xrange' -> 'range'",
        "raw_input": "Deprecated Py2 builtin 'raw_input' -> 'input'",
        "unicode": "Deprecated Py2 type constructor 'unicode' -> 'str'",
        "long": "Deprecated Py2 integer constructor 'long' -> 'int'",
        "unichr": "Deprecated Py2 builtin 'unichr' -> 'chr'",
        "cmp": "Deprecated Py2 builtin 'cmp'",
        "apply": "Deprecated Py2 builtin 'apply'",
        "execfile": "Deprecated Py2 builtin 'execfile'",
        "file": "Deprecated Py2 builtin 'file' -> 'open'",
        "reduce": "Py2 builtin 'reduce' -> moved to 'functools.reduce'",
        "reload": "Py2 builtin 'reload' -> moved to 'importlib.reload'",
    }

    # Removed types/names referenced directly
    REMOVED_NAMES = {
        "basestring": "Deprecated Py2 type 'basestring' -> 'str'",
        "unicode": "Deprecated Py2 type 'unicode' -> 'str'",
        "long": "Deprecated Py2 type 'long' -> 'int'",
        "StandardError": "Deprecated Py2 exception 'StandardError' -> 'Exception'",
    }

    # Legacy Py2 stdlib modules renamed in Py3
    RENAMED_MODULES = {
        "urllib2": "Py2 stdlib 'urllib2' -> 'urllib.request' / 'urllib.error'",
        "urlparse": "Py2 stdlib 'urlparse' -> 'urllib.parse'",
        "ConfigParser": "Py2 stdlib 'ConfigParser' -> 'configparser'",
        "StringIO": "Py2 stdlib 'StringIO' -> 'io.StringIO'",
        "cPickle": "Py2 stdlib 'cPickle' -> 'pickle'",
        "Queue": "Py2 stdlib 'Queue' -> 'queue'",
        "thread": "Py2 stdlib '_thread' / 'threading'",
        "httplib": "Py2 stdlib 'httplib' -> 'http.client'",
        "BaseHTTPServer": "Py2 stdlib 'BaseHTTPServer' -> 'http.server'",
    }

    # Dict methods removed in Py3 (Deterministic / Template)
    DICT_ITER_METHODS = {
        "iteritems": "Legacy dict.iteritems() -> dict.items()",
        "iterkeys": "Legacy dict.iterkeys() -> dict.keys()",
        "itervalues": "Legacy dict.itervalues() -> dict.values()",
        "viewitems": "Legacy dict.viewitems() -> dict.items()",
        "viewkeys": "Legacy dict.viewkeys() -> dict.keys()",
        "viewvalues": "Legacy dict.viewvalues() -> dict.values()",
        "has_key": "Legacy dict.has_key(k) -> k in dict",
    }

    def __init__(self, has_future_division: bool = False):
        super().__init__()
        self.matches: List[PatternMatch] = []
        self.has_future_division = has_future_division
        self._local_vars: Set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # 1. Track arguments to avoid false positives on shadowed names
        for arg in node.args.args:
            self._local_vars.add(arg.arg)

        # 2. Check for @no_migrate decorator
        for decorator in node.decorator_list:
            dec_name = ""
            if isinstance(decorator, ast.Name):
                dec_name = decorator.id
            elif isinstance(decorator, ast.Attribute):
                dec_name = decorator.attr

            if dec_name == "no_migrate":
                self.matches.append(
                    PatternMatch(
                        pattern_id="DECORATOR_NO_MIGRATE",
                        category=ClassificationCategory.SKIP,
                        lineno=node.lineno,
                        col_offset=node.col_offset,
                        description="Function decorated with @no_migrate",
                    )
                )
                return

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        for arg in node.args.args:
            self._local_vars.add(arg.arg)

        for decorator in node.decorator_list:
            dec_name = ""
            if isinstance(decorator, ast.Name):
                dec_name = decorator.id
            elif isinstance(decorator, ast.Attribute):
                dec_name = decorator.attr

            if dec_name == "no_migrate":
                self.matches.append(
                    PatternMatch(
                        pattern_id="DECORATOR_NO_MIGRATE",
                        category=ClassificationCategory.SKIP,
                        lineno=node.lineno,
                        col_offset=node.col_offset,
                        description="Async function decorated with @no_migrate",
                    )
                )
                return

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Ambiguous guardrails: exec/eval calls immediately escalate to LLM
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in {"exec", "eval"}:
                self.matches.append(
                    PatternMatch(
                        pattern_id=f"DYNAMIC_{func_name.upper()}",
                        category=ClassificationCategory.LLM,
                        lineno=node.lineno,
                        col_offset=node.col_offset,
                        description=f"Dynamic code execution via '{func_name}' call",
                    )
                )
            elif func_name in self.REMOVED_BUILTINS and func_name not in self._local_vars:
                self.matches.append(
                    PatternMatch(
                        pattern_id=f"BUILTIN_{func_name.upper()}",
                        category=ClassificationCategory.TEMPLATE,
                        lineno=node.lineno,
                        col_offset=node.col_offset,
                        description=self.REMOVED_BUILTINS[func_name],
                    )
                )

        # Check dict methods calls like d.iteritems() or d.viewitems()
        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name in self.DICT_ITER_METHODS:
                self.matches.append(
                    PatternMatch(
                        pattern_id=f"DICT_{attr_name.upper()}",
                        category=ClassificationCategory.TEMPLATE,
                        lineno=node.lineno,
                        col_offset=node.col_offset,
                        description=self.DICT_ITER_METHODS[attr_name],
                    )
                )

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            if node.id in self.REMOVED_NAMES and node.id not in self._local_vars:
                self.matches.append(
                    PatternMatch(
                        pattern_id=f"TYPE_{node.id.upper()}",
                        category=ClassificationCategory.TEMPLATE,
                        lineno=node.lineno,
                        col_offset=node.col_offset,
                        description=self.REMOVED_NAMES[node.id],
                    )
                )
            elif node.id in self.RENAMED_MODULES and node.id not in self._local_vars:
                self.matches.append(
                    PatternMatch(
                        pattern_id=f"MODULE_{node.id.upper()}",
                        category=ClassificationCategory.TEMPLATE,
                        lineno=node.lineno,
                        col_offset=node.col_offset,
                        description=self.RENAMED_MODULES[node.id],
                    )
                )
            elif node.id == "__metaclass__":
                self.matches.append(
                    PatternMatch(
                        pattern_id="METACLASS_HACK",
                        category=ClassificationCategory.LLM,
                        lineno=node.lineno,
                        col_offset=node.col_offset,
                        description="Legacy Py2 __metaclass__ assignment requiring LLM reasoning",
                    )
                )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        # Check sys.maxint usage
        if isinstance(node.value, ast.Name) and node.value.id == "sys" and node.attr == "maxint":
            self.matches.append(
                PatternMatch(
                    pattern_id="SYS_MAXINT",
                    category=ClassificationCategory.TEMPLATE,
                    lineno=node.lineno,
                    col_offset=node.col_offset,
                    description="Deprecated 'sys.maxint' -> 'sys.maxsize'",
                )
            )
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        # Inspect exception handlers for legacy exceptions (e.g. StandardError)
        if isinstance(node.type, ast.Name) and node.type.id == "StandardError":
            self.matches.append(
                PatternMatch(
                    pattern_id="EXCEPT_STANDARDERROR",
                    category=ClassificationCategory.TEMPLATE,
                    lineno=node.lineno,
                    col_offset=node.col_offset,
                    description="Legacy exception handler catching 'StandardError' -> 'Exception'",
                )
            )
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp):
        # Division '/' operator has ambiguous int vs float division semantics without type inference
        if isinstance(node.op, ast.Div) and not self.has_future_division:
            self.matches.append(
                PatternMatch(
                    pattern_id="AMBIGUOUS_DIVISION",
                    category=ClassificationCategory.LLM,
                    lineno=node.lineno,
                    col_offset=node.col_offset,
                    description="Binary division '/' with unknown runtime operand types",
                )
            )
        self.generic_visit(node)


class FunctionClassifier:
    """Service to evaluate FunctionAST instances and produce ClassificationResult for Suryansh."""

    def __init__(self, has_future_division: bool = False):
        self.has_future_division = has_future_division

    def is_empty_or_abstract(self, func_ast: FunctionAST) -> bool:
        """Checks if function body is empty, pass-only, or docstring-only."""
        node = func_ast.node
        body = node.body
        if not body:
            return True
        if len(body) == 1:
            stmt = body[0]
            if isinstance(stmt, ast.Pass):
                return True
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                return True
        return False

    def classify(self, func_ast: FunctionAST) -> ClassificationResult:
        """Classifies a function definition into 'template', 'llm', or 'skip'."""
        # 1. Check for explicit comment pragmas in raw code or header comments
        combined_text = func_ast.raw_code + "\n" + "\n".join(func_ast.comments)
        if "# py2to3: skip" in combined_text:
            return ClassificationResult(
                function_name=func_ast.name,
                category=ClassificationCategory.SKIP,
                patterns=[],
            )
        if "# py2to3: llm" in combined_text:
            return ClassificationResult(
                function_name=func_ast.name,
                category=ClassificationCategory.LLM,
                patterns=[],
            )

        # 2. Check if abstract/stub
        if self.is_empty_or_abstract(func_ast):
            return ClassificationResult(
                function_name=func_ast.name,
                category=ClassificationCategory.SKIP,
                patterns=[],
            )

        # 3. Visit AST nodes
        visitor = Python2PatternVisitor(has_future_division=self.has_future_division)
        visitor.visit(func_ast.node)
        matches = visitor.matches

        if not matches:
            return ClassificationResult(
                function_name=func_ast.name,
                category=ClassificationCategory.SKIP,
                patterns=[],
            )

        # Check if @no_migrate decorator was matched
        if any(m.pattern_id == "DECORATOR_NO_MIGRATE" for m in matches):
            return ClassificationResult(
                function_name=func_ast.name,
                category=ClassificationCategory.SKIP,
                patterns=matches,
            )

        # Priority resolution: LLM > TEMPLATE > SKIP
        categories = {m.category for m in matches}
        if ClassificationCategory.LLM in categories:
            final_category = ClassificationCategory.LLM
        elif ClassificationCategory.TEMPLATE in categories:
            final_category = ClassificationCategory.TEMPLATE
        else:
            final_category = ClassificationCategory.SKIP

        return ClassificationResult(
            function_name=func_ast.name,
            category=final_category,
            patterns=matches,
        )
