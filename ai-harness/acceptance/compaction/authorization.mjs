/** Root-frozen authorization, never derived from a model/request deadline. */
export const AUTHORIZATIONS = Object.freeze({
  H040: Object.freeze({ task: 'H040', startsUtc: '2026-10-01T02:26:10Z', capUtc: '2026-10-01T04:26:10Z' }),
  H041: Object.freeze({ task: 'H041', startsUtc: '2026-10-01T08:05:07Z', capUtc: '2026-10-01T10:05:07Z' }),
  'H041-COMPACTION-CONTINUATION-02': Object.freeze({ task: 'H041-COMPACTION-CONTINUATION-02', startsUtc: '2026-10-01T09:11:06.096969+00:00', capUtc: '2026-10-01T11:11:06.096969+00:00' }),
});
export const H041_SETTLEMENT_RESERVE_MS = 120000;
export function reviewedAuthorization(review, now = Date.now()) {
  const a = review?.authorization, frozen = AUTHORIZATIONS[a?.task];
  const expiry = Date.parse(review?.notAfterUtc), reserve = review?.settlementReserveMs ?? review?.nativeSettlementReserveMs;
  if (!frozen || a.startsUtc !== frozen.startsUtc || a.capUtc !== frozen.capUtc ||
      typeof a.windowId !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(a.windowId) ||
      !Number.isSafeInteger(reserve) || (a.task !== 'H040' ? reserve !== H041_SETTLEMENT_RESERVE_MS : reserve < 75000 || reserve > 300000) ||
      now < Date.parse(frozen.startsUtc) || !Number.isFinite(expiry) || expiry <= now || expiry > Date.parse(frozen.capUtc))
    throw Error('root_explicit_authorization_required_or_expired');
  return { expiresAt: expiry, dispatchCutoffAt: expiry - reserve, settlementReserveMs: reserve, authorization: frozen };
}
