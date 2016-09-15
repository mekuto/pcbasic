"""
PC-BASIC - userfunctions.py
User-defined functions.

(c) 2013, 2014, 2015, 2016 Rob Hagemans
This file is released under the GNU GPL version 3 or later.
"""

import struct

from . import error
from . import codestream
from . import values
from . import tokens as tk


class UserFunction(object):
    """User-defined function."""

    def __init__(self, name, code_stream, varnames, memory):
        """Define function."""
        self._codestream = code_stream
        self._start_loc = code_stream.tell()
        self._is_parsing = False
        self._memory = memory
        self._varnames = varnames
        self._sigil = name[-1]

    def get_conversions(self):
        """Retrieve list of argument type conversions."""
        # read variables
        return [values.TYPE_TO_CONV[self._memory.complete_name(name)[-1]] for name in self._varnames]

    def evaluate(self, expression_parser, *args):
        """Evaluate user-defined function."""
        # parse/evaluate arguments
        # recursion is not allowed as there's no way to terminate it
        if self._is_parsing:
            raise error.RunError(error.OUT_OF_MEMORY)
        # parse/evaluate function expression
        # save existing vars
        varsave = {}
        for name in self._varnames:
            if name in self._memory.scalars:
                # copy the buffer
                varsave[name] = self._memory.scalars.view(name).clone()
        # set variables
        for name, value in zip(self._varnames, args):
            # append sigil, if missing
            name = self._memory.complete_name(name)
            self._memory.scalars.set(name, value)
        # set recursion flag
        self._is_parsing = True
        save_loc = self._codestream.tell()
        try:
            self._codestream.seek(self._start_loc)
            value = expression_parser.parse(self._codestream)
            return values.to_type(self._sigil, value)
        finally:
            self._codestream.seek(save_loc)
            # unset recursion flag
            self._is_parsing = False
            # restore existing vars
            for name in varsave:
                # re-assign the stored value
                self._memory.scalars.view(name).copy_from(varsave[name])



class UserFunctionManager(object):
    """User-defined function handler."""

    def __init__(self, memory, values):
        """Initialise functions."""
        self._fn_dict = {}
        # state variable for detecting recursion
        self._memory = memory
        self._values = values

    def __contains__(self, name):
        """Check if a function of the given (complete) name exists."""
        return self._memory.complete_name(name) in self._fn_dict

    def clear(self):
        """Clear all user-defined functions."""
        self._fn_dict.clear()

    def get(self, fnname):
        """Retrieve function by name."""
        # append sigil, if missing
        fnname = self._memory.complete_name(fnname)
        # parse/evaluate arguments
        try:
            return self._fn_dict[fnname]
        except KeyError:
            raise error.RunError(error.UNDEFINED_USER_FUNCTION)

    def define(self, fnname, ins):
        """Define a function."""
        pointer_loc = self._memory.code_start + ins.tell()
        # read parameters
        fnvars = []
        if ins.skip_blank_read_if(('(',)):
            while True:
                name = ins.read_name()
                # must not be empty
                error.throw_if(not name, error.STX)
                # do not append sigil here yet, leave until evaluation time
                fnvars.append(name)
                if ins.skip_blank() in tk.END_STATEMENT + (')',):
                    break
                ins.require_read((',',))
            ins.require_read((')',))
        # read code
        ins.require_read((tk.O_EQ,)) #=
        self._fn_dict[fnname] = UserFunction(fnname, ins, fnvars, self._memory)
        ins.skip_to(tk.END_STATEMENT)
        # update memory model
        # allocate function pointer
        pointer = struct.pack('<H', pointer_loc) + bytearray(values.size_bytes(fnname)-2)
        # function name is represented with first char shifted by 128
        memory_name = chr(128+ord(fnname[0])) + fnname[1:]
        self._memory.scalars.set(memory_name, self._values.from_bytes(pointer))
        for name in fnvars:
            # allocate, but don't set, variables
            name = self._memory.complete_name(name)
            self._memory.scalars.set(name)
