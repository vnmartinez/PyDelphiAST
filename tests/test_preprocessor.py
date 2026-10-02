"""Tests for Delphi conditional compilation preprocessor and encoding detection."""

import os
import tempfile
import pytest

import pydelphiast as pda
from pydelphiast.lexer import tokenize
from pydelphiast.preprocessor import preprocess_tokens
from pydelphiast.project import read_source
from pydelphiast.tokens import TT


# ---------------------------------------------------------------------------
# Encoding detection tests
# ---------------------------------------------------------------------------

class TestEncodingDetection:
    def test_read_utf8_without_bom(self, tmp_path):
        f = tmp_path / "unit_utf8.pas"
        content = "unit UnitUtf8; // módulo de teste"
        f.write_text(content, encoding="utf-8")
        assert read_source(str(f)) == content

    def test_read_utf8_with_bom(self, tmp_path):
        f = tmp_path / "unit_bom.pas"
        content = "unit UnitBom; // módulo de teste"
        f.write_text(content, encoding="utf-8-sig")
        assert read_source(str(f)) == content

    def test_read_cp1252_fallback(self, tmp_path):
        f = tmp_path / "unit_cp1252.pas"
        content = "unit UnitCp1252; // este módulo!"
        # Write specifically as CP1252 bytes
        f.write_bytes(content.encode("cp1252"))
        # Auto-detection should recover CP1252
        res = read_source(str(f))
        assert "este módulo!" in res

    def test_read_utf16_with_bom(self, tmp_path):
        f = tmp_path / "unit_u16.pas"
        content = "unit UnitU16; // teste"
        f.write_bytes(content.encode("utf-16"))
        assert read_source(str(f)) == content

    def test_read_utf16_explicit_encoding(self, tmp_path):
        f = tmp_path / "unit_u16_nobom.pas"
        content = "unit UnitU16NoBom; // teste"
        f.write_bytes(content.encode("utf-16-le"))
        assert read_source(str(f), encoding="utf-16-le") == content


# ---------------------------------------------------------------------------
# Preprocessor tests
# ---------------------------------------------------------------------------

class TestPreprocessor:
    def test_ifdef_when_defined(self):
        src = "{$IFDEF FOO} unit Foo; {$ELSE} unit Bar; {$ENDIF}"
        tokens = tokenize(src)
        pre = preprocess_tokens(tokens, defines={"FOO"})
        types = [t.type for t in pre if t.type != TT.EOF]
        values = [t.value for t in pre if t.type != TT.EOF]
        assert "Foo" in values
        assert "Bar" not in values

    def test_ifdef_when_not_defined(self):
        src = "{$IFDEF FOO} unit Foo; {$ELSE} unit Bar; {$ENDIF}"
        tokens = tokenize(src)
        pre = preprocess_tokens(tokens, defines=set())
        values = [t.value for t in pre if t.type != TT.EOF]
        assert "Bar" in values
        assert "Foo" not in values

    def test_default_defines_win32(self):
        src = "{$IFDEF WIN32} uses Windows; {$ELSE} uses Posix; {$ENDIF}"
        tokens = tokenize(src)
        pre = preprocess_tokens(tokens)
        values = [t.value for t in pre if t.type != TT.EOF]
        assert "Windows" in values
        assert "Posix" not in values

    def test_ifndef_normal(self):
        src = "{$IFNDEF SOMETHING} type TMy = Integer; {$ENDIF}"
        tokens = tokenize(src)
        pre = preprocess_tokens(tokens, defines=set())
        values = [t.value for t in pre if t.type != TT.EOF]
        assert "TMy" in values

    def test_ifndef_build_break_skipped(self):
        # Delphi idiom: unquoted text ending with ! inside IFNDEF
        src = "{$IFNDEF CONFREVENDA} Defina a diretiva CONFREVENDA para compilar este módulo! {$ENDIF} unit Foo;"
        tokens = tokenize(src)
        # Even without CONFREVENDA defined, the build break is detected and skipped!
        pre = preprocess_tokens(tokens, defines=set())
        values = [t.value for t in pre if t.type != TT.EOF]
        assert "Defina" not in values
        assert "módulo" not in values
        assert "Foo" in values

    def test_if_defined_expression(self):
        src = "{$IF DEFINED(MY_FEATURE)} procedure DoWork; {$IFEND}"
        tokens = tokenize(src)
        pre = preprocess_tokens(tokens, defines={"MY_FEATURE"})
        values = [t.value for t in pre if t.type != TT.EOF]
        assert "DoWork" in values

        pre2 = preprocess_tokens(tokens, defines=set())
        values2 = [t.value for t in pre2 if t.type != TT.EOF]
        assert "DoWork" not in values2

    def test_define_and_undef_directives(self):
        src = """
        {$DEFINE ACTIVE}
        {$IFDEF ACTIVE}
        type TOne = Integer;
        {$ENDIF}
        {$UNDEF ACTIVE}
        {$IFDEF ACTIVE}
        type TTwo = String;
        {$ENDIF}
        """
        tokens = tokenize(src)
        pre = preprocess_tokens(tokens)
        values = [t.value for t in pre if t.type != TT.EOF]
        assert "TOne" in values
        assert "TTwo" not in values

    def test_non_conditional_directives_preserved(self):
        src = "{$R *.res} unit Foo;"
        tokens = tokenize(src)
        pre = preprocess_tokens(tokens)
        types = [t.type for t in pre if t.type != TT.EOF]
        assert TT.COMPILER_DIR in types


