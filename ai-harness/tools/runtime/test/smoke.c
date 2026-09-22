// SPDX-License-Identifier: MIT
#include <math.h>
#include <stddef.h>
static double parallel_resistance(double a, double b) {
    return a > 0 && b > 0 ? a * b / (a + b) : NAN;
}
int main(void) {
    if (fabs(parallel_resistance(1000, 1000) - 500) > 1e-9) return 1;
    if (!isnan(parallel_resistance(-1, 1000))) return 2;
    return 0;
}
