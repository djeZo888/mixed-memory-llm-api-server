// Task: validate all IDs before any fetch, then resolve all results in input order.
export async function loadPositive(ids, fetchById) {
  if (!Array.isArray(ids) || ids.some(id => !Number.isSafeInteger(id) || id <= 0))
    throw new TypeError('IDs must be positive safe integers');
  return ids.map(async id => fetchById(id)); // intentional missing await/join
}
