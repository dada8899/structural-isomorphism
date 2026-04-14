/**
 * Structural — Onboarding flow (3 steps)
 */

const ONB_KEY = 'structural_onboarding_complete';

window.Onboarding = {
  shouldShow() {
    return !Storage.get(ONB_KEY, false);
  },

  markComplete() {
    Storage.set(ONB_KEY, true);
  },

  reset() {
    Storage.set(ONB_KEY, false);
  },

  init(onComplete) {
    if (!this.shouldShow()) {
      this._showSearchTooltip();
      return;
    }

    const overlay = $('.onboarding');
    if (!overlay) return;

    overlay.classList.add('active');
    this._showStep(1);

    const skipBtn = $('.onboarding__skip');
    skipBtn.addEventListener('click', () => this._finish(onComplete));

    const continueBtn = $('.onb-welcome__continue');
    continueBtn.addEventListener('click', () => this._showStep(2));

    const tryBtn = $('.onb-example__try');
    tryBtn.addEventListener('click', () => this._finish(onComplete));

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this._finish(onComplete);
    });
  },

  _showStep(n) {
    $$('.onboarding__step').forEach((el) => el.classList.remove('active'));
    const step = $(`.onboarding__step[data-step="${n}"]`);
    if (step) {
      step.classList.add('active');
      // Re-trigger animations
      step.querySelectorAll('[class*="animation"], .onb-welcome__headline, .onb-welcome__subtitle, .onb-welcome__diagram, .onb-welcome__continue').forEach((el) => {
        el.style.animation = 'none';
        void el.offsetHeight;
        el.style.animation = '';
      });
    }
  },

  _finish(cb) {
    const overlay = $('.onboarding');
    overlay.classList.add('closing');
    setTimeout(() => {
      overlay.classList.remove('active', 'closing');
      overlay.style.display = 'none';
      this.markComplete();
      this._showSearchTooltip();
      if (cb) cb();
    }, 400);
  },

  _showSearchTooltip() {
    // Show a tooltip near the search box on first search
    const shownKey = 'structural_tooltip_shown';
    if (Storage.get(shownKey, false)) return;

    setTimeout(() => {
      const searchbox = $('.searchbox');
      if (!searchbox) return;

      const tooltip = document.createElement('div');
      tooltip.className = 'onb-tooltip';
      tooltip.textContent = '描述一个你好奇的现象，比如"交通越治越堵"';
      const rect = searchbox.getBoundingClientRect();
      tooltip.style.left = `${rect.left + rect.width / 2 - 160}px`;
      tooltip.style.top = `${rect.top - 50 + window.scrollY}px`;
      document.body.appendChild(tooltip);

      // Add breathe effect to search box
      searchbox.classList.add('searchbox--pulsing');

      const dismiss = () => {
        tooltip.classList.add('fade-out');
        searchbox.classList.remove('searchbox--pulsing');
        setTimeout(() => tooltip.remove(), 300);
        Storage.set(shownKey, true);
        input.removeEventListener('input', dismiss);
        input.removeEventListener('focus', dismiss);
      };

      const input = $('.searchbox__input');
      if (input) {
        input.addEventListener('input', dismiss, { once: true });
        input.addEventListener('focus', dismiss, { once: true });
      }

      // Auto dismiss after 10 seconds
      setTimeout(dismiss, 10000);
    }, 800);
  },
};
