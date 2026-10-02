"""Tests for the TOON export (encoder, compact hierarchy, CLI)."""

from __future__ import annotations

from pathlib import Path

import pytest

import pydelphiast as pda
from pydelphiast.__main__ import main as cli_main
from pydelphiast.toon import (
    _method_row,
    _params_str,
    _type_str,
    encode_toon,
    extract_compact_hierarchy,
    to_toon,
)


# ---------------------------------------------------------------------------
# Task 1 – encoder
# ---------------------------------------------------------------------------

class TestEncodeToonPrimitives:
    @pytest.mark.parametrize("value, expected", [
        (None, "null"),
        (True, "true"),
        (False, "false"),
        (42, "42"),
        (-7, "-7"),
        (1.5, "1.5"),
        (2.0, "2"),
        (-0.0, "0"),
        (1e-7, "0.0000001"),
    ])
    def test_scalar_values(self, value, expected):
        assert encode_toon({"k": value}) == f"k: {expected}"

    @pytest.mark.parametrize("value, expected", [
        ("hello", "hello"),
        ("hello world", "hello world"),
        ("class function", "class function"),
        ("TList<T>", "TList<T>"),
        ("", '""'),
        (" a", '" a"'),
        ("a ", '"a "'),
        ("true", '"true"'),
        ("null", '"null"'),
        ("123", '"123"'),
        ("1.5", '"1.5"'),
        ("05", '"05"'),
        ("a:b", '"a:b"'),
        ("a,b", '"a,b"'),
        ("[x]", '"[x]"'),
        ("{x}", '"{x}"'),
        ("-x", '"-x"'),
        ('a"b', '"a\\"b"'),
        ("a\\b", '"a\\\\b"'),
        ("l1\nl2", '"l1\\nl2"'),
        ("t\tx", '"t\\tx"'),
    ])
    def test_string_quoting(self, value, expected):
        assert encode_toon({"k": value}) == f"k: {expected}"

    def test_key_needing_quotes(self):
        assert encode_toon({"my key": 1}) == '"my key": 1'

    def test_dotted_key_is_bare(self):
        assert encode_toon({"Font.Name": "Tahoma"}) == "Font.Name: Tahoma"

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError):
            encode_toon({"s": {1, 2}})

    def test_root_primitive(self):
        assert encode_toon("x y") == "x y"


class TestEncodeToonStructures:
    def test_flat_object(self):
        assert encode_toon({"a": 1, "b": "x"}) == "a: 1\nb: x"

    def test_nested_object(self):
        assert encode_toon({"a": {"b": 1, "c": {"d": 2}}}) == "a:\n  b: 1\n  c:\n    d: 2"

    def test_empty_object(self):
        assert encode_toon({"a": {}}) == "a:"

    def test_primitive_array(self):
        assert encode_toon({"t": ["A", "B c", 3]}) == "t[3]: A,B c,3"

    def test_empty_array(self):
        assert encode_toon({"t": []}) == "t[0]:"

    def test_tabular_array(self):
        value = {"m": [{"x": 1, "y": "a"}, {"x": 2, "y": ""}]}
        assert encode_toon(value) == 'm[2]{x,y}:\n  1,a\n  2,""'

    def test_non_uniform_objects_use_list_form(self):
        value = {"u": [{"name": "A", "t": [{"x": 1}]}, {"name": "B"}]}
        assert encode_toon(value) == (
            "u[2]:\n"
            "  - name: A\n"
            "    t[1]{x}:\n"
            "      1\n"
            "  - name: B"
        )

    def test_list_item_with_nested_object(self):
        value = {"u": [{"name": "A", "form": {"name": "F"}}, {"name": "B"}]}
        assert encode_toon(value) == (
            "u[2]:\n"
            "  - name: A\n"
            "    form:\n"
            "      name: F\n"
            "  - name: B"
        )

    def test_mixed_list(self):
        value = {"x": [1, {"a": 1}, [1, 2]]}
        assert encode_toon(value) == "x[3]:\n  - 1\n  - a: 1\n  - [2]: 1,2"

    def test_root_list(self):
        assert encode_toon([1, 2]) == "[2]: 1,2"


# ---------------------------------------------------------------------------
# Task 2 – type / parameter / method formatting
# ---------------------------------------------------------------------------

def _tref(name, *args):
    node = {"kind": "TypeRef", "name": name}
    if args:
        node["typeArgs"] = list(args)
    return node


