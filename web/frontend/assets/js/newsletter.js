// New subscriptions are unavailable in this release. Keep the mount API for
// existing pages, including pages that previously mounted an active form.
(function () {
  "use strict";

  window.mountNewsletter = function (containerId, source) {
    var root = document.getElementById(containerId);
    if (!root) return;
    // Replace an old mounted form too; its flag must not preserve collection.
    if (root.dataset.newsletterMounted === "closed") return;
    root.innerHTML =
      '<div class="newsletter-card">' +
        '<span class="newsletter-eyebrow">不定期研究更新</span>' +
        '<h2 class="newsletter-title">新增订阅暂不可用</h2>' +
        '<p class="newsletter-body">本版不收集订阅邮箱。研究进展和公开负结果可在站内查看。</p>' +
        '<p class="newsletter-fineprint">既有订阅请查看原邮件中的退订说明。</p>' +
      '</div>';
    root.dataset.newsletterMounted = "closed";
  };
})();
