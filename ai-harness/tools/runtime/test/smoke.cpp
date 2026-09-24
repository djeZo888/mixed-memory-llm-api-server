// SPDX-License-Identifier: MIT
#include <algorithm>
#include <array>
#include <ranges>
int main() {
    const std::array readings{3, 1, 2, 4};
    int sum = 0;
    for (int value : readings | std::views::filter([](int n) { return n % 2 == 0; })) sum += value;
    return sum == 6 && std::ranges::max(readings) == 4 ? 0 : 1;
}
