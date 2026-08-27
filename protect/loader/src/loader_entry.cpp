#include "crypto.h"
#include "importer.h"

#include <Python.h>

#include <exception>
#include <iostream>
#include <string>

extern "C" __attribute__((visibility("default"))) int lexora_loader_main(int argc, char** argv) {
    try {
        auto archive = lexora::decrypt_archive("/app/code.bin");

        PyConfig config;
        PyConfig_InitPythonConfig(&config);
        config.parse_argv = 0;
        PyStatus status = PyConfig_SetBytesString(&config, &config.program_name, argv[0]);
        if (!PyStatus_Exception(status)) {
            status = Py_InitializeFromConfig(&config);
        }
        PyConfig_Clear(&config);
        if (PyStatus_Exception(status)) {
            Py_ExitStatusException(status);
        }

        const bool ok = lexora::install_importer(archive) && lexora::run_module(argc, argv);
        if (!ok) {
            PyErr_Print();
        }
        const int finalize_status = Py_FinalizeEx();
        return ok && finalize_status >= 0 ? 0 : 1;
    }
    catch (const std::exception& error) {
        std::cerr << "loader: " << error.what() << '\n';
        return 1;
    }
}
