# GTC Toolchain - GT4Py Project - GridTools Framework
#
# Copyright (c) 2014-2022, ETH Zurich
# All rights reserved.
#
# This file is part of the GT4Py project and the GridTools framework.
# GT4Py is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or any later
# version. See the LICENSE.txt file at the top-level directory of this
# distribution for a copy of the license or check <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import base64
import pickle
from typing import Dict, List, Set, Union

import dace.data
import dace.dtypes
import dace.properties
import dace.subsets
import numpy as np
from dace import library

from gtc import common
from gtc import daceir as dcir
from gtc import oir
from gtc.definitions import Extent
from gtc.oir import Decl, FieldDecl, VerticalLoop, VerticalLoopSection

from .expansion.utils import get_dace_debuginfo
from .expansion_specification import ExpansionItem, make_expansion_order


def _set_expansion_order(
    node: "StencilComputation", expansion_order: Union[List[ExpansionItem], List[str]]
):
    res = make_expansion_order(node, expansion_order)
    node._expansion_specification = res


@library.node
class StencilComputation(library.LibraryNode):
    implementations: Dict[str, dace.library.ExpandTransformation] = {}
    default_implementation = "default"

    oir_node = dace.properties.DataclassProperty(dtype=VerticalLoop, allow_none=True)

    declarations = dace.properties.DictProperty(key_type=str, value_type=Decl, allow_none=True)
    extents = dace.properties.DictProperty(key_type=int, value_type=Extent, allow_none=False)

    expansion_specification = dace.properties.ListProperty(
        element_type=ExpansionItem,
        allow_none=True,
        setter=_set_expansion_order,
    )
    tile_sizes = dace.properties.DictProperty(
        key_type=str,
        value_type=int,
        default={dcir.Axis.I: 64, dcir.Axis.J: 8, dcir.Axis.K: 8},
    )
    device = dace.properties.EnumProperty(
        dtype=dace.DeviceType, default=dace.DeviceType.CPU, allow_none=True
    )

    symbol_mapping = dace.properties.DictProperty(
        key_type=str, value_type=object, default=None, allow_none=True
    )
    _dace_library_name = "StencilComputation"

    def __init__(
        self,
        name="unnamed_vloop",
        oir_node: VerticalLoop = None,
        extents: Dict[int, Extent] = None,
        declarations: Dict[str, Decl] = None,
        expansion_order=None,
        *args,
        **kwargs,
    ):
        super().__init__(name=name, *args, **kwargs)

        if oir_node is not None:
            assert extents is not None
            assert declarations is not None
            extents_dict = dict()
            for i, section in enumerate(oir_node.sections):
                for j, he in enumerate(section.horizontal_executions):
                    extents_dict[j * len(oir_node.sections) + i] = extents[id(he)]

            self.oir_node = oir_node
            self.extents = extents_dict
            self.declarations = declarations
            self.symbol_mapping = {
                decl.name: dace.symbol(
                    decl.name,
                    dtype=dace.typeclass(np.dtype(common.data_type_to_typestr(decl.dtype)).type),
                )
                for decl in declarations.values()
                if isinstance(decl, oir.ScalarDecl)
            }
            self.symbol_mapping.update(
                {
                    axis.domain_symbol(): dace.symbol(axis.domain_symbol(), dtype=dace.int32)
                    for axis in dcir.Axis.dims_horizontal()
                }
            )
            if any(
                interval.start.level == common.LevelMarker.END
                or interval.end.level == common.LevelMarker.END
                for interval in oir_node.iter_tree()
                .if_isinstance(VerticalLoopSection)
                .getattr("interval")
            ) or any(
                decl.dimensions[dcir.Axis.K.to_idx()]
                for decl in self.declarations.values()
                if isinstance(decl, oir.FieldDecl)
            ):
                self.symbol_mapping[dcir.Axis.K.domain_symbol()] = dace.symbol(
                    dcir.Axis.K.domain_symbol(), dtype=dace.int32
                )

            self.debuginfo = get_dace_debuginfo(oir_node)

        if expansion_order is None:
            expansion_order = [
                "TileI",
                "TileJ",
                "Sections",
                "K",  # Expands to either Loop or Map
                "Stages",
                "I",
                "J",
            ]
        _set_expansion_order(self, expansion_order)

    def get_extents(self, he):
        for i, section in enumerate(self.oir_node.sections):
            for j, cand_he in enumerate(section.horizontal_executions):
                if he is cand_he:
                    return self.extents[j * len(self.oir_node.sections) + i]

    @property
    def field_decls(self) -> Dict[str, FieldDecl]:
        return {
            name: decl for name, decl in self.declarations.items() if isinstance(decl, FieldDecl)
        }

    def to_json(self, parent):
        protocol = pickle.DEFAULT_PROTOCOL
        pbytes = pickle.dumps(self, protocol=protocol)

        jsonobj = super().to_json(parent)
        jsonobj["classpath"] = dace.nodes.full_class_path(self)
        jsonobj["attributes"]["protocol"] = protocol
        jsonobj["attributes"]["pickle"] = base64.b64encode(pbytes).decode("utf-8")

        return jsonobj

    @classmethod
    def from_json(cls, json_obj, context=None):
        if "attributes" not in json_obj:
            b64string = json_obj["pickle"]
        else:
            b64string = json_obj["attributes"]["pickle"]
        byte_repr = base64.b64decode(b64string)
        return pickle.loads(byte_repr)

    @property
    def free_symbols(self) -> Set[str]:
        result: Set[str] = set()
        for v in self.symbol_mapping.values():
            result.update(map(str, v.free_symbols))
        return result