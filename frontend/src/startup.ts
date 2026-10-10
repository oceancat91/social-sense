type EntryOptions = {
  root: HTMLElement;
  unlock: () => Promise<boolean>;
  cancel: () => void;
  start: (silent: boolean) => void;
};

/**
 * Owns the entry gesture, including keyboard focus and failed audio startup.
 *
 * 入口页不再有独立按钮：整块 `.loading` 接收点击，屏幕正中的提示文字本身可聚焦，
 * 所以键盘依然可达（root 的 keydown 只有在焦点落在它内部时才会触发，
 * 因此 ready() 会把焦点交给提示文字，Tab 也被约束在对话框内）。
 */
export class StartupGate {
  private state: "loading" | "waiting" | "starting" | "error" | "started" = "loading";
  private request = 0;
  private silent: HTMLButtonElement;
  private status: HTMLElement;
  constructor(private options: EntryOptions) {
    const { root } = options;
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute("aria-label", "进入舆情感知档案终端");
    root.insertAdjacentHTML(
      "beforeend",
      '<div class="entry-controls"><p class="entry-status is-shown" role="status" tabindex="-1">资源就绪后即可进入</p><button class="entry-silent" hidden>关闭声音并进入</button></div>',
    );
    this.silent = root.querySelector<HTMLButtonElement>(".entry-silent")!;
    this.status = root.querySelector<HTMLElement>(".entry-status")!;
    root.addEventListener("click", event => {
      event.stopPropagation();
      if ((event.target as Element).closest(".entry-silent")) {
        this.request++;
        options.cancel();
        this.finish(true);
      } else if (this.state === "waiting" || this.state === "error") void this.enter();
    });
    root.addEventListener("keydown", event => {
      event.stopPropagation();
      if (event.key === "Tab") {
        // 模态对话框：焦点不逃逸，单个可聚焦元素时原地保持。
        const targets = [this.status, this.silent].filter(
          el => el.tabIndex >= 0 && !el.hidden,
        );
        event.preventDefault();
        if (!targets.length) return;
        if (targets.length === 1) { targets[0].focus(); return; }
        const index = targets.indexOf(document.activeElement as HTMLElement);
        targets[(index + (event.shiftKey ? targets.length - 1 : 1)) % targets.length].focus();
        return;
      }
      // 提示文字不是原生按钮，Enter / Space 需要自行接管。
      if (
        (event.key === "Enter" || event.key === " ") &&
        (this.state === "waiting" || this.state === "error")
      ) {
        event.preventDefault();
        void this.enter();
      }
    });
  }
  get phase() { return this.state; }
  ready() {
    this.state = "waiting";
    this.options.root.dataset.entry = "waiting";
    this.options.root.querySelector(":scope > span")!.textContent = "INTERNAL DATABASE / READY";
    this.prompt("轻触屏幕或按 Enter 开始", { fade: true, interactive: true });
    this.status.focus({ preventScroll: true });
  }
  /**
   * 更新屏幕正中的提示。
   * fade=true 会先移除再重新加回 .is-shown（中间强制重排），从而重新播放淡入，
   * 用于状态跃迁时给出视觉反馈；渐隐渐显的时长交给 CSS 过渡。
   */
  private prompt(text: string, { fade = false, interactive = false } = {}) {
    this.status.textContent = text;
    this.status.tabIndex = interactive ? 0 : -1;
    this.status.classList.toggle("is-interactive", interactive);
    if (fade) {
      this.status.classList.remove("is-shown");
      void this.status.offsetWidth;
    }
    this.status.classList.add("is-shown");
  }
  private async enter() {
    const request = ++this.request;
    this.state = "starting";
    this.options.root.dataset.entry = "starting";
    this.prompt("正在准备声音…");
    this.silent.hidden = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const fail = () => {
      if (request !== this.request) return;
      this.options.cancel();
      this.state = "error";
      this.options.root.dataset.entry = "error";
      this.prompt("声音暂未就绪 · 轻触重试，或选择无声进入", { fade: true, interactive: true });
      this.status.focus({ preventScroll: true });
    };
    try {
      const unlocked = await Promise.race([
        this.options.unlock(),
        new Promise<boolean>(resolve => { timer = setTimeout(() => resolve(false), 20000); }),
      ]);
      if (request !== this.request) return;
      if (unlocked && !document.hidden) this.finish(false);
      else fail();
    } catch { fail(); } finally { clearTimeout(timer); }
  }
  private finish(silent: boolean) {
    if (this.state === "started") return;
    this.state = "started";
    this.options.start(silent);
  }
}