# ---------------------------------------------------------------------------
# Real-world DPR reproduction test (SAgrBasf / SAgrAdap)
# ---------------------------------------------------------------------------

class TestRealWorldDprBuildBreaks:
    def test_parse_cp1252_dpr_with_build_breaks(self, tmp_path):
        dpr_content = """program SAgrBasf;
                                
{$IFNDEF CONFREVENDA}
  Defina a diretiva CONFREVENDA para compilar este módulo!
{$ENDIF}

{$IFNDEF NAOUSAOPCOES}
  Defina a diretiva NAOUSAOPCOES para compilar este módulo!
{$ENDIF}

uses
  Forms,
  Controls,
  Principal in 'Principal.pas';

{$R *.res}
Var Logou  : Boolean;
begin
  Application.Initialize;
end.
"""
        f = tmp_path / "SAgrBasf.dpr"
        f.write_bytes(dpr_content.encode("cp1252"))

        ast = pda.parse_file(str(f))
        assert ast["kind"] == "Program"
        assert ast["name"] == "SAgrBasf"
        assert ast["uses"] is not None
        unit_names = [item["name"] for item in ast["uses"]["items"]]
        assert "Forms" in unit_names
        assert "Controls" in unit_names
        assert "Principal" in unit_names

    def test_dproj_defines_extracted(self, tmp_path):
        dproj_xml = """<?xml version="1.0" encoding="utf-8"?>
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <MainSource>MyApp.dpr</MainSource>
    <DCC_Define>CONFREVENDA;NAOUSAOPCOES;$(DCC_Define)</DCC_Define>
  </PropertyGroup>
</Project>"""
        f = tmp_path / "MyApp.dproj"
        f.write_text(dproj_xml, encoding="utf-8")

        ast = pda.parse_dproj(dproj_xml, str(f))
        assert "CONFREVENDA" in ast["defines"]
        assert "NAOUSAOPCOES" in ast["defines"]

    def test_cli_with_define(self, tmp_path):
        from pydelphiast.__main__ import main
        dpr_content = """program MyCli;
{$IFNDEF CUSTOM_DEF}
  BuildBreakWithoutExclamation
{$ENDIF}
uses SysUtils;
begin
end.
"""
        f = tmp_path / "MyCli.dpr"
        f.write_text(dpr_content, encoding="utf-8")
        out_json = tmp_path / "MyCli.json"

        ret = main(["-D", "CUSTOM_DEF", str(f), "-o", str(out_json)])
        assert ret == 0
        assert out_json.is_file()
