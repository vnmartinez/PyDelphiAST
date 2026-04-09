"""Tests for the Delphi PAS/DFM parsers."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import pydelphiast as pda
from pydelphiast.parsers.pas_parser import parse_pas
from pydelphiast.parsers.dfm_parser import parse_dfm

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _json_roundtrip(ast: dict) -> dict:
    """Verify the AST is JSON-serialisable and return the round-tripped value."""
    return json.loads(json.dumps(ast, default=str))


# ---------------------------------------------------------------------------
# Unit structure
# ---------------------------------------------------------------------------

class TestUnitStructure:
    def test_minimal_unit(self):
        src = "unit Foo; interface implementation end."
        ast = parse_pas(src)
        assert ast["kind"] == "Unit"
        assert ast["name"] == "Foo"
        assert ast["interface"]["kind"] == "InterfaceSection"
        assert ast["implementation"]["kind"] == "ImplementationSection"

    def test_unit_with_uses(self):
        src = "unit Foo; interface uses SysUtils; implementation end."
        ast = parse_pas(src)
        uses = ast["interface"]["uses"]
        assert uses["kind"] == "UsesClause"
        assert uses["items"][0]["name"] == "SysUtils"

    def test_unit_name_dotted(self):
        src = "unit Vcl.Forms; interface implementation end."
        ast = parse_pas(src)
        assert ast["name"] == "Vcl.Forms"

    def test_program(self):
        src = "program Foo; begin end."
        ast = parse_pas(src)
        assert ast["kind"] == "Program"
        assert ast["name"] == "Foo"

    def test_library(self):
        src = "library Foo; exports Bar; begin end."
        ast = parse_pas(src)
        assert ast["kind"] == "Library"


# ---------------------------------------------------------------------------
# Type declarations
# ---------------------------------------------------------------------------

class TestTypeDeclarations:
    def _unit(self, type_body: str) -> dict:
        src = f"unit T; interface type {type_body} implementation end."
        return parse_pas(src)

    def test_enum(self):
        ast = self._unit("TColor = (Red, Green, Blue);")
        sec = ast["interface"]["declarations"][0]
        td = sec["items"][0]
        assert td["kind"] == "TypeDecl"
        assert td["name"] == "TColor"
        assert td["typeDefinition"]["kind"] == "EnumType"
        assert len(td["typeDefinition"]["values"]) == 3

    def test_subrange(self):
        ast = self._unit("TSmall = 1..10;")
        td = ast["interface"]["declarations"][0]["items"][0]
        assert td["typeDefinition"]["kind"] == "SubrangeType"

    def test_set_of_enum(self):
        ast = self._unit("TColors = set of TColor;")
        td = ast["interface"]["declarations"][0]["items"][0]
        assert td["typeDefinition"]["kind"] == "SetType"

    def test_array(self):
        ast = self._unit("TArr = array[0..9] of Integer;")
        td = ast["interface"]["declarations"][0]["items"][0]
        assert td["typeDefinition"]["kind"] == "ArrayType"

    def test_open_array_type(self):
        ast = self._unit("TOpenArr = array of String;")
        td = ast["interface"]["declarations"][0]["items"][0]
        assert td["typeDefinition"]["kind"] == "ArrayType"

    def test_record(self):
        ast = self._unit("TPoint = record X, Y: Double; end;")
        td = ast["interface"]["declarations"][0]["items"][0]
        assert td["typeDefinition"]["kind"] == "RecordType"
        assert len(td["typeDefinition"]["fields"]) == 1

    def test_pointer(self):
        ast = self._unit("PInteger = ^Integer;")
        td = ast["interface"]["declarations"][0]["items"][0]
        assert td["typeDefinition"]["kind"] == "PointerType"

    def test_proc_type(self):
        ast = self._unit("TCallback = procedure(Sender: TObject) of object;")
        td = ast["interface"]["declarations"][0]["items"][0]
        pt = td["typeDefinition"]
        assert pt["kind"] == "ProcType"
        assert pt["ofObject"] is True

    def test_func_type(self):
        ast = self._unit("TGetter = function: Integer;")
        td = ast["interface"]["declarations"][0]["items"][0]
        pt = td["typeDefinition"]
        assert pt["kind"] == "ProcType"
        assert pt["isFunction"] is True

    def test_class_simple(self):
        src = """
        unit T; interface
        type TFoo = class
        private
          FX: Integer;
        public
          procedure DoIt;
        end;
        implementation end.
        """
        ast = parse_pas(src)
        td = ast["interface"]["declarations"][0]["items"][0]
        ct = td["typeDefinition"]
        assert ct["kind"] == "ClassType"
        members = ct["members"]
        assert any(m.get("kind") == "MethodDecl" for m in members)
        assert any(m.get("kind") == "FieldDecl" for m in members)

    def test_class_with_ancestors(self):
        src = """
        unit T; interface
        type TDog = class(TAnimal, ISerializable)
        end;
        implementation end.
        """
        ast = parse_pas(src)
        ct = ast["interface"]["declarations"][0]["items"][0]["typeDefinition"]
        assert len(ct["ancestors"]) == 2

    def test_interface_type(self):
        src = """
        unit T; interface
        type IFoo = interface
          ['{00000000-0000-0000-0000-000000000000}']
          procedure DoIt;
        end;
        implementation end.
        """
        ast = parse_pas(src)
        it = ast["interface"]["declarations"][0]["items"][0]["typeDefinition"]
        assert it["kind"] == "InterfaceType"
        assert it.get("guid") is not None


# ---------------------------------------------------------------------------
# Const / Var sections
# ---------------------------------------------------------------------------

class TestConstVarSections:
    def _decl(self, body: str) -> list:
        src = f"unit T; interface {body} implementation end."
        return parse_pas(src)["interface"]["declarations"]

    def test_simple_const(self):
        decls = self._decl("const MAX = 100;")
        assert decls[0]["kind"] == "ConstSection"
        assert decls[0]["items"][0]["name"] == "MAX"

    def test_typed_const(self):
        decls = self._decl("const S: string = 'hello';")
        item = decls[0]["items"][0]
        assert item["kind"] == "TypedConstDecl"

    def test_var_decl(self):
        decls = self._decl("var Count: Integer;")
        assert decls[0]["kind"] == "VarSection"
        assert decls[0]["items"][0]["names"] == ["Count"]

    def test_var_multi_name(self):
        decls = self._decl("var X, Y: Double;")
        item = decls[0]["items"][0]
        assert item["names"] == ["X", "Y"]


# ---------------------------------------------------------------------------
# Routine declarations
# ---------------------------------------------------------------------------

class TestRoutineDeclarations:
    def test_procedure_header(self):
        src = """unit T; interface
        procedure Foo(X: Integer);
        implementation end."""
        ast = parse_pas(src)
        decls = ast["interface"]["declarations"]
        r = decls[0]
        assert r["kind"] == "RoutineDecl"
        assert r["name"] == "Foo"
        assert r["kind"] == "RoutineDecl"

    def test_function_header(self):
        src = """unit T; interface
        function Add(A, B: Integer): Integer;
        implementation end."""
        ast = parse_pas(src)
        r = ast["interface"]["declarations"][0]
        assert r["returnType"]["name"] == "Integer"

    def test_routine_implementation(self):
        src = """unit T; interface
        function Add(A, B: Integer): Integer;
        implementation
        function Add(A, B: Integer): Integer;
        begin
          Result := A + B;
        end;
        end."""
        ast = parse_pas(src)
        impl_decls = ast["implementation"]["declarations"]
        r = impl_decls[0]
        assert r["body"] is not None
        assert r["body"]["block"]["kind"] == "Block"


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

class TestStatements:
    def _stmts(self, body: str) -> list:
        src = f"""unit T; interface implementation
        procedure Foo;
        begin {body} end;
        end."""
        ast = parse_pas(src)
        r = ast["implementation"]["declarations"][0]
        return r["body"]["block"]["statements"]

    def test_assignment(self):
        stmts = self._stmts("X := 42;")
        assert stmts[0]["kind"] == "AssignStmt"

    def test_if_then(self):
        stmts = self._stmts("if X > 0 then Y := 1;")
        assert stmts[0]["kind"] == "IfStmt"
        assert stmts[0]["elseStmt"] is None

    def test_if_then_else(self):
        stmts = self._stmts("if X > 0 then Y := 1 else Y := 2;")
        s = stmts[0]
        assert s["kind"] == "IfStmt"
        assert s["elseStmt"] is not None

    def test_for_to(self):
        stmts = self._stmts("for I := 1 to 10 do Inc(I);")
        assert stmts[0]["kind"] == "ForStmt"
        assert stmts[0]["direction"] == "to"

    def test_for_downto(self):
        stmts = self._stmts("for I := 10 downto 1 do Dec(I);")
        assert stmts[0]["direction"] == "downto"

    def test_while(self):
        stmts = self._stmts("while I < 10 do Inc(I);")
        assert stmts[0]["kind"] == "WhileStmt"

    def test_repeat(self):
        stmts = self._stmts("repeat Inc(I); until I = 10;")
        assert stmts[0]["kind"] == "RepeatStmt"

    def test_case(self):
        stmts = self._stmts("case X of 1: Y := 1; 2: Y := 2; end;")
        assert stmts[0]["kind"] == "CaseStmt"
        assert len(stmts[0]["items"]) == 2

    def test_try_except(self):
        stmts = self._stmts("try X := 1; except on E: Exception do; end;")
        assert stmts[0]["kind"] == "TryExceptStmt"

    def test_try_finally(self):
        stmts = self._stmts("try X := 1; finally X := 0; end;")
        assert stmts[0]["kind"] == "TryFinallyStmt"

    def test_with(self):
        stmts = self._stmts("with Obj do Inc(X);")
        assert stmts[0]["kind"] == "WithStmt"

    def test_raise(self):
        stmts = self._stmts("raise EFoo.Create('oops');")
        assert stmts[0]["kind"] == "RaiseStmt"

    def test_nested_begin(self):
        stmts = self._stmts("begin X := 1; Y := 2; end;")
        assert stmts[0]["kind"] == "Block"


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------

class TestExpressions:
    def _expr(self, expr_src: str) -> dict:
        src = f"unit T; interface implementation procedure F; begin X := {expr_src}; end; end."
        ast = parse_pas(src)
        stmt = ast["implementation"]["declarations"][0]["body"]["block"]["statements"][0]
        return stmt["value"]

    def test_integer_literal(self):
        e = self._expr("42")
        assert e["kind"] == "IntegerLiteral"
        assert e["value"] == "42"

    def test_string_literal(self):
        e = self._expr("'hello'")
        assert e["kind"] == "StringLiteral"

    def test_nil(self):
        e = self._expr("nil")
        assert e["kind"] == "NilLiteral"

    def test_binary_plus(self):
        e = self._expr("A + B")
        assert e["kind"] == "BinaryExpr"
        assert e["operator"] == "+"

    def test_binary_comparison(self):
        e = self._expr("A > B")
        assert e["kind"] == "BinaryExpr"
        assert e["operator"] == ">"

    def test_unary_not(self):
        e = self._expr("not A")
        assert e["kind"] == "UnaryExpr"
        assert e["operator"] == "not"

    def test_call_expr(self):
        e = self._expr("Foo(1, 2)")
        assert e["kind"] == "CallExpr"
        assert len(e["args"]) == 2

    def test_member_access(self):
        e = self._expr("Obj.Field")
        assert e["kind"] == "MemberAccess"
        assert e["member"] == "Field"

    def test_index_expr(self):
        e = self._expr("Arr[0]")
        assert e["kind"] == "IndexExpr"

    def test_set_constructor(self):
        e = self._expr("[1, 2, 3]")
        assert e["kind"] == "SetConstructor"
        assert len(e["elements"]) == 3

    def test_paren_expr(self):
        e = self._expr("(A + B)")
        assert e["kind"] == "ParenExpr"


# ---------------------------------------------------------------------------
# Full fixture file
# ---------------------------------------------------------------------------

class TestFixtures:
    def test_simple_pas(self):
        path = FIXTURES / "simple.pas"
        ast = pda.parse_file(str(path), include_forms=False)
        assert ast["kind"] == "Unit"
        assert ast["name"] == "SimpleUnit"
        # JSON-serialisable
        _json_roundtrip(ast)

    def test_project_dpr(self):
        path = FIXTURES / "project.dpr"
        ast = pda.parse_file(str(path), include_forms=False)
        assert ast["kind"] == "Program"
        assert ast["name"] == "MyProject"
        _json_roundtrip(ast)

    def test_form_dfm(self):
        path = FIXTURES / "form.dfm"
        ast = pda.parse_file(str(path))
        assert ast["kind"] == "DfmObject"
        assert ast["name"] == "MainForm"
        assert ast["className"] == "TMainForm"
        _json_roundtrip(ast)


# ---------------------------------------------------------------------------
# DFM parser
# ---------------------------------------------------------------------------

class TestDfmParser:
    def test_minimal_object(self):
        src = "object Foo: TFoo\n  X = 1\nend"
        ast = parse_dfm(src)
        assert ast["kind"] == "DfmObject"
        assert ast["name"] == "Foo"
        assert ast["className"] == "TFoo"

    def test_nested_object(self):
        src = (
            "object Form1: TForm1\n"
            "  object Button1: TButton\n"
            "    Caption = 'OK'\n"
            "  end\n"
            "end"
        )
        ast = parse_dfm(src)
        assert len(ast["children"]) == 1
        assert ast["children"][0]["className"] == "TButton"

    def test_integer_property(self):
        src = "object F: TF\n  Left = 100\nend"
        ast = parse_dfm(src)
        prop = ast["properties"][0]
        assert prop["name"] == "Left"
        assert prop["value"] == 100

    def test_string_property(self):
        src = "object F: TF\n  Caption = 'Hello'\nend"
        ast = parse_dfm(src)
        prop = ast["properties"][0]
        assert "'Hello'" in str(prop["value"]) or prop["value"] == "'Hello'"

    def test_set_property(self):
        src = "object F: TF\n  Anchors = [akLeft, akTop]\nend"
        ast = parse_dfm(src)
        prop = ast["properties"][0]
        assert prop["value"]["kind"] == "DfmSet"
        assert "akLeft" in prop["value"]["items"]


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

class TestJsonOutput:
    def test_to_json(self):
        ast = parse_pas("unit T; interface implementation end.")
        text = pda.to_json(ast)
        reloaded = json.loads(text)
        assert reloaded["kind"] == "Unit"

    def test_parse_source_pas(self):
        ast = pda.parse_source("unit T; interface implementation end.", "T.pas")
        assert ast["kind"] == "Unit"

    def test_parse_source_dfm(self):
        ast = pda.parse_source("object F: TF\nend", "F.dfm")
        assert ast["kind"] == "DfmObject"