class TestTypeStr:
    @pytest.mark.parametrize("node, expected", [
        (None, ""),
        (_tref("Integer"), "Integer"),
        (_tref("TList", {"kind": "StringType"}), "TList<string>"),
        (_tref("TDictionary", _tref("string"), _tref("TList", _tref("Integer"))),
         "TDictionary<string,TList<Integer>>"),
        ({"kind": "StringType"}, "string"),
        ({"kind": "OpenArrayType"}, "array of const"),
        ({"kind": "OpenArrayType", "elementType": _tref("Integer")}, "array of Integer"),
        ({"kind": "ArrayType", "elementType": _tref("Byte")}, "array of Byte"),
        ({"kind": "SetType", "baseType": _tref("TDir")}, "set of TDir"),
        ({"kind": "PointerType", "baseType": _tref("Integer")}, "^Integer"),
        ({"kind": "ProcType", "isFunction": True}, "function"),
        ({"kind": "ProcType", "isFunction": False}, "procedure"),
        ({"kind": "MethodReference", "procType": {"kind": "ProcType", "isFunction": False}},
         "reference to procedure"),
        ({"kind": "EnumType"}, "EnumType"),
    ])
    def test_type_str(self, node, expected):
        assert _type_str(node) == expected


class TestParamsAndMethodRow:
    def test_params_from_real_method(self):
        ast = pda.parse_source(
            "unit U; interface type T = class "
            "procedure P(const A, B: string; var C: Integer; out D; "
            "const V: array of const; X: array of Integer); end; "
            "implementation end.",
            "U.pas",
        )
        m = ast["interface"]["declarations"][0]["items"][0]["typeDefinition"]["members"][0]
        assert _params_str(m["params"]) == (
            "const A,B:string; var C:Integer; out D; "
            "const V:array of const; X:array of Integer"
        )

    def test_params_open_array_param_node(self):
        params = [{"kind": "OpenArrayParam", "modifier": "const", "elementType": None}]
        assert _params_str(params) == "const array of const"

    def test_params_empty(self):
        assert _params_str(None) == ""
        assert _params_str([]) == ""

    def test_method_row_function(self):
        m = {"kind": "MethodDecl", "methodKind": "function", "name": "Get",
             "returnType": _tref("Integer"), "visibility": "protected",
             "isClassMember": False}
        assert _method_row(m) == {"vis": "protected", "kind": "function", "name": "Get",
                                  "params": "", "returns": "Integer"}

    def test_method_row_class_member_and_default_visibility(self):
        m = {"kind": "MethodDecl", "methodKind": "function", "name": "Make",
             "returnType": _tref("TFoo"), "isClassMember": True}
        assert _method_row(m) == {"vis": "public", "kind": "class function",
                                  "name": "Make", "params": "", "returns": "TFoo"}


# ---------------------------------------------------------------------------
# Task 3 – unit / form extraction
# ---------------------------------------------------------------------------

UNIT_SRC = """unit UDemo;
interface
type
  IFoo = interface
    ['{00000000-0000-0000-0000-000000000000}']
    function Get: Integer;
  end;
  TRec = record
    X: Integer;
    procedure Clear;
  end;
  TFwd = class;
  TFoo = class(TForm, IFoo)
  private
    FX: Integer;
    procedure DoIt(const A, B: string; var C: Integer);
  protected
    function Get: Integer; virtual;
  public
    constructor Create(AOwner: TComponent); override;
    class function Make: TFoo;
    property X: Integer read FX;
  end;
  THelp = class helper for TObject
    procedure Hi;
  end;
  TPack = packed record
    A: Byte;
  end;
  TCount = Integer;
procedure Free(P: Pointer);
implementation
type
  TImpl = class
    procedure Z;
  end;
procedure Free(P: Pointer); begin end;
end.
"""

