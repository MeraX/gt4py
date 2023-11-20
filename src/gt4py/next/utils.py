# GT4Py - GridTools Framework
#
# Copyright (c) 2014-2023, ETH Zurich
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

from typing import Any, ClassVar, TypeGuard, TypeVar, Callable


class RecursionGuard:
    """
    Context manager to guard against inifinite recursion.

    >>> def foo(i):
    ...    with RecursionGuard(i):
    ...        if i % 2 == 0:
    ...            foo(i)
    ...    return i
    >>> foo(3)
    3
    >>> foo(2)  # doctest:+ELLIPSIS
    Traceback (most recent call last):
        ...
    gt4py.next.utils.RecursionGuard.RecursionDetected
    """

    guarded_objects: ClassVar[set[int]] = set()

    obj: Any

    class RecursionDetected(Exception):
        pass

    def __init__(self, obj: Any):
        self.obj = obj

    def __enter__(self):
        if id(self.obj) in self.guarded_objects:
            raise self.RecursionDetected()
        self.guarded_objects.add(id(self.obj))

    def __exit__(self, *exc):
        self.guarded_objects.remove(id(self.obj))


_T = TypeVar("_T")
_S = TypeVar("_S")


def is_tuple_of(v: Any, t: type[_T]) -> TypeGuard[tuple[_T, ...]]:
    return isinstance(v, tuple) and all(isinstance(e, t) for e in v)


def get_common_tuple_value(fun: Callable[[_T], _S], value: tuple[_T | tuple, ...] | _T) -> _S:
    if isinstance(value, tuple):
        all_res = tuple(get_common_tuple_value(fun, v) for v in value)
        assert all(v == all_res[0] for v in all_res)
        return all_res[0]
    return fun(value)

    # def _construct_scan_array(domain, init):
    #     if isinstance(init, tuple):
    #         return tuple(_construct_scan_array(domain, v) for v in init)
    #     return constructors.empty(domain, dtype=type(init))


def apply_to_tuple_elems(fun, *args):
    if isinstance(args[0], tuple):
        assert all(isinstance(arg, tuple) for arg in args)
        return tuple(apply_to_tuple_elems(fun, *arg) for arg in zip(*args))
    return fun(*args)
