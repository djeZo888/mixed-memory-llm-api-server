/** Root-frozen authorization, never derived from a model/request deadline. */
export const AUTHORIZATIONS = Object.freeze({
  H044: Object.freeze({ task: 'H044', startsUtc: '2026-10-01T23:14:41Z', capUtc: '2026-10-02T07:45:00Z' }),
  H043: Object.freeze({ task: 'H043', startsUtc: '2026-10-01T21:19:33Z', capUtc: '2026-10-02T00:04:33Z' }),
  H040: Object.freeze({ task: 'H040', startsUtc: '2026-10-01T02:26:10Z', capUtc: '2026-10-01T04:26:10Z' }),
  H041: Object.freeze({ task: 'H041', startsUtc: '2026-10-01T08:05:07Z', capUtc: '2026-10-01T10:05:07Z' }),
  'H041-COMPACTION-DELIVERY-05': Object.freeze({ task: 'H041-COMPACTION-DELIVERY-05', startsUtc: '2026-10-01T14:30:02.674394+00:00', capUtc: '2026-10-01T18:30:02.674394+00:00' }),
  'H041-COMPACTION-DELIVERY-04': Object.freeze({ task: 'H041-COMPACTION-DELIVERY-04', startsUtc: '2026-10-01T11:26:45.729698+00:00', capUtc: '2026-10-01T15:26:45.729698+00:00' }),
  'H041-COMPACTION-DELIVERY-03': Object.freeze({ task: 'H041-COMPACTION-DELIVERY-03', startsUtc: '2026-10-01T10:07:11.972488+00:00', capUtc: '2026-10-01T13:07:11.972488+00:00' }),
  'H041-COMPACTION-CONTINUATION-02': Object.freeze({ task: 'H041-COMPACTION-CONTINUATION-02', startsUtc: '2026-10-01T09:11:06.096969+00:00', capUtc: '2026-10-01T11:11:06.096969+00:00' }),
});
export const H041_SETTLEMENT_RESERVE_MS = 120000;
export function reviewedAuthorization(review, now = Date.now()) {
  const a = review?.authorization, frozen = AUTHORIZATIONS[a?.task];
  const expiry = Date.parse(review?.notAfterUtc), reserve = review?.settlementReserveMs ?? review?.nativeSettlementReserveMs;
  if (!Number.isFinite(now) || !frozen || a.startsUtc !== frozen.startsUtc || a.capUtc !== frozen.capUtc ||
      typeof a.windowId !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(a.windowId) ||
      !Number.isSafeInteger(reserve) || (a.task !== 'H040' ? reserve !== H041_SETTLEMENT_RESERVE_MS : reserve < 75000 || reserve > 300000) ||
      now < Date.parse(frozen.startsUtc) || !Number.isFinite(expiry) || expiry <= now || expiry > Date.parse(frozen.capUtc))
    throw Error('root_explicit_authorization_required_or_expired');
  return { expiresAt: expiry, dispatchCutoffAt: expiry - reserve, settlementReserveMs: reserve, authorization: frozen };
}
