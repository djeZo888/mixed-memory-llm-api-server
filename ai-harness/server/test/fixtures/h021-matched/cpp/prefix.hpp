#pragma once
#include <cstddef>
#include <stdexcept>
#include <vector>
// Task: sum exactly count values; reject count greater than vector size.
inline long prefix_sum(const std::vector<int>& values, std::size_t count) {
    if (count > values.size()) throw std::out_of_range("count");
    long sum = 0;
    for (std::size_t i = 0; i <= count; ++i) sum += values.at(i); // intentional bounds bug
    return sum;
}
