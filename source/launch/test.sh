#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
mkdir -p build
clang -std=c11 -O2 -Wall -Wextra -Werror -fsanitize=address,undefined test_wait.c -o build/test-wait
./build/test-wait
clang -std=c11 -O2 -fshort-wchar -fdeclspec -Wall -Wextra -Werror -fsanitize=address,undefined test_notice.c -o build/test-notice
./build/test-notice
