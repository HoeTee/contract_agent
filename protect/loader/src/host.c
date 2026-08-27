#include <dlfcn.h>
#include <stdio.h>

typedef int (*loader_main_fn)(int, char**);

int main(int argc, char** argv) {
    const char* library = "/app/libloader.vmp.so";
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
