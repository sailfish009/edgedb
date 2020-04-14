#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2008-present MagicStack Inc. and the EdgeDB authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


from __future__ import annotations

from typing import *

from edb.edgeql import ast as qlast
from edb.edgeql import compiler as qlcompiler
from edb.edgeql import qltypes

from . import delta as sd
from . import name as sn
from . import referencing
from . import objects as so

if TYPE_CHECKING:
    from . import schema as s_schema


class Annotation(so.QualifiedObject,
                 so.InheritingObject,
                 qlkind=qltypes.SchemaObjectClass.ANNOTATION):
    # Annotations cannot be renamed, so make sure the name
    # has low compcoef.
    name = so.SchemaField(
        sn.Name,  # type: ignore
        inheritable=False,
        compcoef=0.2,
    )

    inheritable = so.SchemaField(
        bool, default=False, compcoef=0.2)

    def get_verbosename(self,
                        schema: s_schema.Schema,
                        *,
                        with_parent: bool=False) -> str:
        vn = super().get_verbosename(schema)
        return f"abstract {vn}"


class AnnotationValue(referencing.ReferencedInheritingObject):

    subject = so.SchemaField(
        so.Object, compcoef=1.0, default=None, inheritable=False)

    annotation = so.SchemaField(
        Annotation, compcoef=0.429)

    value = so.SchemaField(
        str, compcoef=0.909)

    def __str__(self) -> str:
        return '<{}: at 0x{:x}>'.format(self.__class__.__name__, id(self))

    __repr__ = __str__

    @classmethod
    def get_schema_class_displayname(cls) -> str:
        return 'annotation'

    def get_verbosename(self,
                        schema: s_schema.Schema,
                        *,
                        with_parent: bool=False) -> str:
        vn = super().get_verbosename(schema)
        if with_parent:
            subject = self.get_subject(schema)
            assert subject is not None
            pvn = subject.get_verbosename(schema, with_parent=True)
            return f'{vn} of {pvn}'
        else:
            return vn


class AnnotationSubject(so.Object):

    annotations_refs = so.RefDict(
        attr='annotations',
        ref_cls=AnnotationValue)

    annotations = so.SchemaField(
        so.ObjectIndexByShortname[AnnotationValue],
        inheritable=False, ephemeral=True, coerce=True, compcoef=0.909,
        default=so.DEFAULT_CONSTRUCTOR)

    def add_annotation(self,
                       schema: s_schema.Schema,
                       annotation: AnnotationValue,
                       replace: bool = False) -> s_schema.Schema:
        schema = self.add_classref(
            schema, 'annotations', annotation, replace=replace)
        return schema

    def del_annotation(self,
                       schema: s_schema.Schema,
                       annotation_name: str) -> s_schema.Schema:
        shortname = sn.shortname_from_fullname(annotation_name)
        return self.del_classref(schema, 'annotations', shortname)

    def get_annotation(self,
                       schema: s_schema.Schema,
                       name: str) -> Optional[str]:
        attrval = self.get_annotations(schema).get(schema, name, None)
        return attrval.get_value(schema) if attrval is not None else None


class AnnotationCommandContext(sd.ObjectCommandContext[Annotation]):
    pass


class AnnotationCommand(sd.QualifiedObjectCommand[Annotation],
                        schema_metaclass=Annotation,
                        context_class=AnnotationCommandContext):
    pass


class CreateAnnotation(AnnotationCommand, sd.CreateObject[Annotation]):
    astnode = qlast.CreateAnnotation

    @classmethod
    def _cmd_tree_from_ast(cls,
                           schema: s_schema.Schema,
                           astnode: qlast.DDLOperation,
                           context: sd.CommandContext) -> CreateAnnotation:
        cmd = super()._cmd_tree_from_ast(schema,
                                         astnode,
                                         context)

        assert isinstance(astnode, qlast.CreateAnnotation)

        cmd.set_attribute_value('inheritable', astnode.inheritable)
        cmd.set_attribute_value('is_abstract', True)

        assert isinstance(cmd, CreateAnnotation)
        return cmd

    def _apply_field_ast(self,
                         schema: s_schema.Schema,
                         context: sd.CommandContext,
                         node: qlast.DDLOperation,
                         op: sd.AlterObjectProperty) -> None:
        if op.property == 'inheritable':
            node.inheritable = op.new_value
        else:
            super()._apply_field_ast(schema, context, node, op)


