"""Tests for the TOON export (encoder, compact hierarchy, CLI)."""

from __future__ import annotations

import pytest

from pydelphiast.toon import encode_toon


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