EXPECTED_UNIT_TYPES = [
    {"name": "IFoo", "kind": "interface",
     "methods": [{"vis": "public", "kind": "function", "name": "Get",
                  "params": "", "returns": "Integer"}]},
    {"name": "TRec", "kind": "record",
     "methods": [{"vis": "public", "kind": "procedure", "name": "Clear",
                  "params": "", "returns": ""}]},
    {"name": "TFoo", "kind": "class", "ancestors": ["TForm", "IFoo"],
     "methods": [
         {"vis": "private", "kind": "procedure", "name": "DoIt",
          "params": "const A,B:string; var C:Integer", "returns": ""},
         {"vis": "protected", "kind": "function", "name": "Get",
          "params": "", "returns": "Integer"},
         {"vis": "public", "kind": "constructor", "name": "Create",
          "params": "AOwner:TComponent", "returns": ""},
         {"vis": "public", "kind": "class function", "name": "Make",
          "params": "", "returns": "TFoo"},
     ]},
    {"name": "THelp", "kind": "class helper", "for": "TObject",
     "methods": [{"vis": "published", "kind": "procedure", "name": "Hi",
                  "params": "", "returns": ""}]},
    {"name": "TPack", "kind": "record"},
    {"name": "TImpl", "kind": "class",
     "methods": [{"vis": "published", "kind": "procedure", "name": "Z",
                  "params": "", "returns": ""}]},
]


class TestExtractUnit:
    def test_unit_types_from_full_ast(self, tmp_path):
        ast = pda.parse_source(UNIT_SRC, "UDemo.pas")
        out = extract_compact_hierarchy(ast, base_dir=str(tmp_path))
        assert out["base"] == str(tmp_path).replace("\\", "/")
        assert out["unit"]["name"] == "UDemo"
        assert "path" not in out["unit"]  # parse_source does not stamp filename
        assert out["unit"]["types"] == EXPECTED_UNIT_TYPES

    def test_slim_and_full_ast_give_same_result(self, tmp_path):
        ast = pda.parse_source(UNIT_SRC, "UDemo.pas")
        full = extract_compact_hierarchy(ast, base_dir=str(tmp_path))
        slim = extract_compact_hierarchy(pda.slim_ast(ast), base_dir=str(tmp_path))
        assert full == slim

    def test_unit_file_with_companion_form(self, tmp_path):
        (tmp_path / "UMain.pas").write_text(
            "unit UMain;\ninterface\ntype\n  TMainForm = class(TForm)\n"
            "    procedure FormCreate(Sender: TObject);\n  end;\n"
            "implementation\nprocedure TMainForm.FormCreate(Sender: TObject); begin end;\nend.\n",
            encoding="utf-8",
        )
        (tmp_path / "UMain.dfm").write_text(
            "object MainForm: TMainForm\n  Left = 0\nend\n", encoding="utf-8"
        )
        out = extract_compact_hierarchy(pda.parse_file(str(tmp_path / "UMain.pas")))
        assert out["base"] == str(tmp_path).replace("\\", "/")
        assert out["unit"] == {
            "name": "UMain",
            "path": "UMain.pas",
            "form": {"name": "MainForm", "class": "TMainForm", "path": "UMain.dfm"},
            "types": [{
                "name": "TMainForm", "kind": "class", "ancestors": ["TForm"],
                "methods": [{"vis": "published", "kind": "procedure", "name": "FormCreate",
                             "params": "Sender:TObject", "returns": ""}],
            }],
        }

    def test_form_path_falls_back_to_unit_path(self, tmp_path):
        unit = {"kind": "Unit", "name": "U", "filename": str(tmp_path / "U.pas"),
                "form": {"kind": "DfmObject", "name": "F", "className": "TF"}}
        out = extract_compact_hierarchy(unit)
        assert out["unit"]["form"] == {"name": "F", "class": "TF", "path": "U.dfm"}

    def test_dfm_root(self, tmp_path):
        dfm = tmp_path / "F.dfm"
        dfm.write_text("object F: TF\nend\n", encoding="utf-8")
        out = extract_compact_hierarchy(pda.parse_file(str(dfm)))
        assert out["form"] == {"name": "F", "class": "TF", "path": "F.dfm"}

    def test_parse_error_root(self, tmp_path):
        node = {"kind": "ParseError", "filename": str(tmp_path / "X.pas"), "message": "boom"}
        out = extract_compact_hierarchy(node)
        assert out["error"] == {"path": "X.pas", "message": "boom"}

    def test_parse_file_stamps_form_filename(self, tmp_path):
        (tmp_path / "U.pas").write_text("unit U; interface implementation end.",
                                        encoding="utf-8")
        (tmp_path / "U.dfm").write_text("object F: TF\nend\n", encoding="utf-8")
        ast = pda.parse_file(str(tmp_path / "U.pas"))
        assert ast["form"]["filename"] == str((tmp_path / "U.dfm").resolve())


# ---------------------------------------------------------------------------
# Task 4 – project / group extraction
# ---------------------------------------------------------------------------

