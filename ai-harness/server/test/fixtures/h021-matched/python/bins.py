"""Task: return the half-open interval index, or None outside all intervals.
Precondition: edges contains at least two strictly increasing numeric values.
"""
def bin_index(value, edges):
    for i, (lower, upper) in enumerate(zip(edges, edges[1:])):
        if lower <= value <= upper:  # intentional boundary bug
            return i
    return None
