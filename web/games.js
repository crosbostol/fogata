/* Local game rules. No API calls, credentials or server state. */
(() => {
  "use strict";
  class ClickRound {
    constructor(now) { this.startedAt = now; this.endsAt = now + 15000; this.clicks = 0; }
    click(now) { if (now >= this.startedAt && now < this.endsAt) this.clicks += 1; }
    result(now) {
      const elapsed = Math.max(0, Math.min(15000, now - this.startedAt));
      return { clicks: this.clicks, remaining: Math.max(0, this.endsAt - now),
        cps: elapsed ? this.clicks / (elapsed / 1000) : 0, done: now >= this.endsAt };
    }
  }
  class Runner {
    constructor(random = Math.random) {
      this.random = random; this.y = 0; this.velocity = 0;
      this.obstacle = 110; this.distance = 0; this.over = false;
    }
    jump() { if (!this.over && this.y === 0) this.velocity = 365; }
    step(seconds) {
      // Small steps keep collision detection reliable on slower displays.
      let remaining = Math.min(Math.max(seconds, 0), 0.1);
      while (remaining > 0 && !this.over) {
        const dt = Math.min(remaining, 0.01);
        remaining -= dt;
        this.y = Math.max(0, this.y + this.velocity * dt);
        this.velocity = this.y > 0 ? this.velocity - 1100 * dt : 0;
        const speed = Math.min(65, 35 + this.distance / 50);
        this.obstacle -= speed * dt;
        this.distance += speed * dt / 4;
        if (this.obstacle < 15 && this.obstacle + 5 > 8 && this.y < 23) this.over = true;
        if (this.obstacle < -6) this.obstacle = 105 + this.random() * 35;
      }
    }
  }
  const rules = { ClickRound, Runner };
  if (typeof module !== "undefined" && module.exports) module.exports = rules;
  if (typeof window !== "undefined") window.FogataGameRules = rules;
})();
