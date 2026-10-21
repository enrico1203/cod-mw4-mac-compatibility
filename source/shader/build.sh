#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
mkdir -p build
xcrun clang -arch x86_64 -mmacosx-version-min=13.0 -std=c11 -O2 -Wall -Wextra -Werror -dynamiclib -DCAP_MASK=1 observer.c -o build/sp26.dylib -Wl,-install_name,@rpath/sp26.dylib
codesign --force --sign - build/sp26.dylib
codesign --verify --strict build/sp26.dylib
xcrun clang -arch x86_64 -mmacosx-version-min=13.0 -std=c11 -O2 -Wall -Wextra -Werror -DCAP_MASK=1 contract.c -o build/contract
./build/contract
