#include "crypto.h"

#include "key_data.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <fstream>
#include <iterator>
#include <memory>
#include <stdexcept>

#include <openssl/crypto.h>
#include <openssl/evp.h>

namespace {

constexpr std::array<unsigned char, 8> package_magic = {'L', 'E', 'X', 'O', 'R', 'A', '1', '\0'};
constexpr std::size_t nonce_size = 12;
constexpr std::size_t tag_size = 16;

using cipher_context = std::unique_ptr<EVP_CIPHER_CTX, decltype(&EVP_CIPHER_CTX_free)>;

std::vector<unsigned char> read_binary_file(const std::string& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("cannot open encrypted code package: " + path);
    }
    return std::vector<unsigned char>(
        std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
}

std::array<unsigned char, 32> reconstruct_key() {
    std::array<unsigned char, 32> key{};
    for (std::size_t index = 0; index < key.size(); ++index) {
        key[index] = lexora::protected_key::part_a[index] ^ lexora::protected_key::part_b[index];
    }
    return key;
}

}  // namespace

namespace lexora {

std::vector<unsigned char> decrypt_archive(const std::string& path) {
    const auto package = read_binary_file(path);
    const std::size_t minimum_size = package_magic.size() + nonce_size + tag_size;
    if (package.size() <= minimum_size) {
        throw std::runtime_error("encrypted code package is truncated");
    }
    if (!std::equal(package_magic.begin(), package_magic.end(), package.begin())) {
        throw std::runtime_error("encrypted code package has an invalid header");
    }

    const unsigned char* nonce = package.data() + package_magic.size();
    const unsigned char* ciphertext = nonce + nonce_size;
    const std::size_t encrypted_size = package.size() - package_magic.size() - nonce_size;
    const std::size_t ciphertext_size = encrypted_size - tag_size;
    const unsigned char* tag = ciphertext + ciphertext_size;

    auto key = reconstruct_key();
    cipher_context context(EVP_CIPHER_CTX_new(), &EVP_CIPHER_CTX_free);
    if (!context) {
        OPENSSL_cleanse(key.data(), key.size());
        throw std::runtime_error("cannot allocate AES context");
    }

    int output_size = 0;
    int final_size = 0;
    std::vector<unsigned char> plaintext(ciphertext_size);
    bool ok = EVP_DecryptInit_ex(context.get(), EVP_aes_256_gcm(), nullptr, nullptr, nullptr) == 1
        && EVP_CIPHER_CTX_ctrl(context.get(), EVP_CTRL_GCM_SET_IVLEN, static_cast<int>(nonce_size), nullptr) == 1
        && EVP_DecryptInit_ex(context.get(), nullptr, nullptr, key.data(), nonce) == 1
        && EVP_DecryptUpdate(
               context.get(), nullptr, &output_size, package_magic.data(), static_cast<int>(package_magic.size())) == 1
        && EVP_DecryptUpdate(
               context.get(), plaintext.data(), &output_size, ciphertext, static_cast<int>(ciphertext_size)) == 1
        && EVP_CIPHER_CTX_ctrl(
               context.get(), EVP_CTRL_GCM_SET_TAG, static_cast<int>(tag_size), const_cast<unsigned char*>(tag)) == 1;

    OPENSSL_cleanse(key.data(), key.size());
    if (!ok || EVP_DecryptFinal_ex(context.get(), plaintext.data() + output_size, &final_size) != 1) {
        OPENSSL_cleanse(plaintext.data(), plaintext.size());
        throw std::runtime_error("encrypted code package authentication failed");
    }
    plaintext.resize(static_cast<std::size_t>(output_size + final_size));
    return plaintext;
}

}  // namespace lexora
