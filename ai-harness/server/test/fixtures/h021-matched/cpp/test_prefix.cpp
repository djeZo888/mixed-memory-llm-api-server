#include "prefix.hpp"
#include <cassert>
int main() {
    const std::vector<int> values{3, -4, 99};
    assert(prefix_sum(values, 0) == 0);
    assert(prefix_sum(values, 1) == 3);
    assert(prefix_sum(values, 2) == -1);
    assert(prefix_sum(values, 3) == 98);
    assert(prefix_sum({}, 0) == 0);
    bool rejected = false;
    try { (void)prefix_sum(values, 4); } catch (const std::out_of_range&) { rejected = true; }
    assert(rejected);
}
