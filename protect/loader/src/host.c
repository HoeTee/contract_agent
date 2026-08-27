#include <dlfcn.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

typedef int (*loader_main_fn)(int, char**);

static int resolve_library_path(char* out, size_t out_size) {
    char exe_path[PATH_MAX];
    const ssize_t length = readlink("/proc/self/exe", exe_path, sizeof(exe_path) - 1);
    if (length <= 0) {
        return -1;
    }
    exe_path[length] = '\0';
    char* slash = strrchr(exe_path, '/');
    if (!slash) {
        return -1;
    }
    *(slash + 1) = '\0';
    if (snprintf(out, out_size, "%slibloader.vmp.so", exe_path) >= (int)out_size) {
        return -1;
    }
    return 0;
}

int main(int argc, char** argv) {
    char library[PATH_MAX];
    if (resolve_library_path(library, sizeof(library)) != 0) {
        fprintf(stderr, "host: cannot resolve libloader.vmp.so path\n");
        return 125;
    }
    void* handle = dlopen(library, RTLD_NOW | RTLD_GLOBAL);
    if (!handle) {
        fprintf(stderr, "host: dlopen %s failed: %s\n", library, dlerror());
        return 127;
    }
    loader_main_fn entry = (loader_main_fn)dlsym(handle, "lexora_loader_main");
    if (!entry) {
        fprintf(stderr, "host: dlsym lexora_loader_main failed: %s\n", dlerror());
        dlclose(handle);
        return 126;
    }
    int result = entry(argc, argv);
    dlclose(handle);
    return result;
}
