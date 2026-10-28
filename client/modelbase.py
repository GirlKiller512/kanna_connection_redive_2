"""Adapt legacy protocol declarations to Pydantic 2 (based on autopcr PR #338)."""
import types
import typing

from pydantic import BaseModel
from pydantic.fields import FieldInfo

try:
    import annotationlib
except ImportError:
    annotationlib = None


class _ImplicitOptionalMeta(type(BaseModel)):
    def __new__(mcs, name, bases, namespace, **kwargs):
        annotations = namespace.get("__annotations__")
        if annotations is None and annotationlib is not None:
            annotate = annotationlib.get_annotate_from_class_namespace(namespace)
            if annotate is not None:
                annotations = annotationlib.call_annotate_function(
                    annotate, annotationlib.Format.FORWARDREF
                )
        annotations = dict(annotations or {})

        for field_name, annotation in list(annotations.items()):
            declaration = namespace.get(field_name, ...)
            if field_name.startswith("_"):
                if isinstance(declaration, FieldInfo):
                    annotations.pop(field_name)
                    namespace.pop(field_name, None)
                continue

            if isinstance(annotation, str):
                continue
            origin = typing.get_origin(annotation)
            if origin is typing.ClassVar:
                continue

            default = (
                declaration.default
                if isinstance(declaration, FieldInfo)
                else declaration
            )
            nullable = annotation is typing.Any or annotation is type(None)
            if origin in (typing.Union, types.UnionType):
                nullable = nullable or type(None) in typing.get_args(annotation)
            if default is None and not nullable:
                annotations[field_name] = typing.Optional[annotation]

        namespace["__annotations__"] = annotations
        return super().__new__(mcs, name, bases, namespace, **kwargs)


class GameBaseModel(BaseModel, metaclass=_ImplicitOptionalMeta):
    pass
