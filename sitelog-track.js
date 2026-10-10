// sitelog-track.js — v9 使用率埋点（PR-1-1 前端）。对应后端 POST /api/share/usage。
// 设计铁律：纯旁路、失败静默；绝不抛错、绝不拖慢主流程。
// 事件类型白名单与后端 usage.py 的 ALLOWED_EVENTS 保持一致。
(function () {
  'use strict';
  var ENDPOINT = '/api/share/usage';
  var ALLOWED = { share_view: 1, record_upload: 1, signoff: 1, owner_share_open: 1 };

  window.sitelogTrack = function (eventType, shareCode, meta) {
    try {
      if (!ALLOWED[eventType]) return;
      var payload = { event_type: eventType };
      if (shareCode != null) payload.share_code = String(shareCode).slice(0, 64);
      if (meta != null && typeof meta === 'object') payload.meta = meta;
      var body = JSON.stringify(payload);

      if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
        try {
          navigator.sendBeacon(ENDPOINT, new Blob([body], { type: 'application/json' }));
          return;
        } catch (e) { /* 落到 fetch 兜底 */ }
      }
      // 兜底：非卸载时机用 fetch（keepalive 保证页面切走也能发出去）。失败一律静默。
      fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body,
        keepalive: true,
        credentials: 'same-origin',
        cache: 'no-store',
      }).catch(function () {});
    } catch (e) { /* 埋点失败不影响业务 */ }
  };
})();