_NS = "http://schemas.microsoft.com/developer/msbuild/2003"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _dproj(main_source: str) -> str:
    return (
        f'<Project xmlns="{_NS}">\n'
        "  <PropertyGroup>\n"
        f"    <MainSource>{main_source}</MainSource>\n"
        "    <Config Condition=\"'$(Config)'==''\">Debug</Config>\n"
        "    <Platform Condition=\"'$(Platform)'==''\">Win32</Platform>\n"
        "  </PropertyGroup>\n"
        "</Project>\n"
    )


@pytest.fixture()
def group_dir(tmp_path: Path) -> Path:
    """Build: Group.groupproj -> App/App.dproj, Tool/Tool.dproj, Gone/Gone.dproj (missing)."""
    _write(tmp_path / "Group.groupproj",
           f'<Project xmlns="{_NS}">\n  <ItemGroup>\n'
           '    <Projects Include="App\\App.dproj"/>\n'
           '    <Projects Include="Tool\\Tool.dproj"/>\n'
           '    <Projects Include="Gone\\Gone.dproj"/>\n'
           "  </ItemGroup>\n</Project>\n")
    _write(tmp_path / "App" / "App.dproj", _dproj("App.dpr"))
    _write(tmp_path / "App" / "App.dpr",
           "program App;\nuses\n  UMain in 'UMain.pas',\n"
           "  UShared in '../Shared/UShared.pas';\nbegin\nend.\n")
    _write(tmp_path / "App" / "UMain.pas",
           "unit UMain;\ninterface\ntype\n  TMainForm = class(TForm)\n"
           "  public\n    function Ok(const S: string): Boolean;\n  end;\n"
           "implementation\nfunction TMainForm.Ok(const S: string): Boolean; begin end;\nend.\n")
    _write(tmp_path / "App" / "UMain.dfm", "object MainForm: TMainForm\nend\n")
    _write(tmp_path / "Shared" / "UShared.pas",
           "unit UShared;\ninterface\nimplementation\nend.\n")
    _write(tmp_path / "Tool" / "Tool.dproj", _dproj("Tool.dpr"))
    _write(tmp_path / "Tool" / "Tool.dpr",
           "program Tool;\nuses\n  UShared in '../Shared/UShared.pas';\nbegin\nend.\n")
    return tmp_path


EXPECTED_GROUP = {
    "name": "Group",
    "path": "Group.groupproj",
    "projects": [
        {
            "name": "App",
            "path": "App/App.dproj",
            "source": "App/App.dpr",
            "platform": "Win32",
            "config": "Debug",
            "units": [
                {
                    "name": "UMain",
                    "path": "App/UMain.pas",
                    "form": {"name": "MainForm", "class": "TMainForm",
                             "path": "App/UMain.dfm"},
                    "types": [{
                        "name": "TMainForm", "kind": "class", "ancestors": ["TForm"],
                        "methods": [{"vis": "public", "kind": "function", "name": "Ok",
                                     "params": "const S:string", "returns": "Boolean"}],
                    }],
                },
                {"name": "UShared", "path": "Shared/UShared.pas"},
            ],
        },
        {
            "name": "Tool",
            "path": "Tool/Tool.dproj",
            "source": "Tool/Tool.dpr",
            "platform": "Win32",
            "config": "Debug",
            "units": [{"name": "UShared", "path": "Shared/UShared.pas", "ref": True}],
        },
        {"name": "Gone", "path": "Gone/Gone.dproj", "missing": True},
    ],
}