class AlterAnnotation(AnnotationCommand, sd.AlterObject[Annotation]):
    pass


class DeleteAnnotation(AnnotationCommand, sd.DeleteObject[Annotation]):
    astnode = qlast.DropAnnotation


class AnnotationSubjectCommandContext:
    pass


class AnnotationSubjectCommand(sd.ObjectCommand[so.Object]):
    pass


class AnnotationValueCommandContext(sd.ObjectCommandContext[AnnotationValue]):
    pass


class AnnotationValueCommand(
    referencing.ReferencedInheritingObjectCommand[AnnotationValue],
    schema_metaclass=AnnotationValue,
    context_class=AnnotationValueCommandContext,
    referrer_context_class=AnnotationSubjectCommandContext,
):

    def add_annotation(self,
                       schema: s_schema.Schema,
                       annotation: AnnotationValue,
                       parent: AnnotationSubject) -> s_schema.Schema:
        return parent.add_annotation(schema, annotation, replace=True)

    def del_annotation(self,
                       schema: s_schema.Schema,
                       annotation_name: str,
                       parent: AnnotationSubject) -> s_schema.Schema:
        return parent.del_annotation(schema, annotation_name)


class CreateAnnotationValue(
    AnnotationValueCommand,
    referencing.CreateReferencedInheritingObject[AnnotationValue],
):
    astnode = qlast.CreateAnnotationValue
    referenced_astnode = qlast.CreateAnnotationValue

    @classmethod
    def _cmd_tree_from_ast(
        cls,
        schema: s_schema.Schema,
        astnode: qlast.DDLOperation,
        context: sd.CommandContext
    ) -> CreateAnnotationValue:

        assert isinstance(astnode, qlast.CreateAnnotationValue)
        cmd = super()._cmd_tree_from_ast(schema, astnode, context)
        propname = sn.shortname_from_fullname(cmd.classname)

        value = qlcompiler.evaluate_ast_to_python_val(
            astnode.value, schema=schema)

        if not isinstance(value, str):
            raise ValueError(
                f'unexpected value type in AnnotationValue: {value!r}')

        attr: Annotation = schema.get(propname)

        cmd.set_attribute_value('annotation', attr)
        cmd.set_attribute_value('value', value)
        cmd.set_attribute_value('is_final', not attr.get_inheritable(schema))

        assert isinstance(cmd, CreateAnnotationValue)
        return cmd

    def _apply_field_ast(self,
                         schema: s_schema.Schema,
                         context: sd.CommandContext,
                         node: qlast.DDLOperation,
                         op: sd.AlterObjectProperty) -> None:
        if op.property == 'value':
            assert isinstance(op.new_value, str)
            node.value = qlast.StringConstant.from_python(op.new_value)
        else:
            super()._apply_field_ast(schema, context, node, op)


class AlterAnnotationValue(
    AnnotationValueCommand,
    referencing.AlterReferencedInheritingObject[AnnotationValue],
):

    astnode = qlast.AlterAnnotationValue
    referenced_astnode = qlast.AlterAnnotationValue

    @classmethod
    def _cmd_tree_from_ast(
        cls,
        schema: s_schema.Schema,
        astnode: qlast.DDLOperation,
        context: sd.CommandContext
    ) -> AlterAnnotationValue:
        assert isinstance(astnode, qlast.AlterAnnotationValue)

        cmd = super()._cmd_tree_from_ast(schema, astnode, context)

        value = qlcompiler.evaluate_ast_to_python_val(
            astnode.value, schema=schema)

        if not isinstance(value, str):
            raise ValueError(
                f'unexpected value type in AnnotationValue: {value!r}')

        cmd.set_attribute_value(
            'value',
            value,
        )

        assert isinstance(cmd, AlterAnnotationValue)

        return cmd

    def _apply_field_ast(
        self,
        schema: s_schema.Schema,
        context: sd.CommandContext,
        node: qlast.DDLOperation,
        op: sd.AlterObjectProperty
    ) -> None:
        assert isinstance(node, qlast.AlterAnnotationValue)

        if op.property == 'value':
            assert isinstance(op.new_value, str)
            node.value = qlast.StringConstant.from_python(op.new_value)
        else:
            super()._apply_field_ast(schema, context, node, op)


class DeleteAnnotationValue(
    AnnotationValueCommand,
    referencing.DeleteReferencedInheritingObject[AnnotationValue],
):

    astnode = qlast.DropAnnotationValue
