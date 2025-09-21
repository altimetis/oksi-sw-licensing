// Fingerprint Utility (C++)
// ---------------------------------
// Purpose:
//   Generate a stable, non-PII-heavy machine fingerprint. Intended for Linux
//   hosts that provide
//   /etc/machine-id. Output is a URL-safe base64 (no padding) of a SHA-256
//   digest.
//
// What it does:
//   1) Reads /etc/machine-id (if present) and adds it as "mid:<value>".
//   2) Optionally includes a user-provided salt as "salt:<value>".
//   3) Joins present parts with '|', hashes with SHA-256, and base64-url encodes
//      the digest without '=' padding.
//
// Why this approach:
//   - /etc/machine-id is a stable identifier for a given OS install.
//   - The salt lets you scope/partition fingerprints per-product or per-tenant
//     without exposing additional identifying data.
//   - No direct use of MAC, CPU serials, or other intrusive identifiers.
//
// Usage examples:
//   ./fingerprint_cpp
//   ./fingerprint_cpp --salt my-product-id

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

// Trim helper: removes whitespace from both ends of a string.
static std::string trim(const std::string &s) {
    size_t start = 0;
    while (start < s.size() && (s[start] == ' ' || s[start] == '\n' || s[start] == '\r' || s[start] == '\t')) start++;
    size_t end = s.size();
    while (end > start && (s[end-1] == ' ' || s[end-1] == '\n' || s[end-1] == '\r' || s[end-1] == '\t')) end--;
    return s.substr(start, end - start);
}

// Read entire file into a string (best-effort). Returns empty on failure.
static std::string read_file(const std::string &path) {
    std::ifstream f(path);
    if (!f.good()) return std::string();
    std::ostringstream ss;
    ss << f.rdbuf();
    return trim(ss.str());
}

// Minimal SHA-256 implementation (no external deps).
//
// High-level overview of SHA-256:
//   - Processes input in 512-bit (64-byte) chunks.
//   - Maintains an internal 256-bit state (8 x 32-bit words).
//   - Each chunk is expanded into a message schedule (64 x 32-bit words),
//     then mixed through a compression function with round constants.
//   - Final output is the 256-bit state after processing all chunks.
class SHA256 {
public:
    SHA256() { reset(); }

    // Initialize internal state and counters.
    void reset() {
        m_data_len = 0; m_bit_len = 0;
        m_state[0] = 0x6a09e667;
        m_state[1] = 0xbb67ae85;
        m_state[2] = 0x3c6ef372;
        m_state[3] = 0xa54ff53a;
        m_state[4] = 0x510e527f;
        m_state[5] = 0x9b05688c;
        m_state[6] = 0x1f83d9ab;
        m_state[7] = 0x5be0cd19;
    }

    // Feed arbitrary bytes into the hash; buffers into 64-byte blocks.
    void update(const uint8_t *data, size_t len) {
        for (size_t i = 0; i < len; ++i) {
            m_data[m_data_len] = data[i];
            m_data_len++;
            if (m_data_len == 64) {
                transform();
                m_bit_len += 512;
                m_data_len = 0;
            }
        }
    }
    // Convenience overload for std::string input.
    void update(const std::string &s) { update(reinterpret_cast<const uint8_t*>(s.data()), s.size()); }

    // Finalize and return the 32-byte (256-bit) digest.
    std::array<uint8_t,32> digest() {
        std::array<uint8_t,32> hash{};
        size_t i = m_data_len;

        // Padding: append 0x80, then zeros, leaving 8 bytes for bit length
        if (m_data_len < 56) {
            m_data[i++] = 0x80;
            while (i < 56) m_data[i++] = 0x00;
        } else {
            m_data[i++] = 0x80;
            while (i < 64) m_data[i++] = 0x00;
            transform();
            memset(m_data, 0, 56);
        }
        // Append total message length in bits (big-endian)
        m_bit_len += m_data_len * 8;
        m_data[63] = m_bit_len;
        m_data[62] = m_bit_len >> 8;
        m_data[61] = m_bit_len >> 16;
        m_data[60] = m_bit_len >> 24;
        m_data[59] = m_bit_len >> 32;
        m_data[58] = m_bit_len >> 40;
        m_data[57] = m_bit_len >> 48;
        m_data[56] = m_bit_len >> 56;
        transform();
        // Convert internal state to big-endian byte array
        for (i = 0; i < 4; ++i) {
            hash[i]      = (m_state[0] >> (24 - i * 8)) & 0x000000ff;
            hash[i + 4]  = (m_state[1] >> (24 - i * 8)) & 0x000000ff;
            hash[i + 8]  = (m_state[2] >> (24 - i * 8)) & 0x000000ff;
            hash[i + 12] = (m_state[3] >> (24 - i * 8)) & 0x000000ff;
            hash[i + 16] = (m_state[4] >> (24 - i * 8)) & 0x000000ff;
            hash[i + 20] = (m_state[5] >> (24 - i * 8)) & 0x000000ff;
            hash[i + 24] = (m_state[6] >> (24 - i * 8)) & 0x000000ff;
            hash[i + 28] = (m_state[7] >> (24 - i * 8)) & 0x000000ff;
        }
        return hash;
    }

private:
    uint8_t m_data[64];
    uint32_t m_data_len;
    uint64_t m_bit_len;
    uint32_t m_state[8];