class TestExtractProject:
    def test_dpr_root_has_filename(self, group_dir):
        ast = pda.parse_project(str(group_dir / "App" / "App.dpr"))
        assert ast["filename"] == str(group_dir / "App" / "App.dpr")

    def test_group_hierarchy(self, group_dir):
        ast = pda.parse_project(str(group_dir / "Group.groupproj"))
        out = extract_compact_hierarchy(ast)
        assert out["base"] == str(group_dir).replace("\\", "/")
        assert out["group"] == EXPECTED_GROUP

    def test_group_hierarchy_from_slim_ast(self, group_dir):
        ast = pda.parse_project(str(group_dir / "Group.groupproj"))
        assert extract_compact_hierarchy(pda.slim_ast(ast))["group"] == EXPECTED_GROUP

    def test_dpr_root(self, group_dir):
        ast = pda.parse_project(str(group_dir / "Tool" / "Tool.dpr"))
        out = extract_compact_hierarchy(ast)
        assert out["base"] == str(group_dir / "Tool").replace("\\", "/")
        assert out["project"] == {
            "name": "Tool",
            "path": "Tool.dpr",
            "units": [{"name": "UShared", "path": "../Shared/UShared.pas"}],
        }

    def test_dproj_root(self, group_dir):
        ast = pda.parse_project(str(group_dir / "App" / "App.dproj"))
        out = extract_compact_hierarchy(ast)
        assert out["project"]["path"] == "App.dproj"
        assert out["project"]["source"] == "App.dpr"
        assert [u["name"] for u in out["project"]["units"]] == ["UMain", "UShared"]

    def test_list_input_groups_by_kind(self, group_dir):
        asts = [
            pda.parse_file(str(group_dir / "App" / "UMain.pas")),
            pda.parse_file(str(group_dir / "Shared" / "UShared.pas")),
        ]
        out = extract_compact_hierarchy(asts)
        assert out["base"] == str(group_dir).replace("\\", "/")
        assert [u["path"] for u in out["units"]] == ["App/UMain.pas", "Shared/UShared.pas"]
        assert set(out) == {"base", "units"}


# ---------------------------------------------------------------------------
# Task 5 – to_toon end to end + public API
# ---------------------------------------------------------------------------

class TestToToon:
    def test_public_api_exports(self):
        assert pda.to_toon is to_toon
        assert pda.extract_compact_hierarchy is extract_compact_hierarchy
        assert pda.encode_toon is encode_toon
        for name in ("to_toon", "extract_compact_hierarchy", "encode_toon"):
            assert name in pda.__all__

    def test_group_toon_text(self, group_dir):
        ast = pda.parse_project(str(group_dir / "Group.groupproj"))
        base = str(group_dir).replace("\\", "/")
        assert pda.to_toon(ast) == (
            f'base: "{base}"\n'
            "group:\n"
            "  name: Group\n"
            "  path: Group.groupproj\n"
            "  projects[3]:\n"
            "    - name: App\n"
            "      path: App/App.dproj\n"
            "      source: App/App.dpr\n"
            "      platform: Win32\n"
            "      config: Debug\n"
            "      units[2]:\n"
            "        - name: UMain\n"
            "          path: App/UMain.pas\n"
            "          form:\n"
            "            name: MainForm\n"
            "            class: TMainForm\n"
            "            path: App/UMain.dfm\n"
            "          types[1]:\n"
            "            - name: TMainForm\n"
            "              kind: class\n"
            "              ancestors[1]: TForm\n"
            "              methods[1]{vis,kind,name,params,returns}:\n"
            '                public,function,Ok,"const S:string",Boolean\n'
            "        - name: UShared\n"
            "          path: Shared/UShared.pas\n"
            "    - name: Tool\n"
            "      path: Tool/Tool.dproj\n"
            "      source: Tool/Tool.dpr\n"
            "      platform: Win32\n"
            "      config: Debug\n"
            "      units[1]{name,path,ref}:\n"
            "        UShared,Shared/UShared.pas,true\n"
            "    - name: Gone\n"
            "      path: Gone/Gone.dproj\n"
            "      missing: true"
        )

    def test_toon_is_smaller_than_json(self, group_dir):
        ast = pda.parse_project(str(group_dir / "Group.groupproj"))
        assert len(pda.to_toon(ast)) * 5 < len(pda.to_json(ast))


# ---------------------------------------------------------------------------
# Task 6 – CLI
# ---------------------------------------------------------------------------

class TestCliToon:
    def test_toon_flag_writes_toon_next_to_input(self, group_dir):
        root = group_dir / "Group.groupproj"
        assert cli_main([str(root), "--toon"]) == 0
        out = group_dir / "Group.toon"
        assert out.is_file()
        ast = pda.parse_project(str(root))
        assert out.read_text(encoding="utf-8") == pda.to_toon(ast)
        assert not (group_dir / "Group.json").exists()

    def test_toon_flag_respects_output(self, group_dir, tmp_path):
        target = tmp_path / "custom.toon"
        assert cli_main([str(group_dir / "App" / "UMain.pas"), "--toon",
                         "-o", str(target)]) == 0
        assert target.read_text(encoding="utf-8").startswith("base: ")

    def test_without_toon_still_writes_json(self, group_dir):
        assert cli_main([str(group_dir / "App" / "UMain.pas")]) == 0
        assert (group_dir / "App" / "UMain.json").is_file()
        assert not (group_dir / "App" / "UMain.toon").exists()
