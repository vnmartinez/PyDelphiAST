"""Recursive-descent parser for Delphi 10 .pas and .dpr/.dpl source files.

Handles the full Delphi 10 (Seattle) grammar including:
  - Units, programs, libraries, packages
  - Interface / implementation sections
  - Type declarations: classes, records, interfaces, dispinterfaces,
    object types, enums, subranges, sets, arrays, pointers, procedure types
  - Generic types: TFoo<T, U>
  - Class helpers, record helpers
  - Const / var / threadvar / label / resourcestring sections
  - Procedure / function / constructor / destructor / operator declarations
  - Anonymous methods and method references
  - Full statement parsing: begin/end, if, case, for, while, repeat,
    try/except/finally, with, raise, goto, asm blocks
  - Expression parsing with correct Delphi operator precedence
  - Compiler directives preserved in the AST
  - Error recovery: on parse error the offending token is skipped and an
    "error" node is inserted so the rest of the file is still parsed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..errors import ParseError
from ..lexer import Token, tokenize
from ..tokens import (
    CALLING_CONVENTIONS,
    DIRECTIVE_TYPES,
    ROUTINE_DIRECTIVES,
    VISIBILITY_TYPES,
    TT,
)
from .base import BaseParser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: Token types that may appear as the first token of a statement
_STMT_STARTERS = {
    TT.BEGIN, TT.IF, TT.CASE, TT.FOR, TT.WHILE, TT.REPEAT,
    TT.TRY, TT.WITH, TT.RAISE, TT.GOTO, TT.ASM, TT.INHERITED,
    TT.IDENT,
    TT.SEMI,   # empty statement
} | DIRECTIVE_TYPES

#: Declaration section starters inside a class/record body
_CLASS_SECTION_STARTERS = {
    TT.TYPE, TT.CONST, TT.VAR, TT.CLASS,
    TT.PROCEDURE, TT.FUNCTION, TT.CONSTRUCTOR, TT.DESTRUCTOR,
    TT.PROPERTY,
} | VISIBILITY_TYPES | {TT.D_STRICT}

#: What can follow a uses list item
_AFTER_USES_ITEM = {TT.COMMA, TT.SEMI}

#: Calling convention tokens in a calling-convention position
_CC = CALLING_CONVENTIONS


# ---------------------------------------------------------------------------
# Main parser class
# ---------------------------------------------------------------------------

class PasParser(BaseParser):
    """Parse a single Delphi .pas, .dpr, .dpl, or .dpk source file."""

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def parse(self) -> dict:
        self.skip_compiler_dirs()
        tok = self.current
        if tok.type == TT.UNIT:
            return self._parse_unit()
        if tok.type == TT.PROGRAM:
            return self._parse_program()
        if tok.type == TT.LIBRARY:
            return self._parse_library()
        if tok.type == TT.D_PACKAGE:
            return self._parse_package()
        # Fallback: try as unit
        return self._parse_unit()

    # ==================================================================
    # File-level nodes
    # ==================================================================

    def _parse_unit(self) -> dict:
        start = self.current
        self.expect(TT.UNIT)
        name = self.parse_qualified_name()
        dirs = self._opt_deprecated_hint()
        self.expect(TT.SEMI)

        iface = self._parse_interface_section()
        impl = self._parse_implementation_section()
        init = self._parse_init_section()
        self.match(TT.DOT)

        return self._node("Unit", start,
                          name=name,
                          directives=dirs,
                          interface=iface,
                          implementation=impl,
                          initialization=init)

    def _parse_program(self) -> dict:
        start = self.current
        self.expect(TT.PROGRAM)
        name = self.parse_qualified_name()
        self.expect(TT.SEMI)
        self.skip_compiler_dirs()
        uses = self._parse_uses_clause() if self.check(TT.USES) else None
        # Programs may have top-level var/const/type/label sections before begin
        decls = self._parse_decl_list(allow_impl=True)
        block = self._parse_block()
        self.match(TT.DOT)
        return self._node("Program", start, name=name, uses=uses,
                          declarations=decls, block=block)

    def _parse_library(self) -> dict:
        start = self.current
        self.expect(TT.LIBRARY)
        name = self.parse_qualified_name()
        self.expect(TT.SEMI)
        self.skip_compiler_dirs()
        uses = self._parse_uses_clause() if self.check(TT.USES) else None
        decls = self._parse_decl_list(allow_impl=True)
        block = self._parse_block()
        self.match(TT.DOT)
        return self._node("Library", start, name=name, uses=uses,
                          declarations=decls, block=block)

    def _parse_package(self) -> dict:
        start = self.current
        self.expect(TT.D_PACKAGE)
        name = self.parse_qualified_name()
        self.expect(TT.SEMI)
        requires = self._parse_requires_clause() if self.check_value("requires") else None
        contains = self._parse_contains_clause() if self.check_value("contains") else None
        self.expect(TT.END)
        self.match(TT.DOT)
        return self._node("Package", start, name=name,
                          requires=requires, contains=contains)

    # ==================================================================
    # Sections
    # ==================================================================

    def _parse_interface_section(self) -> dict:
        self.skip_compiler_dirs()
        start = self.current
        self.expect(TT.INTERFACE)
        self.skip_compiler_dirs()
        uses = self._parse_uses_clause() if self.check(TT.USES) else None
        decls = self._parse_decl_list(allow_impl=False)
        return self._node("InterfaceSection", start, uses=uses, declarations=decls)

    def _parse_implementation_section(self) -> dict:
        self.skip_compiler_dirs()
        start = self.current
        self.expect(TT.IMPLEMENTATION)
        self.skip_compiler_dirs()
        uses = self._parse_uses_clause() if self.check(TT.USES) else None
        decls = self._parse_decl_list(allow_impl=True)
        return self._node("ImplementationSection", start, uses=uses, declarations=decls)

    def _parse_init_section(self) -> Optional[dict]:
        if self.check(TT.END):
            self.advance()
            return None
        if self.check(TT.INITIALIZATION):
            start = self.current
            self.advance()
            stmts = self._parse_stmt_list()
            fin_stmts = None
            if self.check(TT.FINALIZATION):
                self.advance()
                fin_stmts = self._parse_stmt_list()
            self.expect(TT.END)
            return self._node("InitSection", start,
                              statements=stmts, finalization=fin_stmts)
        if self.check(TT.BEGIN):
            start = self.current
            block = self._parse_block()
            self.expect(TT.END)
            return self._node("InitSection", start, block=block)
        return None

    def _parse_requires_clause(self) -> dict:
        start = self.current
        self.expect_ident()  # requires
        items: List[str] = []
        items.append(self.parse_qualified_name())
        while self.match(TT.COMMA):
            items.append(self.parse_qualified_name())
        self.expect(TT.SEMI)
        return self._node("RequiresClause", start, items=items)

    def _parse_contains_clause(self) -> dict:
        start = self.current
        self.expect_ident()  # contains
        items: List[str] = []
        items.append(self.parse_qualified_name())
        while self.match(TT.COMMA):
            items.append(self.parse_qualified_name())
        self.expect(TT.SEMI)
        return self._node("ContainsClause", start, items=items)

    # ==================================================================
    # Uses clause
    # ==================================================================

    def _parse_uses_clause(self) -> dict:
        start = self.current
        self.expect(TT.USES)
        items: List[dict] = []
        self.skip_compiler_dirs()
        items.append(self._parse_uses_item())
        while self.match(TT.COMMA):
            self.skip_compiler_dirs()
            if self.check(TT.SEMI):  # trailing comma before semicolon
                break
            items.append(self._parse_uses_item())
        self.expect(TT.SEMI)
        return self._node("UsesClause", start, items=items)

    def _parse_uses_item(self) -> dict:
        start = self.current
        name = self.parse_qualified_name()
        path = None
        if self.check(TT.IN):
            self.advance()
            path = self.expect(TT.STRING).value
        return self._node("UsesItem", start, name=name, path=path)

    # ==================================================================
    # Declaration lists
    # ==================================================================

    def _parse_decl_list(self, allow_impl: bool = True) -> List[dict]:
        """Parse zero or more declaration sections until a section-ending token."""
        decls: List[dict] = []
        while True:
            self.skip_compiler_dirs()
            self.skip_attributes()
            t = self.current.type

            if t == TT.TYPE:
                decls.append(self._parse_type_section())
            elif t == TT.CONST:
                decls.append(self._parse_const_section())
            elif t in (TT.VAR, TT.THREADVAR):
                decls.append(self._parse_var_section())
            elif t == TT.LABEL:
                decls.append(self._parse_label_section())
            elif t == TT.RESOURCESTRING:
                decls.append(self._parse_resourcestring_section())
            elif t == TT.EXPORTS:
                decls.append(self._parse_exports_clause())
            elif t in (TT.PROCEDURE, TT.FUNCTION, TT.CONSTRUCTOR,
                       TT.DESTRUCTOR, TT.OPERATOR, TT.CLASS):
                decls.append(self._parse_routine_decl(allow_impl=allow_impl))
            else:
                break
        return decls

    # ==================================================================
    # Type section
    # ==================================================================

    def _parse_type_section(self) -> dict:
        start = self.current
        self.expect(TT.TYPE)
        items: List[dict] = []
        self.skip_compiler_dirs()
        self.skip_attributes()
        while self.is_ident() or self.check(TT.IDENT):
            try:
                items.append(self._parse_type_decl())
            except ParseError as exc:
                items.append(self._error_node(exc))
                self._recover_to(TT.SEMI, TT.END)
            self.skip_compiler_dirs()
            self.skip_attributes()
        return self._node("TypeSection", start, items=items)

    def _parse_type_decl(self) -> dict:
        start = self.current
        name = self.expect_ident().value
        # Generic params: TFoo<T, U> = ...
        generic_params = self._parse_generic_formal_params()
        self.expect(TT.EQ)
        # Optional 'type' keyword (for type aliases)
        is_new_type = bool(self.match(TT.TYPE))
        typedef = self._parse_type_def()
        self.expect(TT.SEMI)
        return self._node("TypeDecl", start,
                          name=name,
                          genericParams=generic_params,
                          isNewType=is_new_type,
                          typeDefinition=typedef)

    # ==================================================================
    # Type definitions
    # ==================================================================

    def _parse_type_def(self) -> dict:  # noqa: C901
        self.skip_compiler_dirs()
        t = self.current.type

        if t == TT.CLASS:
            return self._parse_class_type()
        if t == TT.RECORD:
            return self._parse_record_type()
        if t == TT.OBJECT:
            return self._parse_object_type()
        if t == TT.INTERFACE:
            return self._parse_interface_type()
        if t == TT.DISPINTERFACE:
            return self._parse_dispinterface_type()
        if t == TT.ARRAY:
            return self._parse_array_type()
        if t == TT.SET:
            return self._parse_set_type()
        if t == TT.FILE:
            return self._parse_file_type()
        if t == TT.CARET:
            return self._parse_pointer_type()
        if t == TT.PROCEDURE:
            return self._parse_proc_type(is_function=False)
        if t == TT.FUNCTION:
            return self._parse_proc_type(is_function=True)
        if t == TT.PACKED:
            return self._parse_packed_type()
        if t == TT.LPAREN:
            return self._parse_enum_type()
        if t == TT.D_REFERENCE:
            return self._parse_method_reference()

        # Could be: subrange literal, identifier alias, or string type
        return self._parse_simple_type()

    def _parse_class_type(self) -> dict:
        start = self.current
        self.expect(TT.CLASS)

        # class of TType (metaclass)
        if self.check(TT.OF):
            self.advance()
            base_type = self._parse_type_ref()
            return self._node("MetaclassType", start, baseType=base_type)

        # Modifiers: abstract, sealed
        modifiers: List[str] = []
        while self.check(TT.D_ABSTRACT, TT.D_SEALED):
            modifiers.append(self.advance().value.lower())

        # Helper: class helper for X
        is_helper = False
        helper_for = None
        if self.check(TT.D_HELPER):
            is_helper = True
            self.advance()
            if self.check(TT.FOR):
                self.advance()
                helper_for = self._parse_type_ref()

        # Ancestors: (TBase, IFace1, IFace2)
        ancestors: List[dict] = []
        if self.check(TT.LPAREN):
            self.advance()
            ancestors.append(self._parse_type_ref())
            while self.match(TT.COMMA):
                ancestors.append(self._parse_type_ref())
            self.expect(TT.RPAREN)

        # Forward declaration: only when no ancestors were specified and the
        # very next token is ';'  (e.g.  TFoo = class;)
        if not ancestors and not is_helper and self.check(TT.SEMI):
            return self._node("ClassType", start,
                              modifiers=modifiers, ancestors=ancestors,
                              isForward=True, isHelper=is_helper,
                              helperFor=helper_for, members=[])

        members = self._parse_class_body()
        self.expect(TT.END)
        return self._node("ClassType", start,
                          modifiers=modifiers, ancestors=ancestors,
                          isForward=False, isHelper=is_helper,
                          helperFor=helper_for, members=members)

    def _parse_class_body(self) -> List[dict]:  # noqa: C901
        members: List[dict] = []
        visibility = "published"  # default for classes

        while not self.check(TT.END, TT.EOF):
            self.skip_compiler_dirs()
            self.skip_attributes()
            if self.check(TT.END, TT.EOF):
                break

            t = self.current.type

            # Visibility section
            if t in VISIBILITY_TYPES or (t == TT.D_STRICT and
                    self.peek().type in VISIBILITY_TYPES):
                strict = bool(self.match(TT.D_STRICT))
                vis_tok = self.advance()
                visibility = ("strict " if strict else "") + vis_tok.value.lower()
                continue

            # Nested type / const / var
            if t == TT.TYPE:
                members.append(self._parse_type_section())
                continue
            if t == TT.CONST:
                members.append(self._parse_const_section())
                continue
            if t == TT.VAR:
                members.append(self._parse_var_section())
                continue

            # Class keyword prefix
            is_class_member = False
            if t == TT.CLASS:
                nxt = self.peek().type
                if nxt in (TT.PROCEDURE, TT.FUNCTION, TT.CONSTRUCTOR,
                            TT.DESTRUCTOR, TT.PROPERTY, TT.OPERATOR, TT.VAR,
                            TT.D_ABSTRACT, TT.IDENT):
                    is_class_member = True
                    self.advance()
                    t = self.current.type
                else:
                    # anonymous nested class? – unlikely; try field
                    pass

            if t in (TT.PROCEDURE, TT.FUNCTION, TT.CONSTRUCTOR, TT.DESTRUCTOR,
                     TT.OPERATOR):
                m = self._parse_method_decl(visibility, is_class_member)
                members.append(m)
            elif t == TT.PROPERTY:
                m = self._parse_property_decl(visibility, is_class_member)
                members.append(m)
            elif t == TT.VAR:
                # 'class var' section inside a class body
                members.append(self._parse_var_section())
            elif self.is_ident() or t == TT.STRING_KW:
                # Could be a field or a method
                m = self._parse_field_or_method(visibility, is_class_member)
                members.append(m)
            else:
                # Unknown token in class body – skip
                members.append(self._node("Unknown", self.current,
                                          value=self.advance().value))

        return members

    def _parse_field_or_method(self, visibility: str, is_class_member: bool) -> dict:
        """Disambiguate field declaration from method declaration."""
        # Look-ahead: if we see identList ':' it's a field; if '(' it might be method
        start = self.current
        names = [self.expect_ident().value]
        while self.match(TT.COMMA):
            names.append(self.expect_ident().value)

        if self.check(TT.COLON):
            # Field
            self.advance()
            type_ref = self._parse_type_ref()
            # Variant absolute / value
            modifiers: dict = {}
            if self.check(TT.D_ABSOLUTE):
                self.advance()
                modifiers["absolute"] = self.parse_qualified_name()
            elif self.check(TT.EQ):
                self.advance()
                modifiers["defaultValue"] = self._parse_expr()
            self._consume_field_directives(modifiers)
            self.expect(TT.SEMI)
            return self._node("FieldDecl", start,
                              names=names, typeRef=type_ref,
                              visibility=visibility,
                              isClassMember=is_class_member,
                              **modifiers)

        # Otherwise treat single name as method name (unusual without type prefix)
        # Emit best-effort error node
        return self._node("UnknownMember", start, names=names, visibility=visibility)

    def _consume_field_directives(self, modifiers: dict) -> None:
        while self.check(TT.D_DEPRECATED, TT.D_EXPERIMENTAL, TT.D_PLATFORM,
                         TT.D_UNSAFE, TT.COMPILER_DIR):
            tok = self.advance()
            modifiers.setdefault("hints", []).append(tok.value)

    def _parse_method_decl(self, visibility: str, is_class_member: bool) -> dict:
        start = self.current
        kind = self.advance().type  # PROCEDURE, FUNCTION, CONSTRUCTOR, DESTRUCTOR, OPERATOR
        kind_name = kind.name.lower()

        name = self.expect_ident().value
        # Generic method params
        generic_params = self._parse_generic_formal_params()

        params = self._parse_param_list() if self.check(TT.LPAREN) else []
        ret_type = None
        if kind == TT.FUNCTION and self.check(TT.COLON):
            self.advance()
            ret_type = self._parse_type_ref()

        self.expect(TT.SEMI)
        directives = self._parse_routine_directives()

        return self._node("MethodDecl", start,
                          methodKind=kind_name,
                          name=name,
                          genericParams=generic_params,
                          params=params,
                          returnType=ret_type,
                          directives=directives,
                          visibility=visibility,
                          isClassMember=is_class_member)

    def _parse_property_decl(self, visibility: str, is_class_member: bool) -> dict:
        start = self.current
        self.expect(TT.PROPERTY)
        name = self.expect_ident().value

        # Array property index params
        index_params: List[dict] = []
        if self.check(TT.LBRACKET):
            self.advance()
            while not self.check(TT.RBRACKET, TT.EOF):
                index_params.append(self._parse_param_group())
                self.match(TT.SEMI)
            self.expect(TT.RBRACKET)

        type_ref = None
        if self.check(TT.COLON):
            self.advance()
            type_ref = self._parse_type_ref()

        # Accessors and specifiers
        prop: dict = {}
        while True:
            t = self.current.type
            if t == TT.D_READ:
                self.advance()
                prop["read"] = self._parse_accessor()
            elif t == TT.D_WRITE:
                self.advance()
                prop["write"] = self._parse_accessor()
            elif t == TT.D_INDEX:
                self.advance()
                prop["index"] = self._parse_expr()
            elif t == TT.D_DEFAULT:
                self.advance()
                if self.check(TT.SEMI):
                    prop["isDefault"] = True  # default array property
                else:
                    prop["default"] = self._parse_expr()
            elif t == TT.D_NODEFAULT:
                self.advance()
                prop["noDefault"] = True
            elif t == TT.D_STORED:
                self.advance()
                prop["stored"] = self._parse_expr()
            elif t == TT.D_IMPLEMENTS:
                self.advance()
                prop["implements"] = self._parse_type_ref()
            elif t == TT.D_READONLY:
                self.advance()
                prop["readonly"] = True
            elif t == TT.D_WRITEONLY:
                self.advance()
                prop["writeonly"] = True
            elif t == TT.D_DISPID:
                self.advance()
                prop["dispid"] = self._parse_expr()
            else:
                break

        self.expect(TT.SEMI)
        # Default property marker
        is_default_prop = False
        if self.check(TT.D_DEFAULT) and self.peek().type == TT.SEMI:
            self.advance(); self.advance()
            is_default_prop = True

        return self._node("PropertyDecl", start,
                          name=name,
                          indexParams=index_params,
                          typeRef=type_ref,
                          visibility=visibility,
                          isClassMember=is_class_member,
                          isDefault=is_default_prop,
                          **prop)

    def _parse_accessor(self) -> dict:
        start = self.current
        name = self.parse_qualified_name()
        return self._node("Accessor", start, name=name)

    # ------------------------------------------------------------------
    # Record type
    # ------------------------------------------------------------------

    def _parse_record_type(self, packed: bool = False) -> dict:
        start = self.current
        self.expect(TT.RECORD)

        # Record helper
        is_helper = False
        helper_for = None
        if self.check(TT.D_HELPER):
            is_helper = True
            self.advance()
            if self.check(TT.FOR):
                self.advance()
                helper_for = self._parse_type_ref()

        fields: List[dict] = []
        variant: Optional[dict] = None
        visibility = "public"

        while not self.check(TT.END, TT.EOF):
            self.skip_compiler_dirs()
            if self.check(TT.END, TT.EOF):
                break
            t = self.current.type

            # Visibility sections (Delphi 2006+)
            if t in VISIBILITY_TYPES or (t == TT.D_STRICT and
                    self.peek().type in VISIBILITY_TYPES):
                strict = bool(self.match(TT.D_STRICT))
                vis_tok = self.advance()
                visibility = ("strict " if strict else "") + vis_tok.value.lower()
                continue

            if t == TT.TYPE:
                fields.append(self._parse_type_section()); continue
            if t == TT.CONST:
                fields.append(self._parse_const_section()); continue
            if t in (TT.PROCEDURE, TT.FUNCTION, TT.CONSTRUCTOR, TT.DESTRUCTOR):
                fields.append(self._parse_method_decl(visibility, False)); continue
            if t == TT.CLASS:
                nxt = self.peek().type
                if nxt in (TT.PROCEDURE, TT.FUNCTION, TT.CONSTRUCTOR,
                            TT.DESTRUCTOR, TT.VAR, TT.OPERATOR):
                    self.advance()
                    fields.append(self._parse_method_decl(visibility, True))
                    continue
            if t == TT.PROPERTY:
                fields.append(self._parse_property_decl(visibility, False)); continue
            if t == TT.CASE:
                variant = self._parse_variant_part(); break

            # Field
            try:
                fields.append(self._parse_record_field(visibility))
            except ParseError:
                self._recover_to(TT.SEMI, TT.END)

        self.expect(TT.END)
        return self._node("RecordType", start,
                          packed=packed,
                          isHelper=is_helper,
                          helperFor=helper_for,
                          fields=fields,
                          variant=variant)

    def _parse_record_field(self, visibility: str) -> dict:
        start = self.current
        names = [self.expect_ident().value]
        while self.match(TT.COMMA):
            names.append(self.expect_ident().value)
        self.expect(TT.COLON)
        type_ref = self._parse_type_ref()
        self.expect(TT.SEMI)
        return self._node("FieldDecl", start, names=names, typeRef=type_ref,
                          visibility=visibility)

    def _parse_variant_part(self) -> dict:
        start = self.current
        self.expect(TT.CASE)
        # Optional tag field: case Tag: Type of
        tag_name = None
        tag_type = None
        if self.is_ident() and self.peek().type == TT.COLON:
            tag_name = self.advance().value
            self.advance()  # :
        tag_type = self._parse_type_ref()
        self.expect(TT.OF)

        variants: List[dict] = []
        while not self.check(TT.END, TT.EOF):
            self.skip_compiler_dirs()
            if self.check(TT.END, TT.EOF):
                break
            v = self._parse_variant_case()
            variants.append(v)

        return self._node("VariantPart", start,
                          tagName=tag_name, tagType=tag_type, variants=variants)

    def _parse_variant_case(self) -> dict:
        start = self.current
        labels: List[dict] = []
        labels.append(self._parse_expr())
        while self.match(TT.COMMA):
            labels.append(self._parse_expr())
        self.expect(TT.COLON)
        self.expect(TT.LPAREN)
        fields: List[dict] = []
        while not self.check(TT.RPAREN, TT.EOF):
            if self.is_ident():
                fields.append(self._parse_record_field("public"))
            else:
                break
        self.expect(TT.RPAREN)
        self.match(TT.SEMI)
        return self._node("VariantCase", start, labels=labels, fields=fields)

    # ------------------------------------------------------------------
    # Interface / dispinterface / object types
    # ------------------------------------------------------------------

    def _parse_interface_type(self) -> dict:
        start = self.current
        self.expect(TT.INTERFACE)
        ancestors: List[dict] = []
        if self.check(TT.LPAREN):
            self.advance()
            ancestors.append(self._parse_type_ref())
            while self.match(TT.COMMA):
                ancestors.append(self._parse_type_ref())
            self.expect(TT.RPAREN)

        # GUID: ['...' ]
        guid = None
        if self.check(TT.LBRACKET):
            self.advance()
            guid = self.expect(TT.STRING).value
            self.expect(TT.RBRACKET)

        # Forward declaration
        if self.check(TT.SEMI) or self.current.type in (TT.EOF, TT.IMPLEMENTATION):
            return self._node("InterfaceType", start,
                              ancestors=ancestors, guid=guid,
                              isForward=True, members=[])

        members = self._parse_interface_body()
        self.expect(TT.END)
        return self._node("InterfaceType", start,
                          ancestors=ancestors, guid=guid,
                          isForward=False, members=members)

    def _parse_interface_body(self) -> List[dict]:
        members: List[dict] = []
        while not self.check(TT.END, TT.EOF):
            self.skip_compiler_dirs()
            if self.check(TT.END, TT.EOF):
                break
            t = self.current.type
            if t in (TT.PROCEDURE, TT.FUNCTION):
                members.append(self._parse_method_decl("public", False))
            elif t == TT.PROPERTY:
                members.append(self._parse_property_decl("public", False))
            else:
                members.append(self._node("Unknown", self.current,
                                          value=self.advance().value))
        return members

    def _parse_dispinterface_type(self) -> dict:
        start = self.current
        self.expect(TT.DISPINTERFACE)
        ancestors: List[dict] = []
        if self.check(TT.LPAREN):
            self.advance()
            ancestors.append(self._parse_type_ref())
            self.expect(TT.RPAREN)
        members = self._parse_interface_body()
        self.expect(TT.END)
        return self._node("DispinterfaceType", start,
                          ancestors=ancestors, members=members)

    def _parse_object_type(self) -> dict:
        start = self.current
        self.expect(TT.OBJECT)
        ancestors: List[dict] = []
        if self.check(TT.LPAREN):
            self.advance()
            ancestors.append(self._parse_type_ref())
            while self.match(TT.COMMA):
                ancestors.append(self._parse_type_ref())
            self.expect(TT.RPAREN)
        members = self._parse_class_body()
        self.expect(TT.END)
        return self._node("ObjectType", start,
                          ancestors=ancestors, members=members)

    # ------------------------------------------------------------------
    # Composite / structural types
    # ------------------------------------------------------------------

    def _parse_array_type(self, packed: bool = False) -> dict:
        start = self.current
        self.expect(TT.ARRAY)
        dimensions: List[dict] = []
        if self.check(TT.LBRACKET):
            self.advance()
            dimensions.append(self._parse_ordinal_type_or_range())
            while self.match(TT.COMMA):
                dimensions.append(self._parse_ordinal_type_or_range())
            self.expect(TT.RBRACKET)
        self.expect(TT.OF)
        element_type = self._parse_type_ref()
        return self._node("ArrayType", start,
                          packed=packed, dimensions=dimensions,
                          elementType=element_type)

    def _parse_set_type(self) -> dict:
        start = self.current
        self.expect(TT.SET)
        self.expect(TT.OF)
        base = self._parse_ordinal_type_or_range()
        return self._node("SetType", start, baseType=base)

    def _parse_file_type(self) -> dict:
        start = self.current
        self.expect(TT.FILE)
        record_type = None
        if self.check(TT.OF):
            self.advance()
            record_type = self._parse_type_ref()
        return self._node("FileType", start, recordType=record_type)

    def _parse_pointer_type(self) -> dict:
        start = self.current
        self.expect(TT.CARET)
        base = self._parse_type_ref()
        return self._node("PointerType", start, baseType=base)

    def _parse_packed_type(self) -> dict:
        start = self.current
        self.expect(TT.PACKED)
        t = self.current.type
        if t == TT.ARRAY:
            return self._parse_array_type(packed=True)
        if t == TT.RECORD:
            return self._parse_record_type(packed=True)
        inner = self._parse_type_def()
        return self._node("PackedType", start, inner=inner)

    def _parse_enum_type(self) -> dict:
        start = self.current
        self.expect(TT.LPAREN)
        values: List[dict] = []
        while not self.check(TT.RPAREN, TT.EOF):
            vs = self.current
            vname = self.expect_ident().value
            vval = None
            if self.check(TT.EQ):
                self.advance()
                vval = self._parse_expr()
            values.append(self._node("EnumValue", vs, name=vname, value=vval))
            self.match(TT.COMMA)
        self.expect(TT.RPAREN)
        return self._node("EnumType", start, values=values)

    def _parse_proc_type(self, is_function: bool) -> dict:
        start = self.current
        self.advance()  # procedure or function
        params = self._parse_param_list() if self.check(TT.LPAREN) else []
        ret_type = None
        if is_function and self.check(TT.COLON):
            self.advance()
            ret_type = self._parse_type_ref()
        # 'of object' or 'of class' suffixes
        of_object = False
        of_class = False
        if self.check(TT.OF):
            self.advance()
            if self.check(TT.OBJECT):
                self.advance(); of_object = True
            elif self.check(TT.CLASS):
                self.advance(); of_class = True
        ccs = self._collect_calling_conventions()
        return self._node("ProcType", start,
                          isFunction=is_function,
                          params=params,
                          returnType=ret_type,
                          ofObject=of_object,
                          ofClass=of_class,
                          callingConventions=ccs)

    def _parse_method_reference(self) -> dict:
        """Parse ``reference to procedure`` / ``reference to function``."""
        start = self.current
        self.expect(TT.D_REFERENCE)
        self.expect(TT.TO)
        inner = self._parse_proc_type(is_function=self.check(TT.FUNCTION))
        return self._node("MethodReference", start, procType=inner)

    # ------------------------------------------------------------------
    # Simple / alias / subrange types
    # ------------------------------------------------------------------

    def _parse_simple_type(self) -> dict:
        """Parse type aliases and subranges."""
        start = self.current
        left = self._parse_const_expr_or_type_ref()
        if self.check(TT.DOTDOT):
            self.advance()
            right = self._parse_expr()
            return self._node("SubrangeType", start, low=left, high=right)
        return left

    def _parse_const_expr_or_type_ref(self) -> dict:
        """Used for simple type alias; tries to parse a type reference first."""
        start = self.current
        if self.is_ident() or self.check(TT.STRING_KW):
            name = self._parse_extended_type_name()
            return name
        # literal subrange starting point
        return self._parse_expr()

    def _parse_type_ref(self) -> dict:
        """Parse a type reference (qualified name, possibly generic, possibly array of)."""
        start = self.current

        if self.check(TT.ARRAY):
            return self._parse_array_type()
        if self.check(TT.SET):
            return self._parse_set_type()
        if self.check(TT.FILE):
            return self._parse_file_type()
        if self.check(TT.CARET):
            return self._parse_pointer_type()
        if self.check(TT.PROCEDURE):
            return self._parse_proc_type(is_function=False)
        if self.check(TT.FUNCTION):
            return self._parse_proc_type(is_function=True)
        if self.check(TT.D_REFERENCE):
            return self._parse_method_reference()
        if self.check(TT.STRING_KW):
            self.advance()
            # string[N]
            max_len = None
            if self.check(TT.LBRACKET):
                self.advance()
                max_len = self._parse_expr()
                self.expect(TT.RBRACKET)
            return self._node("StringType", start, maxLength=max_len)

        return self._parse_extended_type_name()

    def _parse_extended_type_name(self) -> dict:
        """Parse QualifiedName<TypeArgs> type reference."""
        start = self.current
        name = self.parse_qualified_name()
        type_args: List[dict] = []
        if self.check(TT.LT):
            self.advance()
            type_args.append(self._parse_type_ref())
            while self.match(TT.COMMA):
                type_args.append(self._parse_type_ref())
            self.expect(TT.GT)
        return self._node("TypeRef", start, name=name, typeArgs=type_args)

    def _parse_ordinal_type_or_range(self) -> dict:
        """For array dimensions and set bases."""
        start = self.current
        left = self._parse_expr()
        if self.check(TT.DOTDOT):
            self.advance()
            right = self._parse_expr()
            return self._node("SubrangeType", start, low=left, high=right)
        return left

    # ------------------------------------------------------------------
    # Generic formal parameters  <T: IInterface; U: class>
    # ------------------------------------------------------------------

    def _parse_generic_formal_params(self) -> List[dict]:
        if not self.check(TT.LT):
            return []
        self.advance()
        params: List[dict] = []
        while not self.check(TT.GT, TT.EOF):
            start = self.current
            names = [self.expect_ident().value]
            while self.match(TT.COMMA):
                names.append(self.expect_ident().value)
            constraint = None
            if self.check(TT.COLON):
                self.advance()
                constraint = self._parse_type_ref()
            params.append(self._node("GenericParam", start,
                                     names=names, constraint=constraint))
            self.match(TT.SEMI)
        self.expect(TT.GT)
        return params

    # ==================================================================
    # Const section
    # ==================================================================

    def _parse_const_section(self) -> dict:
        start = self.current
        self.expect(TT.CONST)
        items: List[dict] = []
        while self.is_ident():
            try:
                items.append(self._parse_const_decl())
            except ParseError as exc:
                items.append(self._error_node(exc))
                self._recover_to(TT.SEMI, TT.END)
            self.skip_compiler_dirs()
        return self._node("ConstSection", start, items=items)

    def _parse_const_decl(self) -> dict:
        start = self.current
        name = self.expect_ident().value
        if self.check(TT.COLON):
            # Typed constant:  Name: Type = Value;
            self.advance()
            type_ref = self._parse_type_ref()
            self.expect(TT.EQ)
            value = self._parse_const_value()
            self.expect(TT.SEMI)
            return self._node("TypedConstDecl", start,
                              name=name, typeRef=type_ref, value=value)
        self.expect(TT.EQ)
        value = self._parse_const_value()
        hints = self._opt_deprecated_hint()
        self.expect(TT.SEMI)
        return self._node("ConstDecl", start, name=name, value=value, hints=hints)

    def _parse_const_value(self) -> Any:
        """Parse a constant value (may be a structured constant)."""
        if self.check(TT.LPAREN):
            # Structured constant: (field1: val1; field2: val2)
            return self._parse_structured_const()
        return self._parse_expr()

    def _parse_structured_const(self) -> dict:
        start = self.current
        self.expect(TT.LPAREN)
        items: List[dict] = []
        while not self.check(TT.RPAREN, TT.EOF):
            item_start = self.current
            if self.is_ident() and self.peek().type == TT.COLON:
                fname = self.advance().value
                self.advance()
                fval = self._parse_const_value()
                items.append(self._node("FieldInit", item_start, name=fname, value=fval))
            else:
                items.append(self._parse_expr())
            self.match(TT.SEMI)
        self.expect(TT.RPAREN)
        return self._node("StructuredConst", start, items=items)

    # ==================================================================
    # Var / threadvar section
    # ==================================================================

    def _parse_var_section(self) -> dict:
        start = self.current
        kw = self.advance().value.lower()  # var or threadvar
        items: List[dict] = []
        while self.is_ident():
            try:
                items.append(self._parse_var_decl())
            except ParseError as exc:
                items.append(self._error_node(exc))
                self._recover_to(TT.SEMI, TT.END)
            self.skip_compiler_dirs()
        return self._node("VarSection", start, keyword=kw, items=items)

    def _parse_var_decl(self) -> dict:
        start = self.current
        names = [self.expect_ident().value]
        while self.match(TT.COMMA):
            names.append(self.expect_ident().value)
        self.expect(TT.COLON)
        type_ref = self._parse_type_ref()
        init_val = None
        absolute = None
        if self.check(TT.D_ABSOLUTE):
            self.advance()
            if self.check(TT.INTEGER, TT.HEX):
                absolute = self.advance().value
            else:
                absolute = self.parse_qualified_name()
        elif self.check(TT.EQ):
            self.advance()
            init_val = self._parse_const_value()
        hints = self._opt_deprecated_hint()
        self.expect(TT.SEMI)
        return self._node("VarDecl", start,
                          names=names, typeRef=type_ref,
                          initialValue=init_val, absolute=absolute,
                          hints=hints)

    # ==================================================================
    # Label section
    # ==================================================================

    def _parse_label_section(self) -> dict:
        start = self.current
        self.expect(TT.LABEL)
        labels: List[str] = []
        labels.append(self.expect_ident().value)
        while self.match(TT.COMMA):
            labels.append(self.expect_ident().value)
        self.expect(TT.SEMI)
        return self._node("LabelSection", start, labels=labels)

    # ==================================================================
    # Resourcestring section
    # ==================================================================

    def _parse_resourcestring_section(self) -> dict:
        start = self.current
        self.expect(TT.RESOURCESTRING)
        items: List[dict] = []
        while self.is_ident():
            s = self.current
            name = self.advance().value
            self.expect(TT.EQ)
            value = self.expect(TT.STRING).value
            self.expect(TT.SEMI)
            items.append(self._node("ResourceStringDecl", s,
                                    name=name, value=value))
            self.skip_compiler_dirs()
        return self._node("ResourceStringSection", start, items=items)

    # ==================================================================
    # Exports clause
    # ==================================================================

    def _parse_exports_clause(self) -> dict:
        start = self.current
        self.expect(TT.EXPORTS)
        items: List[dict] = []
        while True:
            es = self.current
            name = self.parse_qualified_name()
            mods: dict = {}
            if self.check(TT.D_NAME):
                self.advance()
                mods["name"] = self.expect(TT.STRING).value
            if self.check(TT.D_INDEX):
                self.advance()
                mods["index"] = self._parse_expr()
            if self.check(TT.D_RESIDENT):
                self.advance(); mods["resident"] = True
            items.append(self._node("ExportItem", es, name=name, **mods))
            if not self.match(TT.COMMA):
                break
        self.expect(TT.SEMI)
        return self._node("ExportsClause", start, items=items)

    # ==================================================================
    # Routine declarations  (standalone and method implementations)
    # ==================================================================

    def _parse_routine_decl(self, allow_impl: bool = True) -> dict:  # noqa: C901
        start = self.current
        is_class = bool(self.match(TT.CLASS))
        kind_tok = self.advance()  # PROCEDURE, FUNCTION, CONSTRUCTOR, DESTRUCTOR, OPERATOR
        routine_kind = kind_tok.type.name.lower()

        # Qualified name (could be TClass.MethodName)
        name_parts = [self.expect_ident().value]
        while self.check(TT.DOT):
            self.advance()
            name_parts.append(self.expect_ident().value)
        name = ".".join(name_parts)

        generic_params = self._parse_generic_formal_params()
        params = self._parse_param_list() if self.check(TT.LPAREN) else []

        ret_type = None
        if kind_tok.type == TT.FUNCTION and self.check(TT.COLON):
            self.advance()
            ret_type = self._parse_type_ref()

        hints = self._opt_deprecated_hint()
        self.expect(TT.SEMI)
        directives = self._parse_routine_directives()

        body = None
        if allow_impl and not self._is_forward_or_external(directives):
            body = self._parse_routine_body()

        return self._node("RoutineDecl", start,
                          routineKind=routine_kind,
                          isClass=is_class,
                          name=name,
                          genericParams=generic_params,
                          params=params,
                          returnType=ret_type,
                          hints=hints,
                          directives=directives,
                          body=body)

    def _is_forward_or_external(self, directives: List[dict]) -> bool:
        for d in directives:
            if d.get("kind") in ("forward", "external"):
                return True
        return False

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def _parse_param_list(self) -> List[dict]:
        self.expect(TT.LPAREN)
        params: List[dict] = []
        if not self.check(TT.RPAREN):
            params.append(self._parse_param_group())
            while self.match(TT.SEMI):
                if self.check(TT.RPAREN):
                    break
                params.append(self._parse_param_group())
        self.expect(TT.RPAREN)
        return params

    def _parse_param_group(self) -> dict:
        start = self.current
        modifier = None
        if self.check(TT.CONST, TT.VAR, TT.OUT):
            modifier = self.advance().value.lower()

        # Array of T (open array parameter)
        if self.check(TT.ARRAY):
            self.advance()
            self.expect(TT.OF)
            if self.check(TT.CONST):
                self.advance()
                elem_type = None
            else:
                elem_type = self._parse_type_ref()
            return self._node("OpenArrayParam", start,
                              modifier=modifier, elementType=elem_type)

        names = [self.expect_ident().value]
        while self.match(TT.COMMA):
            names.append(self.expect_ident().value)

        type_ref = None
        default_val = None
        if self.check(TT.COLON):
            self.advance()
            # 'array of T' after colon
            if self.check(TT.ARRAY):
                self.advance()
                self.expect(TT.OF)
                if self.check(TT.CONST):
                    self.advance()
                    type_ref = self._node("OpenArrayType", start, elementType=None)
                else:
                    elem_t = self._parse_type_ref()
                    type_ref = self._node("OpenArrayType", start, elementType=elem_t)
            else:
                type_ref = self._parse_type_ref()

            if self.check(TT.EQ):
                self.advance()
                default_val = self._parse_expr()

        return self._node("ParamGroup", start,
                          modifier=modifier, names=names,
                          typeRef=type_ref, defaultValue=default_val)

    # ------------------------------------------------------------------
    # Routine directives
    # ------------------------------------------------------------------

    def _parse_routine_directives(self) -> List[dict]:  # noqa: C901
        directives: List[dict] = []
        while True:
            self.skip_compiler_dirs()
            t = self.current.type

            if t == TT.D_FORWARD:
                self.advance()
                directives.append({"kind": "forward"})
                self.match(TT.SEMI)
                break

            if t == TT.D_EXTERNAL:
                d = self._parse_external_directive()
                directives.append(d)
                break

            if t in ROUTINE_DIRECTIVES:
                directives.append(self._parse_single_directive())
                self.match(TT.SEMI)

            elif t == TT.D_MESSAGE:
                self.advance()
                expr = self._parse_expr()
                directives.append({"kind": "message", "value": expr})
                self.match(TT.SEMI)

            elif t == TT.D_DISPID:
                self.advance()
                expr = self._parse_expr()
                directives.append({"kind": "dispid", "value": expr})
                self.match(TT.SEMI)

            elif t == TT.D_DEPRECATED:
                self.advance()
                msg = None
                if self.check(TT.STRING):
                    msg = self.advance().value
                directives.append({"kind": "deprecated", "message": msg})
                self.match(TT.SEMI)

            else:
                break

        return directives

    def _parse_external_directive(self) -> dict:
        self.advance()  # external
        lib = None
        name = None
        if self.check(TT.STRING, TT.IDENT):
            lib = self._parse_expr()
        if self.check(TT.D_NAME):
            self.advance()
            name = self._parse_expr()
        if self.check(TT.D_INDEX):
            self.advance()
            self._parse_expr()  # consume index
        self.match(TT.SEMI)
        return {"kind": "external", "library": lib, "name": name}

    def _parse_single_directive(self) -> dict:
        tok = self.advance()
        return {"kind": tok.value.lower()}

    def _collect_calling_conventions(self) -> List[str]:
        ccs: List[str] = []
        while self.current.type in _CC:
            ccs.append(self.advance().value.lower())
        return ccs

    # ------------------------------------------------------------------
    # Routine body
    # ------------------------------------------------------------------

    def _parse_routine_body(self) -> dict:
        start = self.current
        local_decls = self._parse_decl_list(allow_impl=True)
        block = self._parse_block()
        self.expect(TT.SEMI)
        return self._node("RoutineBody", start,
                          localDecls=local_decls, block=block)

    def _parse_block(self) -> dict:
        self.skip_compiler_dirs()
        start = self.current
        self.expect(TT.BEGIN)
        stmts = self._parse_stmt_list()
        self.expect(TT.END)
        return self._node("Block", start, statements=stmts)

    # ==================================================================
    # Statements
    # ==================================================================

    def _parse_stmt_list(self) -> List[dict]:
        stmts: List[dict] = []
        while not self.check(TT.END, TT.UNTIL, TT.ELSE, TT.EXCEPT,
                              TT.FINALLY, TT.EOF):
            self.skip_compiler_dirs()
            if self.check(TT.END, TT.UNTIL, TT.ELSE, TT.EXCEPT,
                          TT.FINALLY, TT.EOF):
                break
            stmt = self._parse_stmt()
            if stmt is not None:
                stmts.append(stmt)
            # Consume semicolon(s)
            while self.match(TT.SEMI):
                pass
        return stmts

    def _parse_stmt(self) -> Optional[dict]:  # noqa: C901
        self.skip_compiler_dirs()
        t = self.current.type

        if t == TT.BEGIN:
            return self._parse_block()
        if t == TT.IF:
            return self._parse_if_stmt()
        if t == TT.CASE:
            return self._parse_case_stmt()
        if t == TT.FOR:
            return self._parse_for_stmt()
        if t == TT.WHILE:
            return self._parse_while_stmt()
        if t == TT.REPEAT:
            return self._parse_repeat_stmt()
        if t == TT.TRY:
            return self._parse_try_stmt()
        if t == TT.WITH:
            return self._parse_with_stmt()
        if t == TT.RAISE:
            return self._parse_raise_stmt()
        if t == TT.GOTO:
            return self._parse_goto_stmt()
        if t == TT.ASM:
            return self._parse_asm_block()
        if t == TT.INHERITED:
            return self._parse_inherited_stmt()
        if t == TT.SEMI:
            return None  # empty statement

        # Label: Foo:  (if identifier followed by colon that is NOT :=)
        if (self.is_ident() and self.peek().type == TT.COLON
                and self.peek(2).type != TT.EQ):
            return self._parse_labeled_stmt()

        # Assignment or procedure call
        if self.is_ident() or t in (TT.INHERITED, TT.AT):
            return self._parse_assign_or_call_stmt()

        # Unrecognised token – skip
        return self._node("Unknown", self.current, value=self.advance().value)

    def _parse_if_stmt(self) -> dict:
        start = self.current
        self.expect(TT.IF)
        cond = self._parse_expr()
        self.expect(TT.THEN)
        then_s = self._parse_stmt()
        else_s = None
        if self.match(TT.ELSE):
            else_s = self._parse_stmt()
        return self._node("IfStmt", start,
                          condition=cond, thenStmt=then_s, elseStmt=else_s)

    def _parse_case_stmt(self) -> dict:
        start = self.current
        self.expect(TT.CASE)
        expr = self._parse_expr()
        self.expect(TT.OF)
        items: List[dict] = []
        while not self.check(TT.ELSE, TT.END, TT.EOF):
            items.append(self._parse_case_item())
            while self.match(TT.SEMI):
                pass
        else_stmts: List[dict] = []
        if self.match(TT.ELSE):
            else_stmts = self._parse_stmt_list()
            self.match(TT.SEMI)
        self.expect(TT.END)
        return self._node("CaseStmt", start,
                          expression=expr, items=items, elseStmts=else_stmts)

    def _parse_case_item(self) -> dict:
        start = self.current
        labels: List[dict] = []
        labels.append(self._parse_case_label())
        while self.match(TT.COMMA):
            labels.append(self._parse_case_label())
        self.expect(TT.COLON)
        stmt = self._parse_stmt()
        return self._node("CaseItem", start, labels=labels, statement=stmt)

    def _parse_case_label(self) -> dict:
        start = self.current
        low = self._parse_expr()
        if self.check(TT.DOTDOT):
            self.advance()
            high = self._parse_expr()
            return self._node("CaseRange", start, low=low, high=high)
        return low

    def _parse_for_stmt(self) -> dict:
        start = self.current
        self.expect(TT.FOR)
        var = self.expect_ident().value
        # for..in (Delphi 2005+)
        if self.check(TT.IN):
            self.advance()
            collection = self._parse_expr()
            self.expect(TT.DO)
            body = self._parse_stmt()
            return self._node("ForInStmt", start,
                              variable=var, collection=collection, body=body)
        self.expect(TT.ASSIGN)
        init = self._parse_expr()
        direction = "to"
        if self.check(TT.TO):
            self.advance()
        elif self.check(TT.DOWNTO):
            self.advance(); direction = "downto"
        limit = self._parse_expr()
        self.expect(TT.DO)
        body = self._parse_stmt()
        return self._node("ForStmt", start,
                          variable=var, init=init,
                          direction=direction, limit=limit, body=body)

    def _parse_while_stmt(self) -> dict:
        start = self.current
        self.expect(TT.WHILE)
        cond = self._parse_expr()
        self.expect(TT.DO)
        body = self._parse_stmt()
        return self._node("WhileStmt", start, condition=cond, body=body)

    def _parse_repeat_stmt(self) -> dict:
        start = self.current
        self.expect(TT.REPEAT)
        stmts = self._parse_stmt_list()
        self.expect(TT.UNTIL)
        cond = self._parse_expr()
        return self._node("RepeatStmt", start, statements=stmts, condition=cond)

    def _parse_try_stmt(self) -> dict:
        start = self.current
        self.expect(TT.TRY)
        body = self._parse_stmt_list()

        if self.check(TT.EXCEPT):
            return self._parse_except_block(start, body)
        if self.check(TT.FINALLY):
            self.advance()
            finally_stmts = self._parse_stmt_list()
            self.expect(TT.END)
            return self._node("TryFinallyStmt", start,
                              body=body, finallyStmts=finally_stmts)
        raise self._error("Expected 'except' or 'finally' after try body")

    def _parse_except_block(self, start: Token, body: List[dict]) -> dict:
        self.expect(TT.EXCEPT)
        handlers: List[dict] = []
        # ON E: EClass DO stmt
        while self.check(TT.ON):
            hs = self.current
            self.advance()
            exc_var = None
            exc_type = None
            if self.is_ident() and self.peek().type == TT.COLON:
                exc_var = self.advance().value
                self.advance()  # :
            exc_type = self._parse_type_ref()
            self.expect(TT.DO)
            handler_stmt = self._parse_stmt()
            self.match(TT.SEMI)
            handlers.append(self._node("ExceptHandler", hs,
                                       variable=exc_var, exceptionType=exc_type,
                                       statement=handler_stmt))

        else_stmts: List[dict] = []
        if not handlers or self.check(TT.ELSE):
            else_stmts = self._parse_stmt_list()

        self.expect(TT.END)
        return self._node("TryExceptStmt", start,
                          body=body, handlers=handlers, elseStmts=else_stmts)

    def _parse_with_stmt(self) -> dict:
        start = self.current
        self.expect(TT.WITH)
        exprs: List[dict] = [self._parse_expr()]
        while self.match(TT.COMMA):
            exprs.append(self._parse_expr())
        self.expect(TT.DO)
        body = self._parse_stmt()
        return self._node("WithStmt", start, expressions=exprs, body=body)

    def _parse_raise_stmt(self) -> dict:
        start = self.current
        self.expect(TT.RAISE)
        expr = None
        if not self.check(TT.SEMI, TT.END, TT.ELSE, TT.EOF):
            expr = self._parse_expr()
            # raise expr at location
            if self.check_value("at"):
                self.advance()
                at_expr = self._parse_expr()
                return self._node("RaiseStmt", start, exception=expr, at=at_expr)
        return self._node("RaiseStmt", start, exception=expr, at=None)

    def _parse_goto_stmt(self) -> dict:
        start = self.current
        self.expect(TT.GOTO)
        label = self.expect_ident().value
        return self._node("GotoStmt", start, label=label)

    def _parse_labeled_stmt(self) -> dict:
        start = self.current
        label = self.advance().value  # identifier
        self.advance()  # :
        stmt = self._parse_stmt()
        return self._node("LabeledStmt", start, label=label, statement=stmt)

    def _parse_asm_block(self) -> dict:
        start = self.current
        self.expect(TT.ASM)
        raw_lines: List[str] = []
        # Consume everything until END
        depth = 1
        while self.pos < len(self.tokens):
            tok = self.current
            if tok.type == TT.ASM:
                depth += 1
            elif tok.type == TT.END:
                depth -= 1
                if depth == 0:
                    self.advance()
                    break
            raw_lines.append(tok.value)
            self.advance()
        return self._node("AsmBlock", start, body=" ".join(raw_lines))

    def _parse_inherited_stmt(self) -> dict:
        start = self.current
        self.expect(TT.INHERITED)
        if self.is_ident():
            name = self.advance().value
            args = self._parse_call_args() if self.check(TT.LPAREN) else []
            return self._node("InheritedCall", start, name=name, args=args)
        return self._node("InheritedCall", start, name=None, args=[])

    def _parse_assign_or_call_stmt(self) -> dict:
        start = self.current
        expr = self._parse_expr()
        if self.check(TT.ASSIGN):
            self.advance()
            value = self._parse_expr()
            return self._node("AssignStmt", start, target=expr, value=value)
        return self._node("CallStmt", start, expression=expr)

    # ==================================================================
    # Expressions  (Delphi operator precedence, lowest → highest)
    # ==================================================================

    def _parse_expr(self) -> dict:
        return self._parse_relational()

    def _parse_relational(self) -> dict:
        start = self.current
        left = self._parse_additive()
        while self.check(TT.EQ, TT.NEQ, TT.LT, TT.GT, TT.LTE, TT.GTE,
                         TT.IN, TT.IS, TT.AS):
            op = self.advance().value
            right = self._parse_additive()
            left = self._node("BinaryExpr", start,
                              operator=op, left=left, right=right)
            start = self.current
        return left

    def _parse_additive(self) -> dict:
        start = self.current
        left = self._parse_multiplicative()
        while self.check(TT.PLUS, TT.MINUS, TT.OR, TT.XOR):
            op = self.advance().value
            right = self._parse_multiplicative()
            left = self._node("BinaryExpr", start,
                              operator=op, left=left, right=right)
            start = self.current
        return left

    def _parse_multiplicative(self) -> dict:
        start = self.current
        left = self._parse_unary()
        while self.check(TT.STAR, TT.SLASH, TT.DIV, TT.MOD,
                         TT.AND, TT.SHL, TT.SHR):
            op = self.advance().value
            right = self._parse_unary()
            left = self._node("BinaryExpr", start,
                              operator=op, left=left, right=right)
            start = self.current
        return left

    def _parse_unary(self) -> dict:
        start = self.current
        if self.check(TT.NOT):
            op = self.advance().value
            operand = self._parse_unary()
            return self._node("UnaryExpr", start, operator=op, operand=operand)
        if self.check(TT.MINUS, TT.PLUS):
            op = self.advance().value
            operand = self._parse_unary()
            return self._node("UnaryExpr", start, operator=op, operand=operand)
        if self.check(TT.AT):
            op = self.advance().value
            operand = self._parse_unary()
            return self._node("AddressExpr", start, operand=operand)
        return self._parse_postfix()

    def _parse_postfix(self) -> dict:
        node = self._parse_primary()
        while True:
            if self.check(TT.DOT):
                self.advance()
                member = self.expect_ident().value
                # Speculatively try generic method call: .Method<T>
                type_args = None
                if self.check(TT.LT):
                    saved = self.pos
                    try:
                        type_args = self._parse_generic_args_expr()
                    except Exception:
                        self.pos = saved
                node = self._node("MemberAccess", node,
                                  obj=node, member=member,
                                  **({"typeArgs": type_args} if type_args else {}))
            elif self.check(TT.LBRACKET):
                self.advance()
                indices: List[dict] = [self._parse_expr()]
                while self.match(TT.COMMA):
                    indices.append(self._parse_expr())
                self.expect(TT.RBRACKET)
                node = self._node("IndexExpr", node,
                                  base=node, indices=indices)
            elif self.check(TT.CARET):
                self.advance()
                node = self._node("DerefExpr", node, base=node)
            elif self.check(TT.LPAREN):
                args = self._parse_call_args()
                node = self._node("CallExpr", node, callable=node, args=args)
            else:
                break
        return node

    def _parse_primary(self) -> dict:  # noqa: C901
        start = self.current
        t = self.current.type

        # Literals
        if t == TT.INTEGER:
            return self._node("IntegerLiteral", start, value=self.advance().value)
        if t == TT.FLOAT:
            return self._node("FloatLiteral", start, value=self.advance().value)
        if t == TT.HEX:
            return self._node("HexLiteral", start, value=self.advance().value)
        if t == TT.STRING:
            return self._node("StringLiteral", start, value=self.advance().value)
        if t == TT.CHAR:
            return self._node("CharLiteral", start, value=self.advance().value)
        if t == TT.NIL:
            self.advance()
            return self._node("NilLiteral", start)
        # Parenthesised expression
        if t == TT.LPAREN:
            self.advance()
            inner = self._parse_expr()
            self.expect(TT.RPAREN)
            return self._node("ParenExpr", start, expression=inner)

        # Set constructor  [a, b, c..d]
        if t == TT.LBRACKET:
            return self._parse_set_constructor()

        # Inherited
        if t == TT.INHERITED:
            self.advance()
            if self.is_ident():
                name = self.advance().value
                return self._node("InheritedExpr", start, name=name)
            return self._node("InheritedExpr", start, name=None)

        # Anonymous method / proc  procedure(...) begin ... end
        if t in (TT.PROCEDURE, TT.FUNCTION):
            return self._parse_anonymous_routine()

        # Identifier / keyword used as identifier (including True / False)
        if self.is_ident():
            name = self.advance().value
            if name.lower() in ("true", "false"):
                return self._node("BoolLiteral", start, value=name.lower() == "true")
            # Speculatively try to parse generic type args: Ident<T, U>
            # Save position so we can backtrack if '<' is really a comparison.
            if self.check(TT.LT):
                saved = self.pos
                try:
                    type_args = self._parse_generic_args_expr()
                    return self._node("Identifier", start, name=name,
                                      typeArgs=type_args)
                except Exception:
                    self.pos = saved
            return self._node("Identifier", start, name=name)

        # String keyword used as type cast / type reference
        if t == TT.STRING_KW:
            self.advance()
            return self._node("Identifier", start, name="string")

        raise self._error(
            f"Unexpected token in expression: {self.current.type.name} ({self.current.value!r})"
        )

    def _parse_generic_args_expr(self) -> List[dict]:
        """Parse '<' TypeRef {',' TypeRef} '>' in an expression context.

        Raises on any unexpected token so the caller can backtrack.
        """
        self.expect(TT.LT)
        args: List[dict] = [self._parse_type_ref()]
        while self.match(TT.COMMA):
            args.append(self._parse_type_ref())
        self.expect(TT.GT)
        return args

    def _parse_set_constructor(self) -> dict:
        start = self.current
        self.expect(TT.LBRACKET)
        elements: List[dict] = []
        while not self.check(TT.RBRACKET, TT.EOF):
            lo = self._parse_expr()
            if self.check(TT.DOTDOT):
                self.advance()
                hi = self._parse_expr()
                elements.append(self._node("SetRange", start, low=lo, high=hi))
            else:
                elements.append(lo)
            self.match(TT.COMMA)
        self.expect(TT.RBRACKET)
        return self._node("SetConstructor", start, elements=elements)

    def _parse_call_args(self) -> List[dict]:
        self.expect(TT.LPAREN)
        args: List[dict] = []
        if not self.check(TT.RPAREN):
            args.append(self._parse_expr())
            while self.match(TT.COMMA):
                args.append(self._parse_expr())
        self.expect(TT.RPAREN)
        return args

    def _parse_anonymous_routine(self) -> dict:
        start = self.current
        is_func = self.advance().type == TT.FUNCTION
        params = self._parse_param_list() if self.check(TT.LPAREN) else []
        ret_type = None
        if is_func and self.check(TT.COLON):
            self.advance()
            ret_type = self._parse_type_ref()
        self.match(TT.SEMI)
        local_decls = self._parse_decl_list(allow_impl=True)
        block = self._parse_block()
        return self._node("AnonymousRoutine", start,
                          isFunction=is_func,
                          params=params,
                          returnType=ret_type,
                          localDecls=local_decls,
                          block=block)

    # ==================================================================
    # Helpers
    # ==================================================================

    def _opt_deprecated_hint(self) -> List[str]:
        hints: List[str] = []
        while self.check(TT.D_DEPRECATED, TT.D_EXPERIMENTAL, TT.D_PLATFORM):
            tok = self.advance()
            hint = tok.value.lower()
            if tok.type == TT.D_DEPRECATED and self.check(TT.STRING):
                hint += f" {self.advance().value!r}"
            hints.append(hint)
        return hints

    def _node(self, kind: str, start_tok: Any, **fields) -> dict:
        node: dict = {"kind": kind}
        if isinstance(start_tok, Token):
            node["startPos"] = start_tok.pos_dict()
            node["endPos"] = self.tokens[max(0, self.pos - 1)].end_pos_dict()
        elif isinstance(start_tok, dict):
            node["startPos"] = start_tok.get("startPos")
            node["endPos"] = self.tokens[max(0, self.pos - 1)].end_pos_dict()
        node.update(fields)
        return node

    def _error_node(self, exc: ParseError) -> dict:
        return {
            "kind": "ParseError",
            "message": exc.message,
            "startPos": {"line": exc.line, "col": exc.column},
        }

    def _recover_to(self, *types: TT) -> None:
        """Skip tokens until one of *types* is found (consumed)."""
        while not self.check(TT.EOF, *types):
            self.advance()
        if not self.check(TT.EOF):
            self.advance()  # consume the recovery token


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def parse_pas(src: str, filename: str = "<unknown>") -> dict:
    """Tokenise and parse a Delphi .pas / .dpr source string; return AST dict."""
    tokens = tokenize(src, filename)
    return PasParser(tokens, filename).parse()
