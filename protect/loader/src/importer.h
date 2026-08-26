#pragma once

#include <Python.h>

#include <vector>

namespace lexora {

bool install_importer(std::vector<unsigned char>& archive);
bool run_module(int argc, char** argv);

}