    // SHA-256 helper functions (bitwise primitives defined by the spec)
    static uint32_t rotr(uint32_t x, uint32_t n) { return (x >> n) | (x << (32 - n)); }
    static uint32_t ch(uint32_t x, uint32_t y, uint32_t z) { return (x & y) ^ (~x & z); }
    static uint32_t maj(uint32_t x, uint32_t y, uint32_t z) { return (x & y) ^ (x & z) ^ (y & z); }
    static uint32_t ep0(uint32_t x) { return rotr(x,2) ^ rotr(x,13) ^ rotr(x,22); }
    static uint32_t ep1(uint32_t x) { return rotr(x,6) ^ rotr(x,11) ^ rotr(x,25); }
    static uint32_t sig0(uint32_t x) { return rotr(x,7) ^ rotr(x,18) ^ (x >> 3); }
    static uint32_t sig1(uint32_t x) { return rotr(x,17) ^ rotr(x,19) ^ (x >> 10); }

    // Core compression: processes one 512-bit block.
    void transform() {
        static const uint32_t K[64] = {
            0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
            0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
            0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
            0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
            0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
            0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
            0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
            0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
        };
        uint32_t m[64];
        // Prepare message schedule m[0..63]
        for (uint32_t i = 0, j = 0; i < 16; ++i, j += 4)
            m[i] = (m_data[j] << 24) | (m_data[j+1] << 16) | (m_data[j+2] << 8) | (m_data[j+3]);
        for (uint32_t i = 16; i < 64; ++i)
            m[i] = sig1(m[i-2]) + m[i-7] + sig0(m[i-15]) + m[i-16];

        // Initialize working variables with current state
        uint32_t a = m_state[0];
        uint32_t b = m_state[1];
        uint32_t c = m_state[2];
        uint32_t d = m_state[3];
        uint32_t e = m_state[4];
        uint32_t f = m_state[5];
        uint32_t g = m_state[6];
        uint32_t h = m_state[7];

        // 64 rounds of mixing with constants and schedule
        for (uint32_t i = 0; i < 64; ++i) {
            uint32_t t1 = h + ep1(e) + ch(e,f,g) + K[i] + m[i];
            uint32_t t2 = ep0(a) + maj(a,b,c);
            h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
        }

        // Add the compressed chunk to the current hash value
        m_state[0] += a;
        m_state[1] += b;
        m_state[2] += c;
        m_state[3] += d;
        m_state[4] += e;
        m_state[5] += f;
        m_state[6] += g;
        m_state[7] += h;
    }
};

// Base64 (URL-safe) encoder without '=' padding.
static std::string base64_urlsafe_nopad(const uint8_t *data, size_t len) {
    static const char* tbl = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    std::string out;
    out.reserve(((len + 2) / 3) * 4);
    size_t i = 0;
    while (i + 3 <= len) {
        uint32_t n = (data[i] << 16) | (data[i+1] << 8) | (data[i+2]);
        i += 3;
        out.push_back(tbl[(n >> 18) & 63]);
        out.push_back(tbl[(n >> 12) & 63]);
        out.push_back(tbl[(n >> 6) & 63]);
        out.push_back(tbl[n & 63]);
    }
    size_t rem = len - i;
    if (rem == 1) {
        uint32_t n = (data[i] << 16);
        out.push_back(tbl[(n >> 18) & 63]);
        out.push_back(tbl[(n >> 12) & 63]);
    } else if (rem == 2) {
        uint32_t n = (data[i] << 16) | (data[i+1] << 8);
        out.push_back(tbl[(n >> 18) & 63]);
        out.push_back(tbl[(n >> 12) & 63]);
        out.push_back(tbl[(n >> 6) & 63]);
    }
    return out;
}

int main(int argc, char** argv) {
    // Parse optional arguments: --salt or --extra-salt <value>
    std::string salt;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if ((a == "--salt" || a == "--extra-salt") && i + 1 < argc) {
            salt = argv[++i];
        }
    }

    // Collect input components (present parts only)
    std::vector<std::string> parts;
    std::string machine_id = read_file("/etc/machine-id");
    if (!machine_id.empty()) {
        parts.push_back(std::string("mid:") + machine_id);
    }
    if (!salt.empty()) {
        parts.push_back(std::string("salt:") + salt);
    }
    // Join components with '|' in a stable format
    std::string joined;
    for (size_t i = 0; i < parts.size(); ++i) {
        if (i) joined.push_back('|');
        joined += parts[i];
    }

    // Hash then encode in URL-safe base64 (no padding)
    SHA256 sha;
    sha.update(joined);
    auto dig = sha.digest();
    std::string out = base64_urlsafe_nopad(dig.data(), dig.size());
    std::cout << out << std::endl;
    return 0;
}
