#include "importer.h"

#include <openssl/crypto.h>

#include <string>

namespace {

constexpr const char* importer_bootstrap = R"PY(
import importlib.abc
import importlib.machinery
import importlib.util
import io
import json
import marshal
import os
import sys
import zipfile

_archive = zipfile.ZipFile(io.BytesIO(_lexora_archive_bytes))
_manifest = json.loads(_archive.read("manifest.json"))["modules"]
del _lexora_archive_bytes

class _LexoraFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        metadata = _manifest.get(fullname)
        if metadata is None:
            return None
        if metadata.get("namespace"):
            spec = importlib.machinery.ModuleSpec(fullname, None, is_package=True)
            spec.origin = metadata["origin"]
            spec.submodule_search_locations = [metadata["origin"]]
            return spec
        return importlib.util.spec_from_loader(
            fullname,
            self,
            origin=metadata["origin"],
            is_package=bool(metadata["package"]),
        )

    def create_module(self, spec):
        return None

    def get_filename(self, fullname):
        return _manifest[fullname]["origin"]

    def get_code(self, fullname):
        metadata = _manifest[fullname]
        payload = _archive.read(metadata["entry"])
        if len(payload) <= 16 or payload[:4] != importlib.util.MAGIC_NUMBER:
            raise ImportError(f"invalid protected bytecode for {fullname}")
        return marshal.loads(payload[16:])

    def exec_module(self, module):
        metadata = _manifest[module.__spec__.name]
        module.__file__ = metadata["origin"]
        module.__cached__ = metadata["origin"]
        if metadata["package"]:
            module.__path__ = [os.path.dirname(metadata["origin"])]
        exec(self.get_code(module.__spec__.name), module.__dict__)

sys.meta_path.insert(0, _LexoraFinder())
)PY";

bool set_runtime_arguments(int argc, char** argv) {
    PyObject* sys_module = PyImport_ImportModule("sys");
    if (!sys_module) {
        return false;
    }
    PyObject* arguments = PyList_New(argc - 2);
    if (!arguments) {
        Py_DECREF(sys_module);
        return false;
    }
    for (int index = 2; index < argc; ++index) {
        PyObject* value = PyUnicode_DecodeFSDefault(argv[index]);
        if (!value) {
            Py_DECREF(arguments);
            Py_DECREF(sys_module);
            return false;
        }
        PyList_SET_ITEM(arguments, index - 2, value);
    }
    if (PyList_GET_SIZE(arguments) == 0) {
        PyObject* module_name = PyUnicode_DecodeFSDefault(argv[2]);
        if (!module_name || PyList_Append(arguments, module_name) != 0) {
            Py_XDECREF(module_name);
            Py_DECREF(arguments);
            Py_DECREF(sys_module);
            return false;
        }
        Py_DECREF(module_name);
    }
    const int argv_result = PyObject_SetAttrString(sys_module, "argv", arguments);
    Py_DECREF(arguments);
    if (argv_result != 0) {
        Py_DECREF(sys_module);
        return false;
    }
    PyObject* executable = PyUnicode_DecodeFSDefault(argv[0]);
    const int executable_result = executable
        ? PyObject_SetAttrString(sys_module, "executable", executable)
        : -1;
    Py_XDECREF(executable);
    Py_DECREF(sys_module);
    return executable_result == 0;
}

}  // namespace

namespace lexora {

bool install_importer(std::vector<unsigned char>& archive) {
    PyObject* main_module = PyImport_AddModule("__main__");
    if (!main_module) {
        return false;
    }
    PyObject* globals = PyModule_GetDict(main_module);
    PyObject* archive_bytes = PyBytes_FromStringAndSize(
        reinterpret_cast<const char*>(archive.data()), static_cast<Py_ssize_t>(archive.size()));
    if (!archive_bytes) {
        return false;
    }
    const int set_result = PyDict_SetItemString(globals, "_lexora_archive_bytes", archive_bytes);
    Py_DECREF(archive_bytes);
    OPENSSL_cleanse(archive.data(), archive.size());
    archive.clear();
    archive.shrink_to_fit();
    if (set_result != 0) {
        return false;
    }
    PyObject* result = PyRun_String(importer_bootstrap, Py_file_input, globals, globals);
    if (!result) {
        return false;
    }
    Py_DECREF(result);
    return true;
}

bool run_module(int argc, char** argv) {
    if (argc < 3 || std::string(argv[1]) != "-m") {
        PyErr_SetString(PyExc_ValueError, "usage: /app/loader -m <module> [arguments...]");
        return false;
    }
    if (!set_runtime_arguments(argc, argv)) {
        return false;
    }

    PyObject* runpy = PyImport_ImportModule("runpy");
    if (!runpy) {
        return false;
    }
    PyObject* function = PyObject_GetAttrString(runpy, "run_module");
    Py_DECREF(runpy);
    if (!function) {
        return false;
    }
    PyObject* module_name = PyUnicode_DecodeFSDefault(argv[2]);
    PyObject* positional = module_name ? PyTuple_Pack(1, module_name) : nullptr;
    Py_XDECREF(module_name);
    PyObject* keywords = Py_BuildValue("{s:s,s:O}", "run_name", "__main__", "alter_sys", Py_True);
    PyObject* result = positional && keywords ? PyObject_Call(function, positional, keywords) : nullptr;
    Py_XDECREF(keywords);
    Py_XDECREF(positional);
    Py_DECREF(function);
    if (!result) {
        return false;
    }
    Py_DECREF(result);
    return true;
}

}  // namespace lexora
